"""角色准入：表单显隐、交评接口、成功片段插入三条链路各自独立判定。

只读角色（reader）在三条链路上一律不放行；只有审评员（writer）放行。
这里没有总开关：任一判定都直接认会话角色，不提供可勾选的角色开关台。
"""

WRITER_ROLE = "writer"
READER_ROLE = "reader"


def is_writer(role: str | None) -> bool:
    return role == WRITER_ROLE


def allow_write(role: str | None) -> bool:
    """交评接口是否接受该会话的提交并落库。"""
    return is_writer(role)


def show_form(role: str | None) -> bool:
    """首页是否给该会话渲染交评表。"""
    return is_writer(role)


def allow_fragment_insert(role: str | None, ok: bool) -> bool:
    """成功后是否允许把新行片段插回页面：仅 writer 且接口确已成功。"""
    return is_writer(role) and ok
