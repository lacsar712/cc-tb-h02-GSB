"""只读拦截回归：三处放行钩子卸掉后，观察员处处碰壁，审评员照常交评。

同时核对：
- 只读碰壁后记录数不变
- 可写成功后记录数加一，片段正常返回
- 只读首页不再出现交评表
"""

import importlib.util
from pathlib import Path

import pytest

import app as app_module

BACKEND_DIR = Path(__file__).parent

PASSING_FORM = {"lot": "秋茶-B", "aroma": "8", "taste": "8", "liquor": "7"}


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("select * from cuppings"):
            self._rows = sorted(self.conn.store, key=lambda r: r["id"], reverse=True)
        elif normalized.startswith("insert into cuppings"):
            lot, aroma, taste, liquor, score, verdict, note, created_by = params
            self._row = {
                "id": self.conn.next_id,
                "lot": lot,
                "aroma": aroma,
                "taste": taste,
                "liquor": liquor,
                "score": score,
                "verdict": verdict,
                "note": note,
                "created_by": created_by,
            }
            self.conn.next_id += 1
            self.conn.store.append(self._row)
        else:
            raise AssertionError(f"未预期的 SQL: {sql}")

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class FakeConn:
    def __init__(self):
        self.store = []
        self.next_id = 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self, cursor_factory=None):
        return FakeCursor(self)

    def commit(self):
        pass


@pytest.fixture
def client(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(app_module, "db", lambda: conn)
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client, conn


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password})


def submit(client, form):
    return client.post("/cuppings", data=form, headers={"HX-Request": "true"})


def test_observer_home_has_no_cupping_form(client):
    test_client, _ = client
    login(test_client, "observer", "look123456")
    res = test_client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "<form" not in html
    assert "新开一轮审评" not in html


def test_taster_home_shows_cupping_form(client):
    test_client, _ = client
    login(test_client, "taster", "tea123456")
    html = test_client.get("/").get_data(as_text=True)
    assert "<form" in html
    assert 'action="/cuppings"' in html


def test_observer_submit_rejected_and_count_unchanged(client):
    test_client, conn = client
    login(test_client, "observer", "look123456")
    before = len(conn.store)
    res = submit(test_client, PASSING_FORM)
    assert res.status_code == 403
    assert len(conn.store) == before
    assert "<tr" not in res.get_data(as_text=True)


def test_taster_submit_success_fragment_and_count_plus_one(client):
    test_client, conn = client
    login(test_client, "taster", "tea123456")
    before = len(conn.store)
    res = submit(test_client, PASSING_FORM)
    assert res.status_code == 200
    assert len(conn.store) == before + 1
    html = res.get_data(as_text=True)
    assert "<tr" in html
    assert "秋茶-B" in html
    assert "通过" in html
    row = conn.store[-1]
    assert row["created_by"] == "taster"
    assert row["score"] == pytest.approx(7.8)


def test_fragment_insert_only_after_success():
    js = (BACKEND_DIR / "templates" / "base.html").read_text(encoding="utf-8")
    assert "观察员放行旁路" not in js
    guard = js.find("if (!res.ok)")
    insert = js.find("insertAdjacentHTML")
    assert guard != -1 and insert != -1
    assert guard < insert


def test_bypass_module_removed():
    assert importlib.util.find_spec("observer_pass") is None
