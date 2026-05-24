from bxengine.tokenizer.tokenize import Tokenizer, TokenizationResult
from bxengine.parsing.parser import Parser, ParsingResult
from bxengine.parsing.nodes import Nodes


def parse(code: str):
    tok = Tokenizer.tokenize(code)
    assert isinstance(tok, TokenizationResult.Success)
    res = Parser.parse(code, tok.tokens)
    assert isinstance(res, ParsingResult.Success), f"Parse error: {res.message}"
    return res.nodes


def parse_error(code: str) -> str:
    tok = Tokenizer.tokenize(code)
    assert isinstance(tok, TokenizationResult.Success)
    res = Parser.parse(code, tok.tokens)
    assert isinstance(res, ParsingResult.Error)
    return res.message


def test_outer_text():
    nodes = parse("hello world")
    assert len(nodes) == 1
    assert isinstance(nodes[0], Nodes.OuterText)
    assert nodes[0].value == "hello world"


def test_function_call():
    nodes = parse("[FUNC]")
    assert len(nodes) == 1
    assert isinstance(nodes[0], Nodes.Function)
    assert nodes[0].name == "FUNC"
    assert nodes[0].arguments == []


def test_function_with_args():
    nodes = parse('[FUNC 1 "hello" bare]')
    func = nodes[0]
    assert isinstance(func, Nodes.Function)
    assert len(func.arguments) == 3
    assert isinstance(func.arguments[0], Nodes.Number)
    assert isinstance(func.arguments[1], Nodes.StringNode)
    assert isinstance(func.arguments[2], Nodes.StringNode)


def test_nested_functions():
    nodes = parse("[A [B 1] [C 2]]")
    assert len(nodes) == 1
    outer = nodes[0]
    assert isinstance(outer, Nodes.Function)
    assert outer.name == "A"
    assert len(outer.arguments) == 2
    assert isinstance(outer.arguments[0], Nodes.Function)
    assert outer.arguments[0].name == "B"
    assert isinstance(outer.arguments[1], Nodes.Function)
    assert outer.arguments[1].name == "C"


def test_mixed_text_and_functions():
    nodes = parse("Hello [CONCAT \"world\" \"!\"] end")
    assert len(nodes) == 3
    assert isinstance(nodes[0], Nodes.OuterText)
    assert isinstance(nodes[1], Nodes.Function)
    assert isinstance(nodes[2], Nodes.OuterText)


def test_empty_brackets_error():
    msg = parse_error("[]")
    assert "empty" in msg.lower()


def test_unclosed_bracket_auto_closed():
    # BPPCOMPAT: unclosed brackets at EOF are auto-closed
    tok = Tokenizer.tokenize("[FUNC")
    assert isinstance(tok, TokenizationResult.Success)
    res = Parser.parse("[FUNC", tok.tokens)
    assert isinstance(res, ParsingResult.Success)
    nodes = res.nodes
    assert len(nodes) == 1
    assert isinstance(nodes[0], Nodes.Function)
    assert nodes[0].name == "FUNC"
    assert len(res.warnings) == 1
    assert "auto-closed" in res.warnings[0].message.lower()


def test_multiple_top_level_functions():
    nodes = parse("[A] [B] [C]")
    funcs = [n for n in nodes if isinstance(n, Nodes.Function)]
    assert len(funcs) == 3
    assert funcs[0].name == "A"
    assert funcs[1].name == "B"
    assert funcs[2].name == "C"
