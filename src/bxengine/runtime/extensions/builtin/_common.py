import re
from typing import Any


_ITERATION_LIMIT = 131072


def _safe_cut(s: Any, num: int = 15) -> str:
    return str(s)[:num] + ("..." if len(str(s)) > num else "")


def _is_number(v: Any) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def _is_whole(v: Any) -> bool:
    try:
        i = int(v)
        f = float(v)
        return f - i == 0
    except (ValueError, TypeError):
        return False


def _equal_repr(v: Any) -> int | str | list:
    if _is_number(v):
        return str(float(v))
    elif v is int or v is float:
        return str(v)
    return v


def _validate_variable_name(name: str) -> None:
    if not isinstance(name, str):
        raise NameError(f"Variable name must be a string: {_safe_cut(name)}")
    if re.search(r"[^A-Za-z_0-9]", name) or (name and re.search(r"[0-9]", name[0])):
        raise NameError(
            f"Variable name must be only letters, underscores and numbers, "
            f"and cannot start with a number: {_safe_cut(name)}"
        )


def _validate_macro_name(name: str) -> None:
    if not isinstance(name, str):
        raise NameError(f"Macro name must be a string: {_safe_cut(name)}")
    if name == "":
        raise NameError("Macro name cannot be empty")
    if re.search(r'[\\\s\[\]"“”]', name):
        raise NameError(
            "Macro name cannot contain spaces, brackets, quotes, or backslashes: "
            f"{_safe_cut(name)}"
        )

