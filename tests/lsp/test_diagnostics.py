from bxengine.lsp.diagnostics import (
    DIAGNOSTIC_WARNING,
    collect_diagnostics,
    offset_to_position,
    span_to_range,
)
from bxengine.spans import SpanData


def test_offset_to_position_utf16_units():
    source = "a😀b\nz"
    # "a😀" is 3 UTF-16 code units (1 + 2).
    pos = offset_to_position(source, 2)
    assert pos.line == 0
    assert pos.character == 3


def test_span_to_range_zero_width_extends_one_character():
    source = "abc"
    span = SpanData(cursor_start=1, cursor_end=1, original_string=source)
    lsp_range = span_to_range(source, span)
    assert lsp_range.start.line == 0
    assert lsp_range.start.character == 1
    assert lsp_range.end.line == 0
    assert lsp_range.end.character == 2


def test_collect_diagnostics_reports_parser_error():
    diagnostics = collect_diagnostics("[]")
    assert len(diagnostics) == 1
    assert "empty" in diagnostics[0].message.lower()


def test_collect_diagnostics_valid_program():
    diagnostics = collect_diagnostics('[CONCAT "a" "b"]')
    assert diagnostics == []


def test_collect_diagnostics_warns_on_extra_closing_bracket():
    diagnostics = collect_diagnostics("hello ]")
    assert len(diagnostics) == 1
    assert diagnostics[0].severity == DIAGNOSTIC_WARNING
    assert "ignored" in diagnostics[0].message.lower()


def test_collect_diagnostics_warns_on_unclosed_open_bracket():
    diagnostics = collect_diagnostics("[CONCAT 1")
    assert len(diagnostics) == 1
    assert diagnostics[0].severity == DIAGNOSTIC_WARNING
    assert "auto-closed" in diagnostics[0].message.lower()


def test_collect_diagnostics_ignores_escaped_bracket_in_text():
    diagnostics = collect_diagnostics(r"hello \]")
    assert diagnostics == []


def test_collect_diagnostics_warns_on_unterminated_quote():
    diagnostics = collect_diagnostics('[CONCAT "oops]')
    assert len(diagnostics) == 2
    assert all(d.severity == DIAGNOSTIC_WARNING for d in diagnostics)
    messages = [d.message.lower() for d in diagnostics]
    assert any("unterminated" in m for m in messages)
    assert any("auto-closed" in m for m in messages)
