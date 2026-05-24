from dataclasses import dataclass
from typing import Optional, Tuple

from .tokens import Token, Tokens
from .stringreader import StringReader, BxeSyntaxException
from bxengine.spans import SpanData
from bxengine.syntax_warnings import BxeSyntaxWarning
import functools


class TokenizationResult:
    @dataclass(frozen=True)
    class Error:
        message: str
        range: SpanData

    @dataclass(frozen=True)
    class Success:
        tokens: Tuple[Token, ...]
        warnings: Tuple[BxeSyntaxWarning, ...] = ()

        def pretty(self) -> str:
            string = f"{len(self.tokens)} tokens:"
            for token in self.tokens:
                string += "\n"
                string += str(token)

            return string


class Tokenizer:
    exceptions: str = "[]"

    def __init__(self, reader: StringReader):
        self.file_name: str = ""
        self.reader: StringReader = reader
        self.nesting_level: int = 0
        self.warnings: list[BxeSyntaxWarning] = []

    @staticmethod
    @functools.lru_cache(maxsize=128, typed=False)
    def tokenize(file_content: str) -> TokenizationResult.Success | TokenizationResult.Error:
        tokenizer = Tokenizer(StringReader(file_content, Tokenizer.exceptions))
        return tokenizer._tokenize_loop()

    def _tokenize_loop(self) -> TokenizationResult.Success | TokenizationResult.Error:
        tokens = []
        while True:
            token = self._tokenize_once()

            if isinstance(token, Tokens.Error):
                return TokenizationResult.Error(token.message, token.range)

            if isinstance(token, Tokens.EndOfFile):
                # Padding end-of-file tokens
                for _ in range(5):
                    tokens.append(Tokens.EndOfFile(self.create_span()))
                return TokenizationResult.Success(
                    tokens=tuple(tokens),
                    warnings=tuple(self.warnings),
                )

            if isinstance(token, Tokens.OuterString):
                if tokens and isinstance(tokens[-1], Tokens.OuterString):
                    # Merge sequential OuterStrings. This safely bridges spans across thrown-away brackets.
                    prev_token = tokens.pop()
                    merged_value = prev_token.value + token.value
                    merged_span = SpanData(
                        prev_token.range.cursor_start,
                        token.range.cursor_end,
                        self.reader.get_string()
                    )
                    tokens.append(Tokens.OuterString(merged_value, merged_span))
                    continue
                elif token.value == "":
                    # Discard standalone empty outer strings
                    continue

            tokens.append(token)

    def _tokenize_once(self) -> Token:
        try:
            return self._tokenize_inner()
        except BxeSyntaxException as e:
            return Tokens.Error(str(e), self.create_span())
        except IndexError:
            return Tokens.EndOfFile(self.create_span())

    def _tokenize_inner(self) -> Token:
        peeked = self.reader.peek()

        if self.nesting_level == 0 and peeked not in self.exceptions:
            start = self.reader.get_cursor()
            return Tokens.OuterString(
                self.reader.read_string_until_excepting_character(),
                self.create_span(start)
            )

        self.reader.skip_whitespace()
        start = self.reader.get_cursor()

        match self.reader.peek():
            case '"' | '“' | '”':
                quoted, terminated = self.reader.read_quoted_string_with_status()
                if not terminated:
                    self._warn(
                        message=(
                            "Unterminated quoted string is accepted as-is (compat behavior). Add a quote."
                        ),
                        span=self.create_span(start, start + 1),
                    )
                return Tokens.QuotedString(quoted, self.create_span(start))

            case '[':
                self.reader.expect('[')
                self.nesting_level += 1
                return Tokens.OpenBracket(self.create_span(start))

            case ']':
                self.reader.expect(']')
                self.nesting_level -= 1
                if self.nesting_level < 0: # BPPCOMPAT: extra brackets get thrown away
                    self.nesting_level = 0
                    self._warn(
                        message="Extra closing bracket is ignored at top level (compat behavior).\n" +
                        "If you want a literal ']' character in the output, do '\\]'.",
                        span=self.create_span(start, start + 1),
                    )
                    return Tokens.OuterString("", self.create_span(start))
                return Tokens.CloseBracket(self.create_span(start))

            case '-':
                next_char = self.reader.peek(1)
                if ('0' <= next_char <= '9') or next_char == '.':
                    return self._read_number_or_unquoted(start)
                return Tokens.UnquotedString(self.reader.read_unquoted_string(), self.create_span(start))

            case '0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9' | '.':
                return self._read_number_or_unquoted(start)

            case _:
                return Tokens.UnquotedString(self.reader.read_unquoted_string(), self.create_span(start))

    def _read_number_or_unquoted(self, start: int) -> Token:
        num = self.reader.read_number_string()

        # Number tokens must match a strict numeric literal and be token-terminated.
        # Otherwise, treat them as unquoted strings (old-engine behavior).
        is_number_literal = self._is_number_literal_token(num)
        if self.reader.can_read():
            next_char = self.reader.peek()
            is_terminated = next_char in self.exceptions or next_char in " \n"
        else:
            is_terminated = True

        # Preserve leading-zero literals as strings for BPPCOMPAT (e.g. "0001").
        unsigned = num[1:] if num[:1] in "+-" else num
        has_leading_zero_int = (
            unsigned.isdigit() and len(unsigned) > 1 and unsigned.startswith("0")
        )

        if is_number_literal and is_terminated and not has_leading_zero_int:
            return Tokens.Number(num, self.create_span(start))

        self.reader.set_cursor(start)
        return Tokens.UnquotedString(
            self.reader.read_unquoted_string(), self.create_span(start)
        )

    @staticmethod
    def _is_number_literal_token(text: str) -> bool:
        # Equivalent to: [+-]?(?:\d+(?:\.\d*)?|\.\d+)
        if not text:
            return False

        i = 0
        n = len(text)
        if text[0] in "+-":
            i = 1
            if i >= n:
                return False

        digits_before = 0
        while i < n and "0" <= text[i] <= "9":
            digits_before += 1
            i += 1

        digits_after = 0
        if i < n and text[i] == ".":
            i += 1
            while i < n and "0" <= text[i] <= "9":
                digits_after += 1
                i += 1

        if i != n:
            return False

        return (digits_before > 0) or (digits_after > 0)

    def create_span(self, start: Optional[int] = None, end: Optional[int] = None) -> SpanData:
        reader = self.reader
        cursor = reader._cursor
        actual_start = cursor if start is None else start
        actual_end = cursor if end is None else end
        return SpanData(actual_start, actual_end, reader._string)

    def _warn(self, message: str, span: SpanData) -> None:
        self.warnings.append(BxeSyntaxWarning(message=message, range=span))
