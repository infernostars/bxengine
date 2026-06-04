from typing import Any

from bxengine.runtime.context import MacroCallableValue, RuntimeContext
from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension, bpp_function

from bxengine.runtime.extensions.builtin._common import _safe_cut, _validate_variable_name


def _contains_callable(value: Any) -> bool:
    if isinstance(value, MacroCallableValue):
        return True
    if isinstance(value, list):
        return any(_contains_callable(item) for item in value)
    return False


class VariablesExtension(BxeStatelessExtension):

    # ========================= Variables =========================

    @staticmethod
    @bpp_function(category="Variables")
    def DEFINE(name: str, value: Any, context: RuntimeContext) -> str:
        """Defines or changes a variable.
        @parameter name the name of the variable. Can only contain letters, numbers, and underscores, and cannot start with a number
        @parameter value the value to be assigned to the variable
        @returns nothing"""
        _validate_variable_name(name)
        if _contains_callable(value):
            raise TypeError("Callable macro parameters cannot be saved into variables")
        if len(str(value)) > 100_000:
            raise MemoryError(
                f"The variable {_safe_cut(name)} is too large: "
                f"{_safe_cut(value)} (limit 100kb)"
            )
        context.local_variables[name] = value
        return ""

    @staticmethod
    @bpp_function(category="Variables")
    def VAR(name: str, context: RuntimeContext) -> Any:
        """Get the value of a variable.
        @parameter name the name of the variable
        @returns the value of the variable"""
        _validate_variable_name(name)
        if name not in context.local_variables:
            raise NameError(f"No variable by the name {_safe_cut(name)} defined")
        return context.local_variables[name]

