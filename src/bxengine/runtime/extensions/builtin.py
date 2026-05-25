import math
import random
import re
import time
from typing import Any


from bxengine.exceptions import (
    BxeRuntimeException,
    BxeRuntimeSyntaxException, ProgramDefinedException,
)
from bxengine.parsing.nodes import Node, Nodes
from bxengine.runtime.context import RuntimeContext, MacroDefinition, MacroParameterSpec
from bxengine.runtime.extensions.BxeExtension import (
    BxeStatelessExtension,
    bpp_function,
)
from bxengine.spans import SpanData

_ITERATION_LIMIT = 131072
_LOOP_ITERATION_CAP = 4096
_MULTIPLY_LIMIT = 1e50


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


def _to_number(v: Any) -> int | float:
    return int(v) if _is_whole(v) else float(v)

def _equal_repr(v: Any) -> int | str | list:
    if _is_number(v):
        return str(float(v))
    elif v is int or v is float:
        return str(v)
    return v

def _validate_variable_name(name: str) -> None:
    if not isinstance(name, str):
        raise NameError(f"Variable name must be a string: {_safe_cut(name)}")
    if re.search(r"[^A-Za-z_0-9]", name) or (name and re.search(r"[0-9]", name[0])):
        raise NameError(
            f"Variable name must be only letters, underscores and numbers, "
            f"and cannot start with a number: {_safe_cut(name)}"
        )


def _validate_macro_name(name: str) -> None:
    if not isinstance(name, str):
        raise NameError(f"Macro name must be a string: {_safe_cut(name)}")
    if name == "":
        raise NameError("Macro name cannot be empty")
    if re.search(r'[\\\s\[\]"“”]', name):
        raise NameError(
            "Macro name cannot contain spaces, brackets, quotes, or backslashes: "
            f"{_safe_cut(name)}"
        )


