from typing import Any

from bxengine.exceptions import (
    BxeRuntimeException,
    BxeRuntimeSyntaxException,
    ProgramDefinedException,
)
from bxengine.parsing.nodes import Node, Nodes
from bxengine.runtime.context import (
    MacroCallableValue,
    MacroDefinition,
    MacroParameterSpec,
    RuntimeContext,
)
from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension, bpp_function
from bxengine.spans import SpanData

from bxengine.runtime.extensions.builtin._common import (
    _is_number,
    _is_whole,
    _safe_cut,
    _validate_macro_name,
    _validate_variable_name,
)

_LOOP_ITERATION_CAP = 4096


class ControlFlowExtension(BxeStatelessExtension):

    # ========================= Control Flow =========================

    @staticmethod
    @bpp_function(node_transformer=True, category="Control Flow")
    def IF(nodes: list[Node], span: SpanData, context: RuntimeContext) -> Any:
        """Selects a function based on whether the condition is true
        @parameter condition the minimum of the range, inclusive
        @parameter true the function to be run if the condition is true
        @optional false the function to be run if the condition is false
        @returns the return value of the selected function, or "" if the condition is false and the `false` parameter is not supplied"""
        if len(nodes) < 2:
            raise BxeRuntimeSyntaxException("IF expected at least 2 parameters")
        condition = context.executor.evaluate_node(nodes[0], context)
        # BPPCOMPAT: only 0 and "0" are falsy for IF.
        if condition not in (0, "0"):
            return context.executor.evaluate_node(nodes[1], context)
        if len(nodes) > 2:
            return context.executor.evaluate_node(nodes[2], context)
        return ""

    @staticmethod
    @bpp_function(node_transformer=True, category="Control Flow")
    def TRY(nodes: list[Node], span: SpanData, context: RuntimeContext):
        """Tries to run the first block. If an error occurs, execution will jump to the second block. Whatever happened before the error will still happen.
        @parameter a The first block of functions to run. Everything executes until an error is found, in which case it stops and begins running `b`
        @parameter b The block to be run if `a` encounters an error.
        @returns the return value of the first block if it doesn't error, otherwise that of the second block"""
        if len(nodes) != 2:
            raise BxeRuntimeSyntaxException("TRY expected 2 parameters")
        try:
            return context.executor.evaluate_node(nodes[0], context)
        except Exception as exc:
            previous_exception = context.last_exception
            context.last_exception = exc
            ret = context.executor.evaluate_node(nodes[1], context)
            context.last_exception = previous_exception
            return ret

    @staticmethod
    def _consume_loop_budget(context: RuntimeContext, amount: int) -> None:
        if amount <= 0:
            return
        projected = context.loop_iterations_used + amount
        if projected > _LOOP_ITERATION_CAP:
            raise BxeRuntimeException(
                f"LOOP iteration cap exceeded: attempted {projected} iterations "
                f"(limit {_LOOP_ITERATION_CAP})"
            )
        context.loop_iterations_used = projected

    @staticmethod
    @bpp_function(node_transformer=True, category="Control Flow")
    def LOOP(nodes: list[Node], span: SpanData, context: RuntimeContext) -> str:
        """Loop a block of code repeatedly.
        @parameter amount the amount of times to loop
        @parameter code the block to be looped
        @returns the return value of all loops concatenated together
        @note you may only loop 4096 times total during a program
        @example [LOOP 10 [RANDINT 0 5]] -> 2013404123"""
        if len(nodes) != 2:
            raise BxeRuntimeSyntaxException("LOOP expected 2 parameters")

        count_raw = context.executor.evaluate_node(nodes[0], context)
        if not _is_whole(count_raw):
            raise ValueError(f"First parameter of LOOP function must be an integer: {_safe_cut(count_raw)}")
        count = int(count_raw)
        if count < 0:
            raise ValueError(f"First parameter of LOOP function cannot be negative: {_safe_cut(count_raw)}")
        if count == 0:
            return ""

        body_node = nodes[1]
        is_direct_nested_loop = (
            isinstance(body_node, Nodes.Function)
            and body_node.name.upper() == "LOOP"
        )

        out: list[str] = []
        for _ in range(count):
            # Count effective loop work once for non-nested bodies.
            # Direct nested LOOPs consume from the shared cap inside the inner LOOP.
            if not is_direct_nested_loop:
                ControlFlowExtension._consume_loop_budget(context, 1)
            value = context.executor.evaluate_node(body_node, context)
            out.append(context.executor._format_result(value))
        return "".join(out)

    @staticmethod
    def _normalize_macro_call_name(name: Any) -> str:
        if not isinstance(name, str):
            raise NameError(f"Macro name must be a string: {_safe_cut(name)}")
        stripped = name.strip()
        if stripped == "":
            raise NameError("Macro name cannot be empty")
        if stripped.startswith("@"):
            stripped = stripped[1:]
        _validate_macro_name(stripped)
        return f"@{stripped.upper()}"

    @staticmethod
    def _value_to_literal_node(value: Any, span: SpanData) -> Node:
        if isinstance(value, MacroCallableValue):
            return value.node
        if isinstance(value, Node):
            return value
        if isinstance(value, list):
            return Nodes.Function(
                name="ARRAY",
                arguments=[ControlFlowExtension._value_to_literal_node(v, span) for v in value],
                range=span,
            )
        if value is None:
            return Nodes.StringNode("", span)
        return Nodes.StringNode(str(value), span)

    @staticmethod
    @bpp_function(node_transformer=True, category="Control Flow")
    def MACRO(nodes: list[Node], span: SpanData, context: RuntimeContext) -> str:
        """Create a macro that can be called with [@macro params].
        @parameter name the name of the macro
        @parameter params an array of the names of parameters for the macro. You may add ? to the end of a name to mark it as optional, or :callable to pass the original node without evaluating it. Optional parameters must come after required ones; you can also add ... to the end to allow any number of extra arguments.
        @parameter block the code that the macro will run
        @returns nothing"""
        if len(nodes) != 3:
            raise BxeRuntimeSyntaxException("MACRO expected 3 parameters")

        macro_name_value = context.executor.evaluate_node(nodes[0], context)
        macro_call_name = ControlFlowExtension._normalize_macro_call_name(macro_name_value)

        parameter_values = context.executor.evaluate_node(nodes[1], context)
        if not isinstance(parameter_values, list):
            raise TypeError(
                f"Second parameter of MACRO function must be an array: {_safe_cut(parameter_values)}"
            )

        parameter_specs: list[MacroParameterSpec] = []
        supports_varargs = False
        saw_optional_parameter = False
        for index, raw_name in enumerate(parameter_values):
            if not isinstance(raw_name, str):
                raise TypeError(
                    f"Macro parameter name must be a string: {_safe_cut(raw_name)}"
                )

            if raw_name == "...":
                if supports_varargs:
                    raise BxeRuntimeSyntaxException("MACRO can only declare varargs once")
                if index != len(parameter_values) - 1:
                    raise BxeRuntimeSyntaxException("MACRO varargs (...) must be the last parameter")
                supports_varargs = True
                continue

            parameter_name = raw_name
            optional = False
            callable_parameter = False
            while True:
                if parameter_name.endswith(":callable"):
                    callable_parameter = True
                    parameter_name = parameter_name[: -len(":callable")]
                    continue
                if parameter_name.endswith("?"):
                    optional = True
                    parameter_name = parameter_name[:-1]
                    continue
                break

            if saw_optional_parameter and not optional:
                raise BxeRuntimeSyntaxException(
                    "MACRO optional parameters must come after all required parameters"
                )
            if optional:
                saw_optional_parameter = True
            _validate_variable_name(parameter_name)
            parameter_specs.append(
                MacroParameterSpec(
                    name=parameter_name,
                    optional=optional,
                    callable=callable_parameter,
                )
            )

        context.macros[macro_call_name] = MacroDefinition(
            call_name=macro_call_name,
            parameters=tuple(parameter_specs),
            supports_varargs=supports_varargs,
            body=nodes[2],
        )
        return ""

    @staticmethod
    @bpp_function(node_transformer=True, category="Control Flow")
    def CALL(nodes: list[Node], span: SpanData, context: RuntimeContext) -> Any:
        """Call the function, macro, or callable node `a` with the array `b` as arguments
        @parameter a the function or macro to be executed
        @optional b an array of arguments to use for the function or macro
        @returns the return value of the function or macro"""
        if len(nodes) not in (1, 2):
            raise BxeRuntimeSyntaxException("CALL expected 1 or 2 parameters")
        target_value = context.executor.evaluate_node(nodes[0], context)
        raw_args: list[Any] = []
        argument_nodes: list[Node] = []
        if len(nodes) == 2:
            raw_args = context.executor.evaluate_node(nodes[1], context)
            if not isinstance(raw_args, list):
                raise TypeError(f"Second parameter of CALL must be an array: {_safe_cut(raw_args)}")
            argument_nodes = [
                ControlFlowExtension._value_to_literal_node(arg, span) for arg in raw_args
            ]

        if isinstance(target_value, MacroCallableValue):
            target_value = target_value.node

        if isinstance(target_value, Node):
            if argument_nodes:
                if not isinstance(target_value, Nodes.Function):
                    raise TypeError("CALL cannot pass arguments to a non-function callable node")
                call_node = Nodes.Function(
                    name=target_value.name,
                    arguments=argument_nodes,
                    range=target_value.range,
                )
            else:
                call_node = target_value

            callable_id = id(target_value)
            if callable_id in context.callable_call_stack:
                raise BxeRuntimeException("Callable recursion detected")
            context.callable_call_stack.append(callable_id)
            try:
                return context.executor.evaluate_node(call_node, context)
            finally:
                context.callable_call_stack.pop()

        if not isinstance(target_value, str):
            raise NameError(f"Function or macro name must be a string: {_safe_cut(target_value)}")
        target_name = target_value.strip()
        if target_name == "":
            raise NameError("Function or macro name cannot be empty")

        # Explicit macro call
        if target_name.startswith("@"):
            macro_call_name = ControlFlowExtension._normalize_macro_call_name(target_name)
            return context.executor.invoke_macro(
                macro_name=macro_call_name,
                argument_nodes=argument_nodes,
                call_span=span,
                context=context,
            )

        # Prefer runtime/builtin function lookup for bare names.
        function_name = target_name.upper()
        if function_name in context.functions:
            return context.executor.evaluate_node(
                Nodes.Function(name=function_name, arguments=argument_nodes, range=span),
                context,
            )

        raise BxeRuntimeException(f"\"{_safe_cut(target_name)}\" is not a function or macro")

    @staticmethod
    @bpp_function(node_transformer=True, aliases=["PARAM"], category="Control Flow")
    def PARAMS(nodes: list[Node], span: SpanData, context: RuntimeContext) -> Any:
        """May only be used inside a macro. Get one of the parameters of the macro
        If `a` is not provided, returns an array containing all parameters
        @parameter a the name of the argument to retrieve
        @returns the parameter(s) specified"""
        if len(nodes) > 1:
            raise BxeRuntimeSyntaxException("PARAMS expected 0 or 1 parameter")
        if not context.macro_param_stack:
            raise BxeRuntimeException("PARAMS can only be used inside a macro")

        if len(nodes) == 0:
            return list(context.macro_param_stack[-1].all_arguments)

        raw_name = context.executor.evaluate_node(nodes[0], context)
        if not isinstance(raw_name, str):
            raise TypeError(f"PARAMS name must be a string: {_safe_cut(raw_name)}")
        _validate_variable_name(raw_name)

        frame = context.macro_param_stack[-1]
        if raw_name not in frame.parameter_values:
            raise NameError(f"No macro parameter named {_safe_cut(raw_name)}")
        return frame.parameter_values[raw_name]

    @staticmethod
    @bpp_function(category="Control Flow")
    def EXCEPTION(detail: str, context: RuntimeContext):
        """May only be used in the second block of a TRY block. Gets the exception caused during the execution of the first block.
        @parameter detail a string. "type" will return the exception type (e.g. "NameError"), while "detail" will return the details (e.g. "Function INVALID does not exist")
        @returns see above."""
        if context.last_exception is None:
            raise BxeRuntimeException("Cannot get the exception outside a TRY block")
        match detail.lower():
            case "type":
                return type(context.last_exception).__name__
            case "detail":
                if isinstance(context.last_exception, ProgramDefinedException):
                    return context.last_exception.bxe_detail
                return str(context.last_exception)
            case _:
                raise BxeRuntimeSyntaxException(f"Unknown exception info parameter {detail}")



    @staticmethod
    @bpp_function(category="Control Flow")
    def COMPARE(a: Any, b: str, c: Any) -> int | Any:
        """Compares 2 items.
        @parameter a the first item to compare
        @parameter op the operation to use. can be >, <, >=, <=, !=, =, ==, "and", or "or".
        @parameter b the second item to compare. Must have the same type as `a`
        @returns the result of the comparison, as 0 if false and 1 if true"""
        operations = [">", "<", ">=", "<=", "!=", "=", "==", "and", "or"]
        if b not in operations:
            raise ValueError(
                f"Operation parameter of COMPARE function is not a comparison operator: {_safe_cut(b)}"
            )
        if _is_number(a):
            a = float(a)
        if _is_number(c):
            c = float(c)
        if operations.index(b) <= 3 and type(a) is not type(c):
            raise TypeError("Entries to compare in COMPARE function are not the same type")
        if b == ">":
            return int(a > c)
        if b == "<":
            return int(a < c)
        if b == ">=":
            return int(a >= c)
        if b == "<=":
            return int(a <= c)
        if b == "!=":
            return int(a != c)
        if b in ("=", "=="):
            return int(a == c)
        if b == "and":
            result = a and c
            return int(result) if type(result) is bool else result
        if b == "or":
            result = a or c
            return int(result) if type(result) is bool else result

    @staticmethod
    @bpp_function(category="Control Flow")
    def THROW(a: Any) -> None:
        """Throw an exception and stop executing the program
        @parameter exception the details of the exception
        @returns nothing"""
        raise ProgramDefinedException(a)
