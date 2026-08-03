from __future__ import annotations

import inspect
import types
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, get_origin, get_args, Union

from bxengine.exceptions import BxeRuntimeException, BxeRecursionException
from bxengine.parsing.nodes import Node, Nodes
from bxengine.runtime.context import RuntimeContext, MacroInvocationFrame, MacroCallableValue
from bxengine.runtime.extensions.BxeExtension import (
    BxeExtensionBase,
    BxeStatefulExtension,
)
from bxengine.runtime.extensions.builtin import create_default_builtin_extensions
from bxengine.spans import SpanData

_MACRO_NESTED_CALL_CAP = 4096


@dataclass(frozen=True)
class FunctionEntry:
    func: Callable
    is_node_transformer: bool
    extension_instance: BxeExtensionBase | None
    parameter_annotations: tuple[Any, ...]
    coercion_annotations: tuple[Any | None, ...]
    context_parameter_index: int | None
    context_parameter_kind: inspect._ParameterKind | None
    node_transformer_accepts_context: bool


class ExecutorResult:
    @dataclass(frozen=True)
    class Success:
        output: str
        stateful_extensions: list[BxeStatefulExtension] = field(default_factory=list)

    @dataclass(frozen=True)
    class Error:
        exception: Exception


@dataclass
class ExecutorSession:
    context: RuntimeContext
    stateful_extensions: list[BxeStatefulExtension] = field(default_factory=list)


def _safe_cut(s: Any, num: int = 15) -> str:
    return str(s)[:num] + ("..." if len(str(s)) > num else "")


def _is_number(v: Any) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def _is_whole(v: Any) -> bool:
    try:
        i = int(v)
        f = float(v)
        return f - i == 0
    except (ValueError, TypeError):
        return False


def _is_optional(target_type):
    origin = get_origin(target_type)
    if origin is Union or origin is types.UnionType:
        return type(None) in get_args(target_type)
    return False

def _extract_non_optional(typ):
    if _is_optional(typ):
        args = [arg for arg in get_args(typ) if arg is not type(None)]
        return args[0] if len(args) == 1 else Union[tuple(args)]
    return typ

def _scan_extension(ext: BxeExtensionBase) -> list[tuple[str, FunctionEntry]]:
    entries: list[tuple[str, FunctionEntry]] = []
    for attr_name in dir(ext):
        if attr_name.startswith("_"):
            continue
        attr = getattr(ext, attr_name, None)
        if attr is None:
            continue
        if callable(attr) and getattr(attr, "_is_bpp_function", False):
            name = getattr(attr, "_bpp_function_name", attr_name).upper()
            aliases = tuple(
                str(alias).upper() for alias in getattr(attr, "_bpp_function_aliases", ())
            )
            is_node_transformer = getattr(attr, "_node_transformer", False)
            sig = inspect.signature(attr)
            parameters = list(sig.parameters.values())
            parameter_annotations = tuple(p.annotation for p in parameters)
            coercion_annotations = tuple(
                (
                    None
                    if (ann is inspect.Parameter.empty or ann is Any or ann is object)
                    else ann
                )
                for p, ann in zip(parameters, parameter_annotations)
                if p.name != "context"
            )
            context_parameter_index = next(
                (i for i, p in enumerate(parameters) if p.name == "context"),
                None,
            )
            context_parameter_kind = (
                parameters[context_parameter_index].kind
                if context_parameter_index is not None
                else None
            )
            entry = FunctionEntry(
                func=attr,
                is_node_transformer=is_node_transformer,
                extension_instance=ext,
                parameter_annotations=parameter_annotations,
                coercion_annotations=coercion_annotations,
                context_parameter_index=context_parameter_index,
                context_parameter_kind=context_parameter_kind,
                node_transformer_accepts_context=(
                    is_node_transformer and context_parameter_index is not None
                ),
            )
            # Register primary function name plus optional aliases.
            seen_names = set()
            for resolved_name in (name, *aliases):
                if resolved_name in seen_names:
                    continue
                seen_names.add(resolved_name)
                entries.append((resolved_name, entry))
    return entries


