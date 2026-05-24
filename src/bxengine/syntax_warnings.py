from __future__ import annotations

from dataclasses import dataclass

from bxengine.spans import SpanData


@dataclass(frozen=True)
class BxeSyntaxWarning:
    message: str
    range: SpanData
    source: str = "bxengine-compat"

