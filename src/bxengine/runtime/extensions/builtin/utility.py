import time
from typing import Any

from bxengine.parsing.nodes import Node
from bxengine.runtime.context import RuntimeContext
from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension, bpp_function
from bxengine.spans import SpanData

from bxengine.runtime.extensions.builtin._common import _ITERATION_LIMIT, _is_number, _is_whole, _safe_cut


class UtilityExtension(BxeStatelessExtension):

    # ========================= Utility =========================

    @staticmethod
    @bpp_function(category="Utility")
    def REPEAT(a: str | list, b: int) -> str | list:
        """Repeats the contents of a string or array
        @parameter a the array or string to be repeated
        @parameter b the amount of times to repeat `a`
        @returns the characters of the string `a` or elements of the array `a`, repeated `b` times"""
        if not _is_whole(b):
            raise ValueError(f"Second parameter of REPEAT function is not an integer: {_safe_cut(b)}")
        if not isinstance(a, list):
            a = str(a)

        if len(a) * b > _ITERATION_LIMIT:
            raise ValueError(
                f"Second parameter of REPEAT function is too large: {_safe_cut(b)} "
                f"(limit of length {_ITERATION_LIMIT})"
            )
        return a * b

    @staticmethod
    @bpp_function(category="Utility")
    def TYPE(a: Any) -> str:
        """Gets the data type of the input.
        Can be str, int, float, or list.
        @parameter a the value to get the type of
        @returns the type of `a`"""
        if _is_whole(a):
            return "int"
        if _is_number(a):
            return "float"
        return type(a).__name__

    @staticmethod
    @bpp_function(category="Utility")
    def TIME() -> float:
        """Gets the time in Unix time
        @returns the time, in the UTC timezone, in seconds since 1970"""
        return time.time()

    @staticmethod
    @bpp_function(name="VOID", aliases=["#"], category="Utility")
    def VOID(*_args: Any) -> str:
        """Returns nothing
        @optional function the function to be run. Will be executed, but its output discarded
        @returns nothing"""
        return ""

    @staticmethod
    @bpp_function(name="//", node_transformer=True, category="Utility")
    def COMMENT(nodes: list[Node], span: SpanData, context: RuntimeContext) -> Any:
        """Makes a comment. Nothing inside the function will be run or executed
        @optional comment the comment. Will not be executed
        @returns nothing"""
        return ""


