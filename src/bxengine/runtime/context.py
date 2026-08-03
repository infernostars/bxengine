from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from bxengine.parsing.nodes import Node

if TYPE_CHECKING:
    from bxengine.runtime.executor import Executor, FunctionEntry

@dataclass(frozen=True)
class MacroParameterSpec:
    name: str
    optional: bool = False
    callable: bool = False


@dataclass(frozen=True)
class MacroCallableValue:
    node: Node


@dataclass(frozen=True)
class MacroDefinition:
    call_name: str
    parameters: tuple[MacroParameterSpec, ...]
    supports_varargs: bool
    body: Node
    varargs_callable: bool = False


@dataclass(frozen=True)
class MacroInvocationFrame:
    parameter_values: dict[str, Any]
    all_arguments: tuple[Any, ...]


@dataclass
class RuntimeContext:
    local_variables: dict[str, Any] = field(default_factory=dict)
    program_args: list[Any] = field(default_factory=list)
    executor: Executor | None = None
    functions: dict[str, FunctionEntry] = field(default_factory=dict)
    macros: dict[str, MacroDefinition] = field(default_factory=dict)
    macro_call_stack: list[str] = field(default_factory=list)
    macro_param_stack: list[MacroInvocationFrame] = field(default_factory=list)
    callable_call_stack: list[int] = field(default_factory=list)
    macro_nested_calls_used: int = 0
    loop_iterations_used: int = 0
    last_exception: Exception | None = None
