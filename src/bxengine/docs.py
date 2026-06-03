from __future__ import annotations

import inspect
import re
from dataclasses import dataclass

from bxengine.runtime.extensions import BxeExtensionBase


_DOC_TAG_PATTERN = re.compile(r"^@(?P<tag>[a-zA-Z][a-zA-Z0-9_-]*)\b(?:\s+(?P<body>.*))?$")


@dataclass(frozen=True)
class ParsedDocstring:
    summary: tuple[str, ...]
    parameters: tuple[tuple[str, str], ...]
    optional_parameters: tuple[tuple[str, str], ...]
    returns: tuple[str, ...]
    raises: tuple[str, ...]
    examples: tuple[str, ...]
    notes: tuple[str, ...]
    category: str | None


@dataclass(frozen=True)
class FunctionDoc:
    name: str
    primary_name: str
    aliases: tuple[str, ...]
    signature: str
    raw_doc: str | None
    documentation_markdown: str | None
    category: str
    is_alias: bool
    alias_of: str | None
    is_node_transformer: bool


def get_docs(ext: type[BxeExtensionBase]) -> dict[str, FunctionDoc]:
    ext_docs: dict[str, FunctionDoc] = {}
    default_category = str(
        getattr(ext, "_bpp_function_category", _default_category_for_extension(ext))
    )

    for attr_name in dir(ext):
        if attr_name.startswith("_"):
            continue
        attr = getattr(ext, attr_name, None)
        if attr is None:
            continue
        if callable(attr) and getattr(attr, "_is_bpp_function", False):
            primary = _normalize_name(getattr(attr, "_bpp_function_name", attr_name))
            aliases = tuple(
                _normalize_name(alias)
                for alias in getattr(attr, "_bpp_function_aliases", ())
                if str(alias) != ""
            )
            raw_doc = inspect.getdoc(attr)
            parsed = parse_docstring(raw_doc)
            category = (
                getattr(attr, "_bpp_function_category", None)
                or parsed.category
                or default_category
            )
            category = _clean_category(str(category))
            is_node_transformer = bool(getattr(attr, "_node_transformer", False))

            for name in _dedupe_names((primary, *aliases)):
                alias_of = None if name == primary else primary
                signature = build_signature_from_docstring(name, raw_doc)
                markdown = format_docstring_markdown(
                    raw_doc,
                    primary_name=primary,
                    current_name=name,
                    aliases=aliases,
                    category=category,
                )
                ext_docs[name] = FunctionDoc(
                    name=name,
                    primary_name=primary,
                    aliases=aliases,
                    signature=signature,
                    raw_doc=raw_doc,
                    documentation_markdown=markdown,
                    category=category,
                    is_alias=alias_of is not None,
                    alias_of=alias_of,
                    is_node_transformer=is_node_transformer,
                )
    return ext_docs


def parse_docstring(docstring: str | None) -> ParsedDocstring:
    summary: list[str] = []
    params: list[tuple[str, str]] = []
    optionals: list[tuple[str, str]] = []
    returns: list[str] = []
    raises: list[str] = []
    notes: list[str] = []
    examples: list[str] = []
    category: str | None = None
    active: tuple[str, int] | None = None

    if not docstring:
        return ParsedDocstring((), (), (), (), (), (), (), None)

    for line in inspect.cleandoc(docstring).splitlines():
        stripped = line.strip()
        if not stripped:
            active = None
            continue

        match = _DOC_TAG_PATTERN.match(stripped)
        if match:
            tag = match.group("tag").lower()
            body = (match.group("body") or "").strip()

            if tag == "parameter":
                params.append(_split_named_doc_body(body))
                active = ("parameter", len(params) - 1)
            elif tag == "optional":
                optionals.append(_split_named_doc_body(body))
                active = ("optional", len(optionals) - 1)
            elif tag in {"return", "returns"}:
                returns.append(body)
                active = ("returns", len(returns) - 1)
            elif tag in {"raise", "raises", "throws"}:
                raises.append(body)
                active = ("raises", len(raises) - 1)
            elif tag == "example":
                examples.append(body)
                active = ("examples", len(examples) - 1)
            elif tag == "category":
                category = _clean_category(body) if body else None
                active = None
            else:
                notes.append(f"@{tag} {body}".strip())
                active = ("notes", len(notes) - 1)
            continue

        if active is None:
            _append_text(summary, stripped)
            continue

        section, index = active
        if section == "parameter":
            name, desc = params[index]
            params[index] = (name, f"{desc} {stripped}".strip())
        elif section == "optional":
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

    return ParsedDocstring(
        summary=tuple(summary),
        parameters=tuple(params),
        optional_parameters=tuple(optionals),
        returns=tuple(returns),
        raises=tuple(raises),
        examples=tuple(examples),
        notes=tuple(notes),
        category=category,
    )


