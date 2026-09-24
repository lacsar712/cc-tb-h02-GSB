"""只读/可写准入的自动化核对（纯标准库 HTTP；有 psycopg2 时直查记录数）。

核对项：
1. observer（只读）首页不渲染交评表；
2. observer 直接 POST 交评接口（带 HX-Request）被 403 挡回，且响应不是新行片段；
3. observer 碰壁后 cuppings 记录数不变；
4. taster（可写）交一笔够线分（8/8/8=8.0）成功，返回的片段是新的一行；
5. taster 成功后记录数恰好多 1，新行出现在首页表头。

用法：
    BASE_URL=http://web:8000 DATABASE_URL=postgresql://... python verify_access.py
"""

import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")
DATABASE_URL = os.environ.get("DATABASE_URL")

OBSERVER = ("observer", "look123456")
TASTER = ("taster", "tea123456")
FORM_MARKER = "新开一轮审评"
TBODY_RE = re.compile(r'<tbody id="rows">(.*?)</tbody>', re.S)
TR_RE = re.compile(r"<tr\b", re.S)

failures = []


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def new_client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def login(client, username, password):
    data = urllib.parse.urlencode({"username": username, "password": password}).encode()
    with client.open(f"{BASE_URL}/login", data=data) as resp:
        body = resp.read().decode()
        return resp.status, body


def get_home(client):
    with client.open(f"{BASE_URL}/") as resp:
        return resp.status, resp.read().decode()


def post_cupping(client, lot, aroma, taste, liquor):
    """返回 (status, body)；403 等非 2xx 不抛异常。"""
    data = urllib.parse.urlencode(
        {"lot": lot, "aroma": aroma, "taste": taste, "liquor": liquor}
    ).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/cuppings", data=data, headers={"HX-Request": "true"}, method="POST"
    )
    try:
        with client.open(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


def row_count_from_page(html):
    match = TBODY_RE.search(html)
    return len(TR_RE.findall(match.group(1))) if match else -1


_db_conn = None


def db_count():
    """直查数据库 COUNT；psycopg2 不可用时返回 None，调用方退化为页面计数。"""
    global _db_conn
    if not DATABASE_URL:
        return None
    try:
        import psycopg2
    except ImportError:
        return None
    if _db_conn is None:
        _db_conn = psycopg2.connect(DATABASE_URL)
    _db_conn.rollback()
    with _db_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cuppings")
        return cur.fetchone()[0]


def wait_health(timeout=30):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=5) as resp:
                if resp.status == 200:
                    return True
        except OSError as exc:
            last = exc
        time.sleep(1)
    raise RuntimeError(f"服务在 {timeout}s 内未就绪：{last}")


def main():
    wait_health()
    check("服务在线 /health=200", True)

    use_db = db_count() is not None
    print(f"记录数来源：{'数据库直查 COUNT(*)' if use_db else '首页表格行数解析（无 psycopg2/DATABASE_URL）'}")

    def record_count(html_for_fallback):
        direct = db_count()
        return direct if direct is not None else row_count_from_page(html_for_fallback)

    lot = "验收-够线分"

    # ---- 只读账号 observer ----
    reader = new_client()
    status, home_reader = login(reader, *OBSERVER)  # 登录 302 自动跟随到首页
    check("observer 登录成功", status == 200, f"实际 {status}")
    status, home_reader = get_home(reader)
    check("只读首页不出现交评表", status == 200 and FORM_MARKER not in home_reader)
    check("只读首页不含任何 <form", "<form" not in home_reader.lower())

    before = record_count(home_reader)
    status, body = post_cupping(reader, lot, 8, 8, 8)  # 8/8/8 加权 8.0，本应够线
    check("只读 POST /cuppings 返回 403", status == 403, f"实际 {status}")
    check("只读碰壁响应不是新行片段", not body.lstrip().lower().startswith("<tr"))
    _, home_reader_after = get_home(reader)
    after = record_count(home_reader_after)
    check("只读碰壁后记录数不变", before == after, f"{before} -> {after}")

    # ---- 可写账号 taster ----
    writer = new_client()
    status, _ = login(writer, *TASTER)
    check("taster 登录成功", status == 200)
    _, home_writer = get_home(writer)
    check("可写首页渲染交评表", FORM_MARKER in home_writer)

    before_w = record_count(home_writer)
    status, fragment = post_cupping(writer, lot, 9, 9, 7)  # 9*.3+9*.5+7*.2 = 8.6 够线
    check("可写提交够线分返回 200", status == 200, f"实际 {status}")
    check("成功响应是新行片段(<tr>)", fragment.lstrip().lower().startswith("<tr"))
    check("片段含提交批次", lot in fragment)
    check("片段结论为通过", "通过" in fragment)
    check("片段加权分为 8.6", ">8.6<" in fragment.replace(" ", ""))

    _, home_writer_after = get_home(writer)
    after_w = record_count(home_writer_after)
    check("可写成功后记录数加一", after_w == before_w + 1, f"{before_w} -> {after_w}")

    head = TBODY_RE.search(home_writer_after).group(1)
    check("新行出现在表头第一行", head.lstrip().startswith("<tr") and lot in head.split("</tr>")[0])

    # ---- 只读账号再看一眼：新数据可读，但依旧没有表单 ----
    _, home_reader_final = get_home(reader)
    check("只读仍看不到交评表", FORM_MARKER not in home_reader_final)
    check("只读可读到新提交的行（数据可见）", lot in home_reader_final)

    print()
    if failures:
        print(f"共 {len(failures)} 项未通过：{failures}")
        sys.exit(1)
    print("全部核对通过。")


if __name__ == "__main__":
    main()
