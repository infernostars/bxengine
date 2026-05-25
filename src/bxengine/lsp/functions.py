from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from functools import lru_cache

from bxengine.docs import build_signature_from_docstring
from bxengine.docs import get_docs
from bxengine.runtime.extensions.BxeExtension import BxeExtensionBase
from bxengine.runtime.extensions.builtin import BuiltinExtension
from bxengine.runtime.extensions.discord_stub import (
    BrainGlobalExtension,
    BrainUserExtension,
    DiscordStubExtension,
)


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    signature: str
    documentation_markdown: str | None
    is_node_transformer: bool


def _iter_extension_functions(
    ext: BxeExtensionBase,
    docs_by_attr_name: dict[str, str],
) -> list[FunctionInfo]:
    infos: list[FunctionInfo] = []
    for attr_name in dir(ext):
        if attr_name.startswith("_"):
            continue

        attr = getattr(ext, attr_name, None)
        if attr is None or not callable(attr):
            continue
        if not getattr(attr, "_is_bpp_function", False):
            continue

        primary = str(getattr(attr, "_bpp_function_name", attr_name)).upper()
        aliases = tuple(str(alias).upper() for alias in getattr(attr, "_bpp_function_aliases", ()))
        is_node_transformer = bool(getattr(attr, "_node_transformer", False))
        raw_doc = docs_by_attr_name.get(attr_name) or inspect.getdoc(attr)
        signature = build_signature_from_docstring(primary, raw_doc)
        documentation_markdown = _format_docstring_markdown(raw_doc)

        seen_names: set[str] = set()
        for name in (primary, *aliases):
            if name in seen_names:
                continue
            seen_names.add(name)
            infos.append(
                FunctionInfo(
                    name=name,
                    signature=signature.replace(primary, name, 1),
                    documentation_markdown=documentation_markdown,
                    is_node_transformer=is_node_transformer,
                )
            )
    return infos


_DOC_TAG_PATTERN = re.compile(r"^@(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)\b(?:\s+(?P<body>.*))?$")


def _append_text(target: list[str], text: str) -> None:
    clean = text.strip()
    if clean:
        target.append(clean)


def _extend_last(target: list[str], text: str) -> None:
    clean = text.strip()
    if not clean:
        return
    if target:
        target[-1] = f"{target[-1]} {clean}"
    else:
        target.append(clean)


def _format_docstring_markdown(raw_doc: str | None) -> str | None:
    if not raw_doc:
        return None

    lines = inspect.cleandoc(raw_doc).splitlines()
    summary: list[str] = []
    params: list[tuple[str, str]] = []
    optionals: list[tuple[str, str]] = []
    returns: list[str] = []
    raises: list[str] = []
    notes: list[str] = []
    examples: list[str] = []
    active: tuple[str, int] | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            active = None
            continue

        match = _DOC_TAG_PATTERN.match(stripped)
        if match:
            tag = match.group("tag").lower()
            body = (match.group("body") or "").strip()

            if tag == "parameter":
                if body:
                    parts = body.split(None, 1)
                    param_name = parts[0]
                    param_desc = parts[1] if len(parts) > 1 else ""
                else:
                    param_name = "param"
                    param_desc = ""
                params.append((param_name, param_desc))
                active = ("parameter", len(params) - 1)
            elif tag == "optional":
                if body:
                    parts = body.split(None, 1)
                    param_name = parts[0]
                    param_desc = parts[1] if len(parts) > 1 else ""
                else:
                    param_name = "param"
                    param_desc = ""
                optionals.append((param_name, param_desc))
                active = ("optional", len(params) - 1)
            elif tag in {"return", "returns"}:
                returns.append(body)
                active = ("returns", len(returns) - 1)
            elif tag in {"raise", "raises", "throws"}:
                raises.append(body)
                active = ("raises", len(raises) - 1)
            elif tag == "example":
                examples.append(body)
                active = ("examples", len(examples) - 1)
            else:
                notes.append(f"@{tag} {body}".strip())
                active = ("notes", len(notes) - 1)
            continue

        if active is None:
            _append_text(summary, stripped)
            continue

        section, index = active
        if section == "param":
            name, desc = params[index]
            params[index] = (name, f"{desc} {stripped}".strip())
        if section == "optional":
            name, desc = optionals[index]
            optionals[index] = (name, f"{desc} {stripped}".strip())
        elif section == "returns":
            _extend_last(returns, stripped)
        elif section == "raises":
            _extend_last(raises, stripped)
        elif section == "examples":
            _extend_last(examples, stripped)
        else:
            _extend_last(notes, stripped)

    parts: list[str] = []
    if summary:
        parts.append(" ".join(summary))
    if params or optionals:
        parts.append(
            "**Parameters**\n"
            + "\n".join(
                f"- `{name}`: {desc}" if desc else f"- `{name}`"
                for name, desc in params
            )
            + "\n".join(
                f"- `{name}`?: {desc}" if desc else f"- `{name}`"
                for name, desc in optionals
            )
        )
    if returns:
        parts.append("**Returns**\n" + "\n".join(f"- {item}" for item in returns))
    if raises:
        parts.append("**Raises**\n" + "\n".join(f"- {item}" for item in raises))
    if examples:
        parts.append("**Examples**\n" + "\n".join(f"- `{item}`" for item in examples))
    if notes:
        parts.append("**Notes**\n" + "\n".join(f"- {item}" for item in notes))

    return "\n\n".join(part for part in parts if part).strip() or None


@lru_cache(maxsize=1)
def get_function_catalog() -> tuple[FunctionInfo, ...]:
    providers: list[BxeExtensionBase] = [
        BuiltinExtension(),
        BrainGlobalExtension(),
        BrainUserExtension(),
        DiscordStubExtension(),
    ]

    all_infos: dict[str, FunctionInfo] = {}
    for provider in providers:
        docs_by_attr_name = get_docs(type(provider))
        for info in _iter_extension_functions(provider, docs_by_attr_name):
            all_infos[info.name] = info

    return tuple(sorted(all_infos.values(), key=lambda i: i.name))
