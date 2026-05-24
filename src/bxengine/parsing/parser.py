from bxengine.parsing.nodes import Node, Nodes
from typing import List, Tuple, Sequence
from bxengine.tokenizer.tokens import Token, Tokens
from bxengine.spans import SpanData
from bxengine.syntax_warnings import BxeSyntaxWarning
from dataclasses import dataclass
import functools


class ParsingResult:
    @dataclass(frozen=True)
    class Error:
        message: str
        range: SpanData
        warnings: Tuple[BxeSyntaxWarning, ...] = ()

    @dataclass(frozen=True)
    class Success:
        nodes: List[Node]
        warnings: Tuple[BxeSyntaxWarning, ...] = ()

        def pretty(self) -> str:
            string = f"{len(self.nodes)} nodes:"
            for node in self.nodes:
                string += "\n"
                string += str(node)

            return string


class Parser:
    _identity_cache: dict[int, tuple[str, Sequence[Token], ParsingResult.Success | ParsingResult.Error]] = {}
    _identity_cache_limit: int = 512

    def __init__(self):
        self.nesting_level: int = 0
        self.nesting_token_indexes: List[int] = []
        self.contents: str = ""
        self.token_list: Sequence[Token] = ()
        self.is_function_declaration: bool = False
        self.index: int = 0
        self.warnings: list[BxeSyntaxWarning] = []

    @staticmethod
    def parse(contents: str, token_list: Sequence[Token]) -> ParsingResult.Success | ParsingResult.Error:
        # Fast path for repeated runs with the same token list object (common when
        # tokenization cache hits across multiple executions in one process).
        cache_key = id(token_list)
        cached = Parser._identity_cache.get(cache_key)
        if cached is not None:
            cached_contents, cached_tokens, cached_result = cached
            if cached_contents == contents and cached_tokens is token_list:
                return cached_result

        result = Parser._parse_cache(contents, tuple(token_list))

        if len(Parser._identity_cache) >= Parser._identity_cache_limit:
            Parser._identity_cache.clear()
        Parser._identity_cache[cache_key] = (contents, token_list, result)
        return result

    @staticmethod
    @functools.lru_cache(maxsize=128, typed=False)
    def _parse_cache(contents: str, token_list: Tuple[Token]) -> ParsingResult.Success | ParsingResult.Error:
        parser = Parser()
        parser.contents = contents
        parser.token_list = token_list
        parser.nesting_level = 0
        parser.nesting_token_indexes = []
        parser.index = 0
        parser.is_function_declaration = False

        return parser._parse_loop()

    def _parse_loop(self) -> ParsingResult.Success | ParsingResult.Error:
        node_list = []
        while True:
            node = self._parse_once()

            if isinstance(node, Nodes.Error):
                return ParsingResult.Error(
                    message=node.message,
                    range=node.range,
                    warnings=tuple(self.warnings),
                )
            elif isinstance(node, Nodes._Complete):
                return ParsingResult.Success(
                    nodes=node_list,
                    warnings=tuple(self.warnings),
                )

            node_list.append(node)

    def _parse_once(self) -> Node:
        return self._parse_inner()

    def _parse_inner(self) -> Node:
        token = self.token_list[self.index]

        if isinstance(token, Tokens.EndOfFile):
            if self.nesting_level > 0:
                bracket_index = self.nesting_token_indexes[-1]
                return Nodes.Error("Unclosed bracket.", self.token_list[bracket_index].range)
            else:
                return Nodes._Complete(token.range)

        if isinstance(token, Tokens.Error):
            self.index += 1
            return Nodes.Error(token.message, token.range)

        if self.nesting_level == 0:
            match token:
                case Tokens.OuterString():
                    self.index += 1
                    return Nodes.OuterText(token.value, token.range)
                case Tokens.OpenBracket():
                    return self._parse_function()
                case _:
                    self.index += 1
                    text = self.contents[token.range.cursor_start:token.range.cursor_end]
                    return Nodes.Error(
                        f"Unexpected token '{text}' at top level. Only text and function calls are allowed.",
                        token.range
                    )
        else:
            self.index += 1
            return Nodes.Error("Parser bug: `_parse_inner` called while (somehow??) nested. Please report this!",
                               token.range)

    def _parse_function(self) -> Node:
        open_bracket = self.token_list[self.index]  # this is always an OpenBracket
        self.index += 1  # consume

        self.nesting_level += 1
        self.nesting_token_indexes.append(self.index - 1)

        if self.index >= len(self.token_list):
            self.nesting_level -= 1
            self.nesting_token_indexes.pop()
            # Equivalent to empty brackets `[]` due to auto-close.
            return Nodes.Error("Function call cannot be empty `[]`.", self.create_span(open_bracket, open_bracket))

        name_token = self.token_list[self.index]

        # BPPCOMPAT: Close on EndOfFile just like a CloseBracket
        if isinstance(name_token, (Tokens.CloseBracket, Tokens.EndOfFile)):
            if isinstance(name_token, Tokens.CloseBracket):
                self.index += 1
            self.nesting_level -= 1
            self.nesting_token_indexes.pop()
            return Nodes.Error("Function call cannot be empty `[]`.", self.create_span(open_bracket, name_token))

        if not isinstance(name_token, Tokens.UnquotedString):
            self.nesting_level -= 1
            self.nesting_token_indexes.pop()
            return Nodes.Error("Function name must be an unquoted string.", name_token.range)

        self.index += 1  # consume

        function_name = name_token.value
        arguments = []

        while True:
            if self.index >= len(self.token_list):
                self.nesting_level -= 1
                self.nesting_token_indexes.pop()
                last_token = self.token_list[-1] if self.token_list else open_bracket
                self._warn(
                    message=(
                        "Unclosed '[' is auto-closed at end of file (compat behavior). "
                        "Add a matching ']'."
                    ),
                    span=open_bracket.range,
                )
                return Nodes.Function(function_name, arguments, self.create_span(open_bracket, last_token))

            current = self.token_list[self.index]

            # BPPCOMPAT: Close on EndOfFile just like a CloseBracket
            if isinstance(current, (Tokens.CloseBracket, Tokens.EndOfFile)):
                if isinstance(current, Tokens.CloseBracket):
                    self.index += 1
                else:
                    self._warn(
                        message=(
                            "Unclosed '[' is auto-closed at end of file (compat behavior). "
                            "Add a matching ']'."
                        ),
                        span=open_bracket.range,
                    )
                self.nesting_level -= 1
                self.nesting_token_indexes.pop()
                return Nodes.Function(function_name, arguments, self.create_span(open_bracket, current))

            argument = self._parse_expression()
            if isinstance(argument, Nodes.Error):
                return argument

            arguments.append(argument)

    def _parse_expression(self) -> Node:
        token = self.token_list[self.index]

        if isinstance(token, Tokens.Error):
            self.index += 1
            return Nodes.Error(token.message, token.range)

        match token:
            case Tokens.OpenBracket():
                return self._parse_function()
            case Tokens.Number():
                self.index += 1
                return Nodes.Number(token.value, token.range)
            case Tokens.QuotedString():
                self.index += 1
                return Nodes.StringNode(token.value, token.range)
            case Tokens.UnquotedString():
                self.index += 1
                return Nodes.StringNode(token.value, token.range)
            case Tokens.EndOfFile():
                bracket_index = self.nesting_token_indexes[-1]
                return Nodes.Error("Parser bug: `_parse_expression` called and hit end of file (should be impossible...!)", self.token_list[bracket_index].range)
            case _:
                self.index += 1
                return Nodes.Error("Unexpected token while parsing arguments.", token.range)

    def create_span(self, start: Token, end: Token) -> SpanData:
        start_int = start.range.cursor_start
        end_int = end.range.cursor_end
        return SpanData(start_int, end_int, self.contents)

    def _warn(self, message: str, span: SpanData) -> None:
        self.warnings.append(BxeSyntaxWarning(message=message, range=span))
