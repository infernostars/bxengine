from __future__ import annotations

from bxengine.spans import SpanData


class BxeRuntimeException(Exception):
    def __init__(self, message: str = "", span: SpanData | None = None):
        super().__init__(message)
        self.span = span

class BxeSyntaxException(Exception):
    pass

class BxeUnclosedStringException(BxeSyntaxException):
    def __init__(self, position: int = -1):
        super().__init__("Unclosed string")
        self.position = position

class ProgramDefinedException(BxeRuntimeException):
    pass

class BxeRuntimeSyntaxException(BxeRuntimeException):
    pass
