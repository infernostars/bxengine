from bxengine.tokenizer.tokenize import Tokenizer, TokenizationResult
from bxengine.tokenizer.tokens import Tokens


def tokenize(code: str) -> list:
    res = Tokenizer.tokenize(code)
    assert isinstance(res, TokenizationResult.Success)
    return res.tokens


def token_types(tokens: list) -> list[str]:
    return [type(t).__name__ for t in tokens]


def test_plain_text():
    tokens = tokenize("hello world")
    types = token_types(tokens)
    assert "OuterString" in types
    assert "EndOfFile" in types


def test_brackets():
    tokens = tokenize("[FUNC]")
    types = token_types(tokens)
    assert types[0] == "OpenBracket"
    assert types[1] == "UnquotedString"
    assert types[2] == "CloseBracket"


def test_nested_brackets():
    tokens = tokenize("[A [B]]")
    opens = sum(1 for t in tokens if isinstance(t, Tokens.OpenBracket))
    closes = sum(1 for t in tokens if isinstance(t, Tokens.CloseBracket))
    assert opens == 2
    assert closes == 2


def test_quoted_string():
    tokens = tokenize('[FUNC "hello world"]')
    quoted = [t for t in tokens if isinstance(t, Tokens.QuotedString)]
    assert len(quoted) == 1
    assert quoted[0].value == "hello world"


def test_number_token():
    tokens = tokenize("[FUNC 42 3.14 -7]")
    numbers = [t for t in tokens if isinstance(t, Tokens.Number)]
    assert len(numbers) == 3
    assert numbers[0].value == "42"
    assert numbers[1].value == "3.14"
    assert numbers[2].value == "-7"


def test_escaped_quotes():
    tokens = tokenize(r'[FUNC "hello \"world\""]')
    quoted = [t for t in tokens if isinstance(t, Tokens.QuotedString)]
    assert len(quoted) == 1
    assert quoted[0].value == 'hello "world"'


def test_extra_closing_brackets_absorbed():
    tokens = tokenize("A]]]]]]]]")
    types = token_types(tokens)
    assert "OuterString" in types
    assert "CloseBracket" not in types


def test_outer_string_merging():
    tokens = tokenize("hello [A] world")
    outers = [t for t in tokens if isinstance(t, Tokens.OuterString)]
    assert len(outers) == 2
    assert outers[0].value == "hello "
    assert outers[1].value == " world"


def test_unquoted_backslash_escapes_space():
    tokens = tokenize(r"[FN \ text]")
    unquoted = [t for t in tokens if isinstance(t, Tokens.UnquotedString)]
    assert len(unquoted) == 2
    assert unquoted[0].value == "FN"
    assert unquoted[1].value == " text"


def test_unquoted_backslash_escapes_close_bracket():
    tokens = tokenize(r"[FN hello\]]")
    unquoted = [t for t in tokens if isinstance(t, Tokens.UnquotedString)]
    assert len(unquoted) == 2
    assert unquoted[0].value == "FN"
    assert unquoted[1].value == "hello]"


def test_outer_string_dangling_backslash_is_swallowed():
    tokens = tokenize("abc\\")
    outers = [t for t in tokens if isinstance(t, Tokens.OuterString)]
    assert len(outers) == 1
    assert outers[0].value == "abc"


def test_warns_on_extra_closing_bracket():
    res = Tokenizer.tokenize("hello ]")
    assert isinstance(res, TokenizationResult.Success)
    assert len(res.warnings) == 1
    assert "ignored" in res.warnings[0].message.lower()


def test_warns_on_unterminated_quote():
    res = Tokenizer.tokenize('[CONCAT "oops]')
    assert isinstance(res, TokenizationResult.Success)
    assert len(res.warnings) == 1
    assert "unterminated" in res.warnings[0].message.lower()
