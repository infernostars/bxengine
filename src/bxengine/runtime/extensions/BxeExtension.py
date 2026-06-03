from abc import ABC
from typing import Callable, Any

from bxengine.exceptions import BxeRuntimeSyntaxException
from bxengine.parsing.nodes import Node, Nodes
from bxengine.spans import SpanData


def bpp_function(
    name: str | None = None,
    node_transformer: bool = False,
    aliases: list[str] | tuple[str, ...] | str | None = None,
    category: str | None = None,
):
    """
    Annotates a function as available in the runtime.
    """
    if aliases is None:
        alias_tuple: tuple[str, ...] = ()
    elif isinstance(aliases, str):
        alias_tuple = (aliases,)
    else:
        alias_tuple = tuple(str(a) for a in aliases if str(a) != "")

    def decorator(func: Callable) -> Callable:
        func._is_bpp_function = True
        func._node_transformer = node_transformer
        func._bpp_function_name = name if name is not None else func.__name__
        func._bpp_function_aliases = alias_tuple
        func._bpp_function_category = category
        return func
    return decorator

class BxeExtensionBase(ABC):
    pass

class BxeStatelessExtension(BxeExtensionBase):
    pass

class BxeStatefulExtension(BxeExtensionBase):
    def post_parse_hook(self, nodes: list[Node]):
        pass

class MyBxeExtension(BxeStatelessExtension):
    @staticmethod
    @bpp_function()
    def test_basic() -> int:
        return 1

    @staticmethod
    @bpp_function()
    def test_args(val: int) -> int:
        return val * 2

    @staticmethod
    @bpp_function()
    def test_argsfloat(val: float) -> float:
        return val * 2

    @staticmethod
    @bpp_function(node_transformer=True)
    def test_nodetransform(_nodes: list[Node], span: SpanData) -> Node:
        return Nodes.Number("1", span)


class GlobalVariableBppExtension(BxeStatefulExtension):
    def __init__(self):
        self.global_variables: dict[str, Any] = {}

    def post_parse_hook(self, nodes: list[Node]):
        pass

    @bpp_function("GLOBAL")
    def global_fn(self, func_type: str, variable: str, value: Any | None = None) -> Any:
        match func_type.lower():
            case "define":
                self.global_variables[variable] = value
                return ""
            case "var":
                if value:
                    raise BxeRuntimeSyntaxException("GLOBAL VAR expected 2 parameters, but got 3")
                if not variable in self.global_variables.keys():
                    raise NameError(f"No global variable by the name {variable} defined")
                return self.global_variables[variable]
            case _:
                raise BxeRuntimeSyntaxException("GLOBAL needs a function type parameter")
