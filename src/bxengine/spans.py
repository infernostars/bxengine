from dataclasses import dataclass


@dataclass(frozen=True)
class DebugInfo:
    is_multiline: bool
    start_line: int
    end_line: int
    first_line_prefix: str
    first_line_error: str
    first_line_suffix: str
    last_line_prefix: str = ""
    last_line_error: str = ""
    last_line_suffix: str = ""

    def __str__(self) -> str:
        def format_line(prefix: str, err: str, suffix: str) -> str:
            line = prefix + err + suffix
            l_spaces = len(line) - len(line.lstrip(' \t'))

            stripped_line = line.lstrip(' \t').rstrip()

            # Figure out where the error string begins in the stripped line
            err_start_in_stripped = max(0, len(prefix) - l_spaces)

            # If leading whitespace consumed part of the error itself, adjust the caret length
            if l_spaces > len(prefix):
                err_len = max(0, len(err) - (l_spaces - len(prefix)))
            else:
                err_len = len(err)

            spaces = ' ' * err_start_in_stripped
            caret_len = max(err_len, 1)
            carets = '^' * caret_len

            return f"{stripped_line}\n{spaces}{carets}"

        if not self.is_multiline:
            line_out = format_line(self.first_line_prefix, self.first_line_error, self.first_line_suffix)
            return f"{line_out}\n line {self.start_line}"
        else:
            first_out = format_line(self.first_line_prefix, self.first_line_error, self.first_line_suffix)
            last_out = format_line(self.last_line_prefix, self.last_line_error, self.last_line_suffix)
            lines_between = self.end_line - self.start_line
            if lines_between == 1:
                return f"{first_out}\n{last_out}\nlines {self.start_line} and {self.end_line}"
            return f"{first_out}\n({lines_between - 1} line{'' if lines_between <= 2 else 's'} cut)\n{last_out}\nlines {self.start_line}-{self.end_line}"


@dataclass(frozen=True)
class SpanData:
    cursor_start: int
    cursor_end: int
    original_string: str

    def __str__(self) -> str:
        return f"{self.cursor_start}..{self.cursor_end}"

    def __repr__(self):
        return self.__str__()

    @staticmethod
    def merge(from_span: "SpanData", to_span: "SpanData") -> "SpanData":
        return SpanData(
            cursor_start=from_span.cursor_start,
            cursor_end=to_span.cursor_end,
            original_string=to_span.original_string,
        )

    def debug_info(self) -> DebugInfo:
        def get_row_col_line(index: int):
            row = 1
            col = 1
            line_start = 0
            for i in range(index):
                if self.original_string[i] == '\n':
                    row += 1
                    col = 1
                    line_start = i + 1
                else:
                    col += 1
            line_end = self.original_string.find('\n', line_start)
            if line_end == -1:
                line_end = len(self.original_string)
            return row, col, line_start, line_end

        start_row, start_col, start_line_start, start_line_end = get_row_col_line(self.cursor_start)
        end_row, end_col, end_line_start, end_line_end = get_row_col_line(self.cursor_end)

        start_line_text = self.original_string[start_line_start:start_line_end]
        end_line_text = self.original_string[end_line_start:end_line_end]

        is_multiline = start_row != end_row

        if not is_multiline:
            prefix = start_line_text[:start_col - 1]
            err_text = start_line_text[start_col - 1:end_col - 1]
            suffix = start_line_text[end_col - 1:]

            # Cap if the length is > 75 so 35+(...)+35 actually shortens the string
            if len(err_text) > 75:
                err_text = err_text[:35] + "(...)" + err_text[-35:]

            return DebugInfo(
                is_multiline=False,
                start_line=start_row,
                end_line=end_row,
                first_line_prefix=prefix,
                first_line_error=err_text,
                first_line_suffix=suffix,
            )
        else:
            first_prefix = start_line_text[:start_col - 1]
            first_err = start_line_text[start_col - 1:]

            if len(first_err) > 40:
                first_err = first_err[:35] + "(...)"

            last_prefix = ""
            last_err = end_line_text[:end_col - 1]
            last_suffix = end_line_text[end_col - 1:]

            if len(last_err) > 40:
                last_err = "(...)" + last_err[-35:]

            return DebugInfo(
                is_multiline=True,
                start_line=start_row,
                end_line=end_row,
                first_line_prefix=first_prefix,
                first_line_error=first_err,
                first_line_suffix="",
                last_line_prefix=last_prefix,
                last_line_error=last_err,
                last_line_suffix=last_suffix,
            )