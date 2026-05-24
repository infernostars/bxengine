from __future__ import annotations

import inspect
from dataclasses import dataclass
from functools import lru_cache

from bxengine.runtime.extensions.BxeExtension import BxeExtensionBase
from bxengine.runtime.extensions.BxeExtension import GlobalVariableBppExtension
from bxengine.runtime.extensions.builtin import BuiltinExtension
from bxengine.runtime.extensions.discord_stub import DiscordStubExtension


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    signature: str
    detail: str
    is_node_transformer: bool


def _iter_extension_functions(ext: BxeExtensionBase) -> list[FunctionInfo]:
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
        signature = _build_signature(attr, primary, is_node_transformer)
        detail = "Special form (node-transformer)" if is_node_transformer else "Builtin function"

        seen_names: set[str] = set()
        for name in (primary, *aliases):
            if name in seen_names:
                continue
            seen_names.add(name)
            infos.append(
                FunctionInfo(
                    name=name,
                    signature=signature.replace(primary, name, 1),
                    detail=detail,
                    is_node_transformer=is_node_transformer,
                )
            )
    return infos


def _build_signature(func: object, display_name: str, is_node_transformer: bool) -> str:
    if is_node_transformer:
        return f"[{display_name} ...]"

    sig = inspect.signature(func)
    arg_names = [
        p.name
        for p in sig.parameters.values()
        if p.name != "context"
    ]
    if not arg_names:
        return f"[{display_name}]"
    return f"[{display_name} {' '.join(arg_names)}]"


@lru_cache(maxsize=1)
def get_function_catalog() -> tuple[FunctionInfo, ...]:
    providers: list[BxeExtensionBase] = [
        BuiltinExtension(),
        GlobalVariableBppExtension(),
        DiscordStubExtension(),
    ]

    all_infos: dict[str, FunctionInfo] = {}
    for provider in providers:
        for info in _iter_extension_functions(provider):
            all_infos[info.name] = info

    return tuple(sorted(all_infos.values(), key=lambda i: i.name))