class Executor:
    def __init__(
        self,
        extensions: list[BxeExtensionBase] | None = None,
        stateful_extensions: list[type[BxeStatefulExtension]] | None = None,
        program_args: list[Any] | None = None,
    ):
        self._program_args = program_args or []

        registered_extensions = (
            create_default_builtin_extensions() if extensions is None else extensions
        )

        self._stateless_functions: dict[str, FunctionEntry] = {}
        for ext in registered_extensions:
            for name, entry in _scan_extension(ext):
                self._stateless_functions[name] = entry

        self._stateful_classes: list[type[BxeStatefulExtension]] = list(
            stateful_extensions or []
        )

    def create_session(self) -> ExecutorSession:
        functions = dict(self._stateless_functions)
        stateful_instances: list[BxeStatefulExtension] = []

        for cls in self._stateful_classes:
            instance = cls()
            stateful_instances.append(instance)
            for name, entry in _scan_extension(instance):
                functions[name] = entry

        context = RuntimeContext(
            local_variables={},
            program_args=self._program_args,
            executor=self,
            functions=functions,
        )

        return ExecutorSession(
            context=context,
            stateful_extensions=stateful_instances,
        )

    def execute(
        self, nodes: list[Node]
    ) -> ExecutorResult.Success | ExecutorResult.Error:
        return self.execute_in_session(nodes, self.create_session())

    def execute_in_session(
        self, nodes: list[Node], session: ExecutorSession
    ) -> ExecutorResult.Success | ExecutorResult.Error:
        context = session.context
        context.macro_nested_calls_used = 0
        context.loop_iterations_used = 0
        context.callable_call_stack.clear()

        for inst in session.stateful_extensions:
            inst.post_parse_hook(nodes)

        output_parts: list[str] = []
        try:
            for node in nodes:
                if isinstance(node, Nodes.OuterText):
                    output_parts.append(node.value)
                elif isinstance(node, Nodes.Function):
                    result = self._evaluate_function(node, context)
                    output_parts.append(self._format_result(result))
        except Exception as e:
            return ExecutorResult.Error(exception=e)

        return ExecutorResult.Success(
            output="".join(output_parts),
            stateful_extensions=session.stateful_extensions,
        )

    def _evaluate_function(self, node: Nodes.Function, context: RuntimeContext) -> Any:
        try:
            func_name = node.name.upper()

            if func_name.startswith("@") and func_name in context.macros:
                return self.invoke_macro(
                    macro_name=func_name,
                    argument_nodes=node.arguments,
                    call_span=node.range,
                    context=context,
                )

            entry = context.functions.get(func_name)

            if entry is None:
                raise NameError(f"Function {node.name} does not exist")

            if entry.is_node_transformer:
                return self._call_node_transformer(entry, node, context)

            evaluated_args: list[Any] = []
            for arg in node.arguments:
                evaluated_args.append(self._evaluate_node(arg, context))

            coerced_args = self._coerce_args(entry, evaluated_args)
            final_args, kwargs = self._inject_context(entry, coerced_args, context)

            return entry.func(*final_args, **kwargs)
        except Exception as e:
            self._attach_span_if_missing(e, node.range)
            raise

    def invoke_macro(
        self,
        macro_name: str,
        argument_nodes: list[Node],
        call_span: SpanData,
        context: RuntimeContext,
    ) -> Any:
        try:
            if macro_name not in context.macros:
                raise NameError(f"Macro {macro_name} does not exist")

            macro = context.macros[macro_name]

            if macro_name in context.macro_call_stack:
                cycle = " -> ".join((*context.macro_call_stack, macro_name))
                raise BxeRecursionException(f"Macro recursion detected: {cycle}")

            required_args = sum(1 for p in macro.parameters if not p.optional)
            max_args = None if macro.supports_varargs else len(macro.parameters)

            if len(argument_nodes) < required_args:
                raise TypeError(
                    f"{macro.call_name} expected at least {required_args} parameters, "
                    f"but got {len(argument_nodes)}"
                )
            if max_args is not None and len(argument_nodes) > max_args:
                raise TypeError(
                    f"{macro.call_name} expected at most {max_args} parameters, "
                    f"but got {len(argument_nodes)}"
                )

            # First-level macro invocations do not count toward this cap.
            if context.macro_call_stack:
                projected = context.macro_nested_calls_used + 1
                if projected > _MACRO_NESTED_CALL_CAP:
                    raise BxeRecursionException(
                        "Macro nested call cap exceeded: "
                        f"attempted {projected} nested calls (limit {_MACRO_NESTED_CALL_CAP})"
                    )
                context.macro_nested_calls_used = projected

            param_scope: dict[str, Any] = {}
            bound_args: list[Any] = []
            for index, param in enumerate(macro.parameters):
                if index < len(argument_nodes):
                    if param.callable:
                        value = MacroCallableValue(argument_nodes[index])
                    else:
                        value = self._evaluate_node(argument_nodes[index], context)
                    param_scope[param.name] = value
                    bound_args.append(value)
                else:
                    # Optional parameters default to empty string when omitted.
                    param_scope[param.name] = ""

            if macro.supports_varargs and len(argument_nodes) > len(macro.parameters):
                for arg in argument_nodes[len(macro.parameters):]:
                    if macro.varargs_callable:
                        bound_args.append(MacroCallableValue(arg))
                    else:
                        bound_args.append(self._evaluate_node(arg, context))

            context.macro_call_stack.append(macro_name)
            context.macro_param_stack.append(
                MacroInvocationFrame(
                    parameter_values=param_scope,
                    all_arguments=tuple(bound_args),
                )
            )
            try:
                return self._evaluate_node(macro.body, context)
            finally:
                context.macro_param_stack.pop()
                context.macro_call_stack.pop()
        except Exception as e:
            self._attach_span_if_missing(e, call_span)
            raise

    def _evaluate_node(self, node: Node, context: RuntimeContext) -> Any:
        if isinstance(node, Nodes.Function):
            return self._evaluate_function(node, context)
        elif isinstance(node, Nodes.Number):
            return self._parse_number(node.value)
        elif isinstance(node, Nodes.StringNode):
            return node.value
        elif isinstance(node, Nodes.OuterText):
            return node.value
        else:
            raise BxeRuntimeException(f"Unexpected node type: {type(node).__name__}")

    def _call_node_transformer(
        self, entry: FunctionEntry, node: Nodes.Function, context: RuntimeContext
    ) -> Any:
        try:
            if entry.node_transformer_accepts_context:
                result = entry.func(node.arguments, node.range, context=context)
            else:
                result = entry.func(node.arguments, node.range)
        except Exception as e:
            self._attach_span_if_missing(e, node.range)
            raise

        if isinstance(result, Node):
            return self._evaluate_node(result, context)
        return result

    @staticmethod
    def _attach_span_if_missing(exception: Exception, span: SpanData) -> None:
        existing = getattr(exception, "span", None)
        if existing is None:
            try:
                setattr(exception, "span", span)
            except Exception:
                pass

    def _coerce_args(self, entry: FunctionEntry, args: list[Any]) -> list[Any]:
        coercion_annotations = entry.coercion_annotations
        if not coercion_annotations:
            return args

        coerced: list[Any] = []
        for i, arg in enumerate(args):
            if i < len(coercion_annotations) and coercion_annotations[i] is not None:
                coerced.append(self._coerce_value(arg, coercion_annotations[i]))
            else:
                coerced.append(arg)
        return coerced

    @staticmethod
    def _coerce_value(value: Any, target_type: type) -> Any:
        #print(value, target_type)
        if value is None:
            #print("none!")
            return value
        if _is_optional(target_type):
            if value == "":
                #print("emptystr -> none!")
                return None
            target_type = _extract_non_optional(target_type)
        if target_type is float and isinstance(value, int):
            #print("int -> float!")
            return float(value)
        if target_type is int and isinstance(value, float):
            #print("float -> int!")
            return int(value)
        if target_type == str | list or target_type == Union[str, list]:
            if isinstance(value, list):
                #print("str | list -> list!")
                return value
            #print("str | list -> str!")
            return str(value)
        if target_type is str:
            #print("str!")
            return str(value)
        if target_type in (int, float) and isinstance(value, str):
            try:
                return target_type(value)
            except (ValueError, TypeError):
                return value

        return value

    @staticmethod
    def _inject_context(
        entry: FunctionEntry, args: list[Any], context: RuntimeContext
    ) -> tuple[list[Any], dict[str, Any]]:
        context_idx = entry.context_parameter_index
        if context_idx is None:
            return args, {}

        if entry.context_parameter_kind is inspect.Parameter.KEYWORD_ONLY:
            return args, {"context": context}

        if entry.context_parameter_kind is inspect.Parameter.POSITIONAL_ONLY:
            final_args = list(args)
            final_args.insert(context_idx, context)
            return final_args, {}

        if len(args) > context_idx:
            function_name = getattr(entry.func, "__name__", "function").upper()
            raise TypeError(
                f"{function_name} expected at most {context_idx} parameters, "
                f"but got {len(args)}"
            )

        return args, {"context": context}

    @staticmethod
    def _parse_number(value: str) -> str:
        # BPPCOMPAT:
        # The old engine keeps bare numeric-looking literals as raw strings
        # unless a function explicitly converts them.
        return value

    @staticmethod
    def _format_result(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return Executor._express_array(value)
        return str(value)

    @staticmethod
    def _express_array(l: list) -> str:
        str_form = " ".join(['"' + str(a) + '"' for a in l])
        return f"[ARRAY {str_form}]"

    def evaluate_node(self, node: Node, context: RuntimeContext) -> Any:
        return self._evaluate_node(node, context)

if __name__ == "__main__":
    print(_extract_non_optional(int | str | None))