def build_signature_from_docstring(function_name: str, docstring: str | None) -> str:
    parsed = parse_docstring(docstring)
    required = [name for name, _desc in parsed.parameters]
    optional: list[str] = []

    for name, _desc in parsed.optional_parameters:
        if name.endswith("?") or name == "...":
            optional.append(name)
        else:
            optional.append(f"{name}?")

    arg_names = [*required, *optional]
    if not arg_names:
        return f"[{function_name}]"
    return f"[{function_name} {' '.join(arg_names)}]"


def format_docstring_markdown(
    raw_doc: str | None,
    *,
    primary_name: str | None = None,
    current_name: str | None = None,
    aliases: tuple[str, ...] = (),
    category: str | None = None,
) -> str | None:
    parsed = parse_docstring(raw_doc)
    parts: list[str] = []

    if category:
        parts.append(f"**Category**\n{category}")

    primary = primary_name.upper() if primary_name else None
    current = current_name.upper() if current_name else None
    if primary and current and current != primary:
        parts.append(f"**Alias**\n`{current}` is an alias for `{primary}`.")

    visible_aliases = tuple(
        alias
        for alias in aliases
        if (not primary or alias != primary) and (not current or alias != current)
    )
    if visible_aliases:
        parts.append("**Aliases**\n" + ", ".join(f"`{alias}`" for alias in visible_aliases))

    if parsed.summary:
        parts.append("\n".join(parsed.summary))
    if parsed.parameters or parsed.optional_parameters:
        param_lines = [
            f"- `{name}`: {desc}" if desc else f"- `{name}`"
            for name, desc in parsed.parameters
        ]
        optional_lines = [
            f"- `{name}`?: {desc}" if desc else f"- `{name}`"
            for name, desc in parsed.optional_parameters
        ]
        parts.append("**Parameters**\n" + "\n".join([*param_lines, *optional_lines]))
    if parsed.returns:
        parts.append("**Returns**\n" + "\n".join(f"- {item}" for item in parsed.returns))
    if parsed.raises:
        parts.append("**Raises**\n" + "\n".join(f"- {item}" for item in parsed.raises))
    if parsed.examples:
        parts.append("**Examples**\n" + "\n".join(f"- `{item}`" for item in parsed.examples))
    if parsed.notes:
        parts.append("**Notes**\n" + "\n".join(f"- {item}" for item in parsed.notes))

    return "\n\n".join(part for part in parts if part).strip() or None


def _normalize_name(value: object) -> str:
    return str(value).upper()


def _dedupe_names(names: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return tuple(out)


def _clean_category(category: str) -> str:
    return " ".join(category.strip().split()) or "General"


def _split_named_doc_body(body: str) -> tuple[str, str]:
    if not body:
        return ("param", "")
    parts = body.split(None, 1)
    param_name = parts[0]
    param_desc = parts[1] if len(parts) > 1 else ""
    return (param_name, param_desc)


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


def _default_category_for_extension(ext: type[BxeExtensionBase]) -> str:
    name = ext.__name__
    if name.endswith("Extension"):
        name = name[: -len("Extension")]
    return re.sub(r"(?<!^)(?=[A-Z])", " ", name)
