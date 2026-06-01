from bxengine.exceptions import BxeSyntaxException


class StringReader:
    def __init__(self, string: str, exceptions: str):
        self._string = string
        self._length = len(string)
        self._cursor = 0
        self._exceptions = exceptions

    def get_string(self) -> str:
        return self._string

    def get_cursor(self) -> int:
        return self._cursor

    def set_cursor(self, cursor: int) -> None:
        self._cursor = cursor

    def can_read(self, length: int = 1) -> bool:
        return self._cursor + length <= self._length

    def peek(self, offset: int = 0) -> str:
        position = self._cursor + offset
        if position >= self._length:
            raise IndexError("String index out of bounds")
        return self._string[position]

    def read(self) -> str:
        cursor = self._cursor
        if cursor >= self._length:
            raise IndexError("String index out of bounds")
        c = self._string[cursor]
        self._cursor = cursor + 1
        return c

    def skip_whitespace(self) -> None:
        string = self._string
        cursor = self._cursor
        length = self._length

        while cursor < length and string[cursor] in " \n":
            cursor += 1

        self._cursor = cursor

    def expect(self, expected: str) -> None:
        if not self.can_read() or self._string[self._cursor] != expected:
            raise BxeSyntaxException(f"Expected '{expected}' at position {self._cursor}")
        self._cursor += 1

    def read_string_until_excepting_character(self) -> str:
        string = self._string
        cursor = self._cursor
        length = self._length
        exceptions = self._exceptions
        result = []
        while cursor < length:
            c = string[cursor]
            if c in exceptions:
                break

            if c == '\\':
                cursor += 1  # consume backslash
                if cursor >= length:
                    break
                if string[cursor] == "n":
                    result.append("\n")
                else:
                    result.append(string[cursor])  # include escaped char literally
                cursor += 1
                continue
            result.append(c)
            cursor += 1

        self._cursor = cursor
        return "".join(result)

    def read_unquoted_string(self) -> str:
        string = self._string
        cursor = self._cursor
        length = self._length
        exceptions = self._exceptions
        escaped = False
        out = []

        while cursor < length:
            c = string[cursor]

            if escaped:
                if string[cursor] == "n":
                    out.append("\n")
                else:
                    out.append(c)
                cursor += 1
                escaped = False
                continue

            if c == "\\":
                cursor += 1
                escaped = True
                continue

            if c in exceptions or c in " \n":
                break

            cursor += 1
            if c in '\"“”': #BPPCOMPAT: these are ignored if not in a quoted string, apparently.
                continue

            out.append(c)

        # BPPCOMPAT: dangling trailing backslash is swallowed.
        self._cursor = cursor
        return "".join(out)

    def read_quoted_string_with_status(self) -> tuple[str, bool]:
        if not self.can_read():
            return "", False

        string = self._string
        cursor = self._cursor
        length = self._length
        quote = string[cursor]
        cursor += 1

        if quote not in '\"“”':
            self._cursor = cursor
            raise BxeSyntaxException(f"Expected quote at position {cursor - 1}")

        result = []
        escaped = False

        while cursor < length:
            c = string[cursor]
            cursor += 1
            if escaped:
                result.append(c)
                escaped = False
            elif c == '\\':
                escaped = True
            elif c in '\"“”':
                self._cursor = cursor
                return "".join(result), True
            else:
                result.append(c)

        self._cursor = cursor
        return "".join(result), False  # BXECOMPAT: unterminated strings return

    def read_quoted_string(self) -> str:
        value, _terminated = self.read_quoted_string_with_status()
        return value

    def read_number_string(self) -> str:
        string = self._string
        cursor = self._cursor
        length = self._length
        start = cursor

        while cursor < length:
            c = string[cursor]
            if ("0" <= c <= "9") or c in ".-+":
                cursor += 1
                continue
            break

        self._cursor = cursor
        return string[start:cursor]
