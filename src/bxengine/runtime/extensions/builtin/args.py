from typing import Any

from bxengine.runtime.context import RuntimeContext
from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension, bpp_function

from bxengine.runtime.extensions.builtin._common import _is_whole, _safe_cut


class ArgsExtension(BxeStatelessExtension):

    # ========================= Args =========================

    @staticmethod
    @bpp_function(aliases=["ARG"], category="Args")
    def ARGS(index: Any = None, context: RuntimeContext = None) -> Any:
        """Get one of the arguments provided for the program.
        If `a` is not provided, returns an array containing all arguments.
        @parameter a an integer index into the list of arguments provided. Zero-indexed (the first is 0)
        @returns the argument(s) specified"""
        if index is None:
            return context.program_args
        if not _is_whole(index):
            raise ValueError(f"ARGS function index must be an integer: {_safe_cut(index)}")
        idx = int(index)
        if idx >= len(context.program_args) or -idx >= len(context.program_args) + 1:
            return ""
        return context.program_args[idx]

    @staticmethod
    @bpp_function(category="Args")
    def SETARGS(*args: Any, context: RuntimeContext) -> str:
        """Change the arguments provided for the program.
        @parameter a if only this parameter is provided (must be an array), the arguments will be changed to this.
        @optional ... set the arguments to each provided parameter (with `a` as the first)
        @returns nothing"""
        if len(args) == 1 and isinstance(args[0], list):
            context.program_args = list(args[0])
        else:
            context.program_args = list(args)
        return ""


