from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension
from bxengine.runtime.extensions.builtin.args import ArgsExtension
from bxengine.runtime.extensions.builtin.array import ArrayExtension
from bxengine.runtime.extensions.builtin.control_flow import ControlFlowExtension
from bxengine.runtime.extensions.builtin.math import MathExtension
from bxengine.runtime.extensions.builtin.string import StringExtension
from bxengine.runtime.extensions.builtin.utility import UtilityExtension
from bxengine.runtime.extensions.builtin.variables import VariablesExtension

DEFAULT_BUILTIN_EXTENSION_TYPES = (
    ControlFlowExtension,
    VariablesExtension,
    ArgsExtension,
    MathExtension,
    StringExtension,
    ArrayExtension,
    UtilityExtension,
)


def create_default_builtin_extensions() -> list[BxeStatelessExtension]:
    return [extension_type() for extension_type in DEFAULT_BUILTIN_EXTENSION_TYPES]


class BuiltinExtension(
    ControlFlowExtension,
    VariablesExtension,
    ArgsExtension,
    MathExtension,
    StringExtension,
    ArrayExtension,
    UtilityExtension,
):
    """Compatibility aggregate for callers that still register all builtins explicitly."""

    pass


__all__ = [
    "ArgsExtension",
    "ArrayExtension",
    "BuiltinExtension",
    "ControlFlowExtension",
    "DEFAULT_BUILTIN_EXTENSION_TYPES",
    "MathExtension",
    "StringExtension",
    "UtilityExtension",
    "VariablesExtension",
    "create_default_builtin_extensions",
]
