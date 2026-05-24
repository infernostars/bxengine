from bxengine.lsp.functions import get_function_catalog
from bxengine.lsp.server import (
    _declared_macros,
    completion_prefix_at,
    completion_span_at,
    position_to_offset,
    word_at_offset,
)


def test_position_to_offset_uses_utf16_columns():
    source = "a😀b\n"
    # line 0, utf16 char 3 should point to "b"
    assert position_to_offset(source, line=0, character_utf16=3) == 2


def test_word_at_offset_extracts_symbol():
    source = "[CONCAT \"x\" \"y\"]"
    symbol, start, end = word_at_offset(source, 2)
    assert symbol == "CONCAT"
    assert source[start:end] == "CONCAT"


def test_word_at_offset_handles_macro_name():
    source = "[@HELLO]"
    symbol, _, _ = word_at_offset(source, 2)
    assert symbol == "@HELLO"


def test_function_catalog_contains_core_functions():
    catalog = get_function_catalog()
    names = {entry.name for entry in catalog}
    assert "CONCAT" in names
    assert "IF" in names
    assert "GLOBAL" in names
    randint = next(entry for entry in catalog if entry.name == "RANDINT")
    assert randint.documentation is not None
    assert "Generates a random integer" in randint.documentation


def test_completion_prefix_at():
    source = "[@hel"
    assert completion_prefix_at(source, len(source)) == "@hel"


def test_completion_span_at():
    source = "[@hel"
    assert completion_span_at(source, len(source)) == (1, 5)


def test_declared_macros_extracts_static_names():
    source = '[MACRO "foo" [ARRAY] "ok"] [MACRO "@Bar" [ARRAY] "ok"]'
    assert _declared_macros(source) == ("@FOO", "@BAR")
