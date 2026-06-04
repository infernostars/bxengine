from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from bxengine.docs import get_docs
from bxengine.runtime.extensions.BxeExtension import BxeExtensionBase
from bxengine.runtime.extensions.builtin import create_default_builtin_extensions
from bxengine.runtime.extensions.discord_stub import (
    BrainGlobalExtension,
    BrainUserExtension,
    DiscordStubExtension,
)


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    primary_name: str
    aliases: tuple[str, ...]
    signature: str
    documentation_markdown: str | None
    category: str
    is_alias: bool
    alias_of: str | None
    is_node_transformer: bool


def _iter_extension_functions(ext: type[BxeExtensionBase]) -> list[FunctionInfo]:
    infos: list[FunctionInfo] = []
    for doc in get_docs(ext).values():
        infos.append(
            FunctionInfo(
                name=doc.name,
                primary_name=doc.primary_name,
                aliases=doc.aliases,
                signature=doc.signature,
                documentation_markdown=doc.documentation_markdown,
                category=doc.category,
                is_alias=doc.is_alias,
                alias_of=doc.alias_of,
                is_node_transformer=doc.is_node_transformer,
            )
        )
    return infos


@lru_cache(maxsize=1)
def get_function_catalog() -> tuple[FunctionInfo, ...]:
    providers: list[BxeExtensionBase] = [
        *create_default_builtin_extensions(),
        BrainGlobalExtension(),
        BrainUserExtension(),
        DiscordStubExtension(),
    ]

    all_infos: dict[str, FunctionInfo] = {}
    for provider in providers:
        for info in _iter_extension_functions(type(provider)):
            all_infos[info.name] = info

    return tuple(sorted(all_infos.values(), key=lambda i: (i.category, i.is_alias, i.name)))
