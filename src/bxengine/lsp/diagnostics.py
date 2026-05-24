from __future__ import annotations

from dataclasses import dataclass

from bxengine.parsing.parser import Parser, ParsingResult
from bxengine.spans import SpanData
from bxengine.syntax_warnings import BxeSyntaxWarning
from bxengine.tokenizer.tokenize import TokenizationResult, Tokenizer


@dataclass(frozen=True)
class Position:
    line: int
    character: int


@dataclass(frozen=True)
class Range:
    start: Position
    end: Position


@dataclass(frozen=True)
class Diagnostic:
    message: str
    range: Range
    severity: int = 1
    source: str = "bxengine"

DIAGNOSTIC_ERROR = 1
DIAGNOSTIC_WARNING = 2


def collect_diagnostics(source: str) -> list[Diagnostic]:
    tokenized = Tokenizer.tokenize(source)
    if isinstance(tokenized, TokenizationResult.Error):
        return [
            Diagnostic(
                message=tokenized.message,
                range=span_to_range(source, tokenized.range),
                severity=DIAGNOSTIC_ERROR,
            ),
        ]

    diagnostics = _warnings_to_diagnostics(source, tokenized.warnings)

    parsed = Parser.parse(source, tokenized.tokens)
    if isinstance(parsed, ParsingResult.Error):
        return diagnostics + [
            Diagnostic(
                message=parsed.message,
                range=span_to_range(source, parsed.range),
                severity=DIAGNOSTIC_ERROR,
            ),
        ] + _warnings_to_diagnostics(source, parsed.warnings)

    return diagnostics + _warnings_to_diagnostics(source, parsed.warnings)


def _warnings_to_diagnostics(source: str, warnings: tuple[BxeSyntaxWarning, ...]) -> list[Diagnostic]:
    return [
        Diagnostic(
            message=warning.message,
            range=span_to_range(source, warning.range),
            severity=DIAGNOSTIC_WARNING,
            source=warning.source,
        )
        for warning in warnings
    ]


def span_to_range(source: str, span: SpanData) -> Range:
    length = len(source)
    start_offset = _clamp(span.cursor_start, 0, length)
    end_offset = _clamp(span.cursor_end, 0, length)

    if end_offset < start_offset:
        end_offset = start_offset

    # Zero-width errors are hard to see in editors; highlight one character when possible.
    if start_offset == end_offset and end_offset < length:
        end_offset += 1

    return Range(
        start=offset_to_position(source, start_offset),
        end=offset_to_position(source, end_offset),
    )


def offset_to_position(source: str, offset: int) -> Position:
    offset = _clamp(offset, 0, len(source))

    line = source.count("\n", 0, offset)
    line_start = source.rfind("\n", 0, offset)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1

    line_prefix = source[line_start:offset]
    return Position(line=line, character=_utf16_units(line_prefix))


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))
