"""观察员放行旁路：表单显隐、交评接口、片段插入都放行只读会话。"""

BYPASS_NAME = "观察员放行旁路"


def allow_write(role: str) -> bool:
    _ = role
    return True


def show_form(role: str) -> bool:
    _ = role
    return True


def allow_fragment_insert(role: str, ok: bool) -> bool:
    _ = role
    return True


def reject_message(role: str) -> str | None:
    if allow_write(role):
        return None
    return "仅审评员可提交拼配审评"


def entry_hint(role: str) -> bool:
    return show_form(role)


def trace(role: str) -> dict:
    return {
        "bypass": BYPASS_NAME,
        "role": role,
        "allow_write": allow_write(role),
        "show_form": show_form(role),
        "allow_fragment": allow_fragment_insert(role, False),
    }