class BuiltinExtension(BxeStatelessExtension):

    # ========================= Control Flow =========================

    @staticmethod
    @bpp_function(node_transformer=True)
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
    @bpp_function(node_transformer=True)
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
    @bpp_function(node_transformer=True)
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
                BuiltinExtension._consume_loop_budget(context, 1)
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
        if isinstance(value, list):
            return Nodes.Function(
                name="ARRAY",
                arguments=[BuiltinExtension._value_to_literal_node(v, span) for v in value],
                range=span,
            )
        if value is None:
            return Nodes.StringNode("", span)
        return Nodes.StringNode(str(value), span)

    @staticmethod
    @bpp_function(node_transformer=True)
    def MACRO(nodes: list[Node], span: SpanData, context: RuntimeContext) -> str:
        """Create a macro that can be called with [@macro params].
        @parameter name the name of the macro
        @parameter params an array of the names of parameters for the macro. You may add ? to the end of a name to mark it as optional. Optional parameters must come after required ones; you can also add ... to the end to allow any number of extra arguments.
        @parameter block the code that the macro will run
        @returns nothing"""
        if len(nodes) != 3:
            raise BxeRuntimeSyntaxException("MACRO expected 3 parameters")

        macro_name_value = context.executor.evaluate_node(nodes[0], context)
        macro_call_name = BuiltinExtension._normalize_macro_call_name(macro_name_value)

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

            optional = raw_name.endswith("?")
            parameter_name = raw_name[:-1] if optional else raw_name
            if saw_optional_parameter and not optional:
                raise BxeRuntimeSyntaxException(
                    "MACRO optional parameters must come after all required parameters"
                )
            if optional:
                saw_optional_parameter = True
            _validate_variable_name(parameter_name)
            parameter_specs.append(MacroParameterSpec(name=parameter_name, optional=optional))

        context.macros[macro_call_name] = MacroDefinition(
            call_name=macro_call_name,
            parameters=tuple(parameter_specs),
            supports_varargs=supports_varargs,
            body=nodes[2],
        )
        return ""

    @staticmethod
    @bpp_function(node_transformer=True)
    def CALL(nodes: list[Node], span: SpanData, context: RuntimeContext) -> Any:
        """Call the function or macro `a` with the array `b` as arguments
        @parameter a the function or macro to be executed
        @parameter b an array of arguments to use for the function or macro
        @returns the return value of the function or macro"""
        if len(nodes) != 2:
            raise BxeRuntimeSyntaxException("CALL expected 2 parameters")
        target_value = context.executor.evaluate_node(nodes[0], context)
        if not isinstance(target_value, str):
            raise NameError(f"Function or macro name must be a string: {_safe_cut(target_value)}")
        target_name = target_value.strip()
        if target_name == "":
            raise NameError("Function or macro name cannot be empty")

        raw_args = context.executor.evaluate_node(nodes[1], context)
        if not isinstance(raw_args, list):
            raise TypeError(f"Second parameter of CALL must be an array: {_safe_cut(raw_args)}")
        argument_nodes = [BuiltinExtension._value_to_literal_node(arg, span) for arg in raw_args]

        # Explicit macro call form: [CALL "@name" [ARRAY ...]]
        if target_name.startswith("@"):
            macro_call_name = BuiltinExtension._normalize_macro_call_name(target_name)
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
    @bpp_function(node_transformer=True, aliases=["PARAM"])
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
    @bpp_function()
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
    @bpp_function()
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
    @bpp_function()
    def THROW(a: Any) -> None:
        """Throw an exception and stop executing the program
        @parameter exception the details of the exception
        @returns nothing"""
        raise ProgramDefinedException(a)

    # ========================= Variables =========================

    @staticmethod
    @bpp_function()
    def DEFINE(name: str, value: Any, context: RuntimeContext) -> str:
        """Defines or changes a variable.
        @parameter name the name of the variable. Can only contain letters, numbers, and underscores, and cannot start with a number
        @parameter value the value to be assigned to the variable
        @returns nothing"""
        _validate_variable_name(name)
        if len(str(value)) > 100_000:
            raise MemoryError(
                f"The variable {_safe_cut(name)} is too large: "
                f"{_safe_cut(value)} (limit 100kb)"
            )
        context.local_variables[name] = value
        return ""

    @staticmethod
    @bpp_function()
    def VAR(name: str, context: RuntimeContext) -> Any:
        """Get the value of a variable.
        @parameter name the name of the variable
        @returns the value of the variable"""
        _validate_variable_name(name)
        if name not in context.local_variables:
            raise NameError(f"No variable by the name {_safe_cut(name)} defined")
        return context.local_variables[name]

    # ========================= Args =========================

    @staticmethod
    @bpp_function(aliases=["ARG"])
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
    @bpp_function()
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

    # ========================= Math =========================

    @staticmethod
    @bpp_function()
    def MATH(*args: Any) -> int | float:
        """Function for math expressions.
        @parameter expression The expression to be evaluated. Can contain functions, numbers, and the +, -, *, /, ^, and % (modulo) operators.
        @returns the answer to the expression"""
        expression = "".join(
            [str(x) if not isinstance(x, list) else str(x) for x in args]
        ).replace(" ", "")
        operators = set("+-*/^%")
        values: list[str] = []
        buffer = ""
        for c in expression:
            if c in operators and (
                (c != "-" or len(buffer) > 0) and buffer[-1:] != "e"
            ):
                values.append(buffer)
                buffer = ""
                values.append(c)
            else:
                buffer += c
        if buffer:
            values.append(buffer)

        order = ("^", "*/%", "+-")
        for ops in order:
            i = 0
            while i + 2 < len(values):
                if str(values[i + 1]) in ops:
                    values[i] = BuiltinExtension._math_op(
                        values[i], values[i + 1], values[i + 2]
                    )
                    values.pop(i + 1)
                    values.pop(i + 1)
                else:
                    i += 1

        if len(values) > 1:
            raise ValueError(
                f"Parameters of MATH function do not result in a single value: "
                f"{' '.join(str(a) for a in args)}"
            )
        out = values[0]
        if isinstance(out, (int, float)):
            return int(out) if isinstance(out, float) and out == int(out) else out
        f = float(out)
        return int(f) if f == int(f) else f

    @staticmethod
    def _math_op(a: Any, op: str, c: Any) -> int | float:
        if not _is_number(a):
            raise ValueError(f"First parameter of MATH function is not a number: {_safe_cut(a)}")
        if op not in "+-*/^%":
            raise ValueError(f"Operation parameter of MATH function not an operation: {_safe_cut(op)}")
        if not _is_number(c):
            raise ValueError(f"Second parameter of MATH function is not a number: {_safe_cut(c)}")
        a_n = int(a) if _is_whole(a) else float(a)
        c_n = int(c) if _is_whole(c) else float(c)
        if op == "+":
            return a_n + c_n
        if op == "-":
            return a_n - c_n
        if op == "*":
            if abs(a_n) > _MULTIPLY_LIMIT:
                raise ValueError(
                    f"First parameter of MATH function too large to safely multiply: "
                    f"{_safe_cut(a_n)} (limit 10^50)"
                )
            if abs(c_n) > _MULTIPLY_LIMIT:
                raise ValueError(
                    f"Second parameter of MATH function too large to safely multiply: "
                    f"{_safe_cut(c_n)} (limit 10^50)"
                )
            return a_n * c_n
        if op == "/":
            if c_n == 0:
                raise ZeroDivisionError(
                    "Second parameter of MATH function in division cannot be zero"
                )
            return a_n / c_n
        if op == "%":
            if c_n == 0:
                raise ZeroDivisionError(
                    "Second parameter of MATH function in modulo cannot be zero"
                )
            return a_n % c_n
        if op == "^":
            try:
                return math.pow(a_n, c_n)
            except OverflowError:
                raise ValueError(
                    f"Parameters of MATH function too large to safely exponentiate: "
                    f"{_safe_cut(a_n)}, {_safe_cut(c_n)}"
                )

    @staticmethod
    @bpp_function()
    def RANDINT(a: Any, b: Any) -> int:
        """Generates a random integer number between `a` and `b`, including `a` but not `b`
        @parameter a the minimum of the range, inclusive
        @parameter b the maximum of the range, exclusive
        @returns the random number"""
        if not _is_whole(a):
            raise ValueError(f"First parameter of RANDINT function is not an integer: {_safe_cut(a)}")
        if not _is_whole(b):
            raise ValueError(f"Second parameter of RANDINT function is not an integer: {_safe_cut(b)}")
        lo, hi = sorted([int(a), int(b)])
        if lo == hi:
            hi += 1
        return random.randrange(lo, hi)

    @staticmethod
    @bpp_function()
    def RANDOM(a: Any, b: Any) -> float:
        """Generates a random number between `a` and `b`
        @parameter a the minimum of the range
        @parameter b the maximum of the range
        @returns the random number"""
        if not _is_number(a):
            raise ValueError(f"First parameter of RANDOM function is not a number: {_safe_cut(a)}")
        if not _is_number(b):
            raise ValueError(f"Second parameter of RANDOM function is not a number: {_safe_cut(b)}")
        return random.uniform(float(a), float(b))

    @staticmethod
    @bpp_function()
    def FLOOR(a: Any) -> int:
        """Returns the floor of a number; the part before the decimal point
        @parameter a the number to be floored
        @returns the floor of `a`"""
        if not _is_number(a):
            raise ValueError(f"FLOOR function parameter is not a number: {_safe_cut(a)}")
        return math.floor(float(a))

    @staticmethod
    @bpp_function()
    def CEIL(a: Any) -> int:
        """Returns the ceiling of a number; the smallest whole number greater or equal to it
        @parameter a the number to be ceiled
        @returns the ceil of `a`"""
        if not _is_number(a):
            raise ValueError(f"CEIL function parameter is not a number: {_safe_cut(a)}")
        return math.ceil(float(a))

    @staticmethod
    @bpp_function()
    def ROUND(a: Any, b: Any = 0) -> int | float:
        """Rounds a number to the closest whole number
        @parameter a the number to be rounded
        @returns the rounded number"""
        if not _is_number(a):
            raise ValueError(f"ROUND function parameter is not a number: {_safe_cut(a)}")
        if not _is_whole(b):
            raise ValueError(f"ROUND function parameter is not an integer: {_safe_cut(b)}")
        rounded = round(float(a), int(b))
        return int(rounded) if rounded.is_integer() else rounded

    @staticmethod
    @bpp_function()
    def ABS(a: Any) -> int | float:
        """Returns the absolute value of a number (the number made positive if it was negative, otherwise unchanged)
        @parameter a the number to use
        @returns the absolute value of `a`"""
        if not _is_number(a):
            raise ValueError(f"Parameter of ABS function must be a number: {_safe_cut(a)}")
        return abs(int(a) if _is_whole(a) else float(a))

    @staticmethod
    @bpp_function()
    def MOD(a: Any, b: Any) -> int | float:
        """Returns the remainder ("modulo") of dividing `a` by `b`
        @parameter a the number to be divided
        @parameter b the number to divide by
        @returns the modulo of `a` and `b`"""
        if not _is_number(a):
            raise ValueError(f"First parameter of MOD function is not a number: {_safe_cut(a)}")
        if not _is_number(b):
            raise ValueError(f"Second parameter of MOD function is not a number: {_safe_cut(b)}")
        a_n = int(a) if _is_whole(a) else float(a)
        b_n = int(b) if _is_whole(b) else float(b)
        if b_n == 0:
            raise ZeroDivisionError("Second parameter of MOD function cannot be zero")
        return a_n % b_n

    @staticmethod
    @bpp_function()
    def LOG(a: Any, b: Any) -> float:
        """Returns the logarithm of `a` base `b`, or the natural logarithm of `a` if `b` is omitted
        @parameter a the number to take the logarithm of
        @parameter b the base of the logarithm; defaults to e
        @returns the logarithm"""
        if not _is_number(a):
            raise ValueError(f"LOG function parameter is not a number: {_safe_cut(a)}")
        if not _is_number(b):
            raise ValueError(f"LOG function parameter is not a number: {_safe_cut(b)}")
        if float(b) == 0:
            raise ValueError("Second parameter of LOG function must not be zero")
        return math.log(float(a), float(b))

    @staticmethod
    @bpp_function()
    def FACTORIAL(a: Any) -> float:
        """Returns the factorial of `a` (`a * a-1 * a-2 ... 2 * 1`)
        @parameter a the number to take the factorial of
        @returns the factorial of `a`
        @note this function also works for fractional and (most) negative values (using the equivalent Γ(x+1))"""
        if not _is_number(a):
            raise ValueError(f"FACTORIAL function parameter is not a number: {_safe_cut(a)}")
        try:
            return math.gamma(float(a) + 1)
        except OverflowError:
            raise ValueError(
                f"First parameter of FACTORIAL function too large to safely factorial: {_safe_cut(a)}"
            )

    @staticmethod
    @bpp_function()
    def SIN(a: Any) -> float:
        """Returns the sine of `a`
        @parameter a the number to take the sine of
        @returns the sine of `a`"""
        if not _is_number(a):
            raise ValueError(f"SIN function parameter is not a number: {_safe_cut(a)}")
        return math.sin(float(a))

    @staticmethod
    @bpp_function()
    def COS(a: Any) -> float:
        """Returns the cosine of `a`
        @parameter a the number to take the cosine of
        @returns the cosine of `a`"""
        if not _is_number(a):
            raise ValueError(f"COS function parameter is not a number: {_safe_cut(a)}")
        return math.cos(float(a))

    @staticmethod
    @bpp_function()
    def TAN(a: Any) -> float:
        """Returns the tangent of `a`
        @parameter a the number to take the tangent of
        @returns the tangent of `a`"""
        if not _is_number(a):
            raise ValueError(f"TAN function parameter is not a number: {_safe_cut(a)}")
        return math.tan(float(a))

    @staticmethod
    @bpp_function()
    def MIN(a: list) -> Any:
        """Returns the minimum value in the array `a`
        This is the lowest number if all values in the array are numbers, otherwise the lexicographically earliest
        ("15" < "2" < "aeiou" < "zyxxy")
        @parameter a the array to find the minimum value of
        @returns the minimum"""
        if not isinstance(a, list):
            raise ValueError(f"MIN function parameter is not a list: {_safe_cut(a)}")
        if all(_is_number(e) for e in a):
            a = [float(e) for e in a]
        return min(a)

    @staticmethod
    @bpp_function()
    def MAX(a: list) -> Any:
        """Returns the maximum value in the array `a`
        This is the highest number if all values in the array are numbers, otherwise the lexicographically last
        ("15" < "2" < "aeiou" < "zyxxy")
        @parameter a the array to find the maximum value of
        @returns the maximum"""
        if not isinstance(a, list):
            raise ValueError(f"MAX function parameter is not a list: {_safe_cut(a)}")
        if all(_is_number(e) for e in a):
            a = [float(e) for e in a]
        return max(a)

    # ========================= String =========================
    @staticmethod
    @bpp_function()
    def UPPER(a: str):
        """Returns the string `s` in all uppercase
        @parameter s the input string
        @returns `s` in all-caps"""
        return a.upper()

    @staticmethod
    @bpp_function()
    def LOWER(a: str):
        """Returns the string `s` in all lowercase
        @parameter s the input string
        @returns `s` in lowercase"""
        return a.lower()

    @staticmethod
    @bpp_function()
    def STRIP(a: str, side: str | None = None, chars: str | None = None):
        """Strips whitespace or other characters from the sides of a string.
        If chars is provided, characters will be stripped from the edge until a character not in the list is found
        @parameter s the input string
        @optional side the side(s) to strip. can be "both" (default), "right", or "left"
        @optional chars a string containing the characters to strip
        @returns the stripped string"""
        side = side if side is not None else "both"
        side = side.lower()
        match side:
            case "both":
                return a.strip(chars)
            case "right":
                return a.rstrip(chars)
            case "left":
                return a.lstrip(chars)
            case _:
                raise BxeRuntimeException(f"Unknown side to strip {_safe_cut(side)}")

    @staticmethod
    @bpp_function()
    def CONCAT(*args: Any) -> str | list:
        """Concatenates its inputs together
        @parameter ... arrays to join together, or other items to concatenate as strings
        @returns the joined array or string"""
        all_type = None
        for a in args:
            if isinstance(a, (int, float)):
                a = str(a)
            if all_type is None:
                all_type = type(a)
            elif type(a) is not all_type:
                raise TypeError("CONCAT parameters must either be all arrays or all strings")
        if all_type is str:
            return "".join(str(a) for a in args)
        if all_type is list:
            import itertools
            return list(itertools.chain(*args))
        raise IndexError("Cannot call CONCAT function with no arguments")

    @staticmethod
    @bpp_function()
    def SPLIT(a: Any, b: Any) -> list:
        """Splits the string `s` by `b`
        @parameter s the string to be split
        @parameter b the separator to split the string by
        @returns an array containing the split parts of the string
        @example [SPLIT test,b,,123, ,] -> [ARRAY "test" "b" "" "123" ""]"""
        if isinstance(a, list):
            raise TypeError(f"Parameter of SPLIT function cannot be an array: {_safe_cut(a)}")
        if isinstance(b, list):
            raise TypeError(f"Parameter of SPLIT function cannot be an array: {_safe_cut(b)}")
        return str(a).split(str(b))

    @staticmethod
    @bpp_function()
    def REPLACE(a: Any, b: Any, c: Any) -> str:
        """Replaces all instances of `b` in the string `s` with `c`
        @parameter s the string
        @parameter b the substring to replace
        @Parameter c the string to replace every instance of `b` with
        @returns the string `s` with replacements made"""
        if isinstance(a, list):
            raise TypeError(f"Parameter of REPLACE function cannot be an array: {_safe_cut(a)}")
        return str(a).replace(str(b), str(c))

    @staticmethod
    @bpp_function()
    def LENGTH(a: Any) -> int:
        """Returns the length of `a` as either a string or array
        @parameter a the string or array
        @returns the number of characters in the string `a`, or the number of items in the array `a`"""
        if isinstance(a, (int, float)):
            a = str(a)
        return len(a)

    @staticmethod
    @bpp_function()
    def INDEXOF(a: Any, b: Any, c: Any = None, d: Any = None) -> int | str:
        """Finds the index of `b` in the array `a`
        @parameter a the array to search in
        @parameter b the item to find
        @optional c the index to start searching at
        @optional d the index to finish searching at
        @returns the index of `b` in `a` (after `c` and before `d`, if applicable)"""
        if c is not None and not _is_number(c) and not isinstance(c, str):
            raise TypeError(
                f"Optional third parameter of INDEXOF function must be a number: {_safe_cut(c)}"
            )
        if d is not None and not _is_number(d) and not isinstance(d, str):
            raise TypeError(
                f"Optional fourth parameter of INDEXOF function must be a number: {_safe_cut(d)}"
            )
        if isinstance(c, str):
            try:
                c = int(c)
            except ValueError:
                raise TypeError(
                    f"Optional third parameter of INDEXOF function must be a number: {_safe_cut(c)}"
                )
        if isinstance(d, str):
            try:
                d = int(d)
            except ValueError:
                raise TypeError(
                    f"Optional fourth parameter of INDEXOF function must be a number: {_safe_cut(d)}"
                )
        if not isinstance(a, (str, list)):
            raise TypeError(
                f"First parameter of INDEXOF function must be an array or string: {_safe_cut(a)}"
            )

        # Strings should be searched as strings so substring lookups work.
        if isinstance(a, str):
            try:
                if c is not None:
                    sliced = a[c:d] if d is not None else a[c:]
                    return sliced.index(str(b))
                return a.index(str(b))
            except (ValueError, IndexError):
                return ""

        a_str = [_equal_repr(i) for i in a]
        try:
            if c is not None:
                sliced = a_str[c:d] if d is not None else a_str[c:]
                return sliced.index(_equal_repr(b))
            return a_str.index(_equal_repr(b))
        except (ValueError, IndexError):
            return ""

    @staticmethod
    @bpp_function()
    def JOIN(a: list, b: str = "") -> str:
        """Joins the elements of `a` as strings using `b` as a separator.
        @parameter a the list to join together
        @parameter b the separator to use
        @returns a string containing the elements of `a` joined together with `b`
        @example [JOIN [ARRAY a b 1.5] ;] -> a;b;1.5
        """
        if not isinstance(a, list):
            raise ValueError(f"First JOIN function parameter is not a list: {_safe_cut(a)}")
        if not isinstance(b, str):
            raise ValueError(f"Second JOIN function parameter is not a string: {_safe_cut(b)}")
        return b.join(str(e) for e in a)

    @staticmethod
    @bpp_function()
    def SETINDEX(a: str | list, b: int, c: Any) -> str | list:
        """Returns a string or array with one item changed
        @parameter a the string or array to be changed
        @parameter b the index into `a` to change
        @parameter c what the item at index `b` of `a` should be set to
        @returns `a` with the item at index `b` set to `c`
        """
        if not _is_whole(b):
            raise ValueError(f"SETINDEX function parameter is not an integer: {_safe_cut(b)}")
        idx = int(b)
        if isinstance(a, list):
            mylist = a.copy()
            mylist[idx] = c
            return mylist
        a = str(a)
        if len(str(c)) > 1:
            raise ValueError(f"SETINDEX function parameter is not a character: {_safe_cut(c)}")
        # noinspection PyTypeChecker
        return a[:idx] + str(c) + a[idx + 1 :]

    @staticmethod
    @bpp_function()
    def CHAR(a: Any) -> str:
        """Returns a Unicode character from its codepoint
        @parameter a the codepoint of the character as a decimal integer
        @returns the character at that codepoint
        """
        if not _is_whole(a):
            raise ValueError(f"CHAR function parameter is not an integer: {_safe_cut(a)}")
        try:
            return chr(int(a))
        except (ValueError, OverflowError):
            raise ValueError(f"CHAR function parameter is not a valid character: {_safe_cut(a)}")

    @staticmethod
    @bpp_function()
    def UNICODE(a: Any) -> int:
        """Finds the Unicode codepoint for a character
        @parameter c a single-character string
        @returns the codepoint of `c` as an integer
        """
        if len(str(a)) != 1:
            raise ValueError(f"UNICODE function parameter is not a character: {_safe_cut(a)}")
        return ord(str(a))

    @staticmethod
    @bpp_function()
    def CHOOSECHAR(a: str, *_args: Any) -> str:
        """Chooses a random character of the string `s`.
        @parameter s the string to use
        @returns a randomly chosen character of `s`
        """
        if not isinstance(a, str):
            raise ValueError(f"CHOOSECHAR function parameter is not a string: {_safe_cut(a)}")
        return random.choice(list(a))

    # ========================= Array =========================

    @staticmethod
    @bpp_function()
    def ARRAY(*args: Any) -> list:
        """Creates a new array.
        @parameter ... items that will be part of the array. Can be empty
        @returns an array created from the items given"""
        return list(args)

    @staticmethod
    @bpp_function()
    def INDEX(a: str | list, b: int) -> Any:
        """Indexes into a string or array. Always zero-indexed (index 0 is the first item/character)
        Negative indexes can be used (-1 is the last item, -2 the second-to-last, etc.)
        @parameter a the string or array to be indexed into
        @parameter b the index to use
        @returns the `b`-th item of the array `a`, or `b`-th character of the string `a`"""
        if not _is_whole(b):
            raise TypeError(f"Second parameter of INDEX function must be an integer: {_safe_cut(b)}")
        return a[b]

    @staticmethod
    @bpp_function()
    def SLICE(a: str | list, b: int | None = None, c: int | None = None, d: int | None = None) -> str | list:
        """Returns a portion of a string or array
        @parameter a the string or array to be sliced
        @optional b the start of the slice
        @optional c the end of the slice; the character at this index will not be included
        @optional d the step; 2 will only contain every other item, 3 every third item, and -1 will go backwards
        @returns the sliced string/array
        @example [SLICE "hello world" 0 5] -> hello
        @example [SLICE "hello world" "" -3] -> hello wo
        @example [SLICE "-h-e-l-l-o" 1 "" 2] -> hello"""
        if b is not None and not _is_whole(b):
            raise TypeError(f"Second parameter of SLICE function must be an integer: {_safe_cut(b)}")
        if c is not None and not _is_whole(c):
            raise TypeError(f"Third parameter of SLICE function must be an integer: {_safe_cut(c)}")
        if d is not None and not _is_whole(d):
            raise TypeError(
                f"Optional fourth parameter of SLICE function must be an integer: {_safe_cut(d)}"
            )
        if d is not None and int(d) == 0:
            raise TypeError(
                f"Optional fourth parameter of SLICE function cannot be 0: {_safe_cut(d)}"
            )
        to_cut = a if isinstance(a, list) else str(a)
        start = int(b) if b is not None else None
        end = int(c) if c is not None else None
        step = int(d) if d is not None else None
        return to_cut[start:end:step]

    @staticmethod
    @bpp_function()
    def SHUFFLE(a: list) -> list:
        """Randomly shuffles the contents of an array
        @parameter a the array to shuffle
        @returns an array containing the items of `a` in a random order"""
        if not isinstance(a, list):
            raise ValueError(f"SHUFFLE function parameter is not a list: {_safe_cut(a)}")
        return random.sample(a, k=len(a))

    @staticmethod
    @bpp_function()
    def SORT(a: list) -> list:
        """Sorts an array
        Items will be ordered by number if all values in the array are numbers, otherwise lexicographically
        ("15" < "2" < "aeiou" < "zyxxy")
        @parameter a the array to sort
        @returns a sorted version of the array"""
        if not isinstance(a, list):
            raise ValueError(f"SORT function parameter is not a list: {_safe_cut(a)}")
        if all(_is_number(e) for e in a):
            a = [float(e) for e in a]
        return sorted(a)

    @staticmethod
    @bpp_function()
    def CHOOSE(*args: Any) -> Any:
        """Randomly chooses between items in an array, or between the arguments of the function
        @parameter a an array of items
        @optional ... more items to choose between; if supplied, `a` will be treated as a single item
        @returns a randomly selected item from the array or items supplied."""
        if len(args) == 1:
            args = args[0]
        if isinstance(args, int | float):
            args = str(args)
        return random.choice(args)

    # ========================= Utility =========================

    @staticmethod
    @bpp_function()
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
    @bpp_function()
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
    @bpp_function()
    def TIME() -> float:
        """Gets the time in Unix time
        @returns the time, in the UTC timezone, in seconds since 1970"""
        return time.time()

    @staticmethod
    @bpp_function(name="#", aliases=["VOID"])
    def VOID(*_args: Any) -> str:
        """Returns nothing
        @optional function the function to be run. Will be executed, but its output discarded
        @returns nothing"""
        return ""

    @staticmethod
    @bpp_function(name="//", node_transformer=True)
    def COMMENT(nodes: list[Node], span: SpanData, context: RuntimeContext) -> Any:
        """Makes a comment. Nothing inside the function will be run or executed
        @optional comment the comment. Will not be executed
        @returns nothing"""
        return ""
