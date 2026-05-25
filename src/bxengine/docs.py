from __future__ import annotations

import inspect
import re

from bxengine.runtime.extensions import BxeExtensionBase


_DOC_TAG_PATTERN = re.compile(r"^@(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)\b(?:\s+(?P<body>.*))?$")

def get_docs(ext: type[BxeExtensionBase]) -> dict[str, str]:
    ext_docs = {}
    for attr_name in dir(ext):
        if attr_name.startswith("_"):
            continue
        attr = getattr(ext, attr_name, None)
        if attr is None:
            continue
        if callable(attr) and getattr(attr, "_is_bpp_function", False):
            names = []
            names.append(getattr(attr, "_bpp_function_name", "Unknown"))
            for alias in getattr(attr, "_bpp_function_aliases", ()):
                names.append(alias)
            for name in names:
                ext_docs[name] = attr.__doc__
    return ext_docs


def build_signature_from_docstring(function_name: str, docstring: str | None) -> str:
    if not docstring:
        return f"[{function_name}]"

    required: list[str] = []
    optional: list[str] = []

    for line in inspect.cleandoc(docstring).splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        match = _DOC_TAG_PATTERN.match(stripped)
        if not match:
            continue

        tag = match.group("tag").lower()
        if tag not in {"parameter", "optional"}:
            continue

        body = (match.group("body") or "").strip()
        if not body:
            continue

        param_name = body.split(None, 1)[0]
        if tag == "parameter":
            required.append(param_name)
            continue

        if param_name.endswith("?") or param_name == "...":
            optional.append(param_name)
        else:
            optional.append(f"{param_name}?")

    arg_names = [*required, *optional]
    if not arg_names:
        return f"[{function_name}]"
    return f"[{function_name} {' '.join(arg_names)}]"
