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
        raise ProgramDefinedException(a)

    # ========================= Variables =========================

    @staticmethod
    @bpp_function()
    def DEFINE(name: str, value: Any, context: RuntimeContext) -> str:
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
        _validate_variable_name(name)
        if name not in context.local_variables:
            raise NameError(f"No variable by the name {_safe_cut(name)} defined")
        return context.local_variables[name]

    # ========================= Args =========================

    @staticmethod
    @bpp_function(aliases=["ARG"])
    def ARGS(index: Any = None, context: RuntimeContext = None) -> Any:
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
        if len(args) == 1 and isinstance(args[0], list):
            context.program_args = list(args[0])
        else:
            context.program_args = list(args)
        return ""

    # ========================= Math =========================

    @staticmethod
    @bpp_function()
    def MATH(*args: Any) -> int | float:
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
        if not _is_number(a):
            raise ValueError(f"First parameter of RANDOM function is not a number: {_safe_cut(a)}")
        if not _is_number(b):
            raise ValueError(f"Second parameter of RANDOM function is not a number: {_safe_cut(b)}")
        return random.uniform(float(a), float(b))

    @staticmethod
    @bpp_function()
    def FLOOR(a: Any) -> int:
        if not _is_number(a):
            raise ValueError(f"FLOOR function parameter is not a number: {_safe_cut(a)}")
        return math.floor(float(a))

    @staticmethod
    @bpp_function()
    def CEIL(a: Any) -> int:
        if not _is_number(a):
            raise ValueError(f"CEIL function parameter is not a number: {_safe_cut(a)}")
        return math.ceil(float(a))

    @staticmethod
    @bpp_function()
    def ROUND(a: Any, b: Any = 0) -> int | float:
        if not _is_number(a):
            raise ValueError(f"ROUND function parameter is not a number: {_safe_cut(a)}")
        if not _is_whole(b):
            raise ValueError(f"ROUND function parameter is not an integer: {_safe_cut(b)}")
        rounded = round(float(a), int(b))
        return int(rounded) if rounded.is_integer() else rounded

    @staticmethod
    @bpp_function()
    def ABS(a: Any) -> int | float:
        if not _is_number(a):
            raise ValueError(f"Parameter of ABS function must be a number: {_safe_cut(a)}")
        return abs(int(a) if _is_whole(a) else float(a))

    @staticmethod
    @bpp_function()
    def MOD(a: Any, b: Any) -> int | float:
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
        if not _is_number(a):
            raise ValueError(f"SIN function parameter is not a number: {_safe_cut(a)}")
        return math.sin(float(a))

    @staticmethod
    @bpp_function()
    def COS(a: Any) -> float:
        if not _is_number(a):
            raise ValueError(f"COS function parameter is not a number: {_safe_cut(a)}")
        return math.cos(float(a))

    @staticmethod
    @bpp_function()
    def TAN(a: Any) -> float:
        if not _is_number(a):
            raise ValueError(f"TAN function parameter is not a number: {_safe_cut(a)}")
        return math.tan(float(a))

    @staticmethod
    @bpp_function()
    def MIN(a: list) -> Any:
        if not isinstance(a, list):
            raise ValueError(f"MIN function parameter is not a list: {_safe_cut(a)}")
        if all(_is_number(e) for e in a):
            a = [float(e) for e in a]
        return min(a)

    @staticmethod
    @bpp_function()
    def MAX(a: list) -> Any:
        if not isinstance(a, list):
            raise ValueError(f"MAX function parameter is not a list: {_safe_cut(a)}")
        if all(_is_number(e) for e in a):
            a = [float(e) for e in a]
        return max(a)

    # ========================= String =========================
    @staticmethod
    @bpp_function()
    def UPPER(a: str):
        return a.upper()

    @staticmethod
    @bpp_function()
    def LOWER(a: str):
        return a.lower()

    @staticmethod
    @bpp_function()
    def STRIP(a: str, side: str | None = None, chars: str | None = None):
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
        if isinstance(a, list):
            raise TypeError(f"Parameter of SPLIT function cannot be an array: {_safe_cut(a)}")
        if isinstance(b, list):
            raise TypeError(f"Parameter of SPLIT function cannot be an array: {_safe_cut(b)}")
        return str(a).split(str(b))

    @staticmethod
    @bpp_function()
    def REPLACE(a: Any, b: Any, c: Any) -> str:
        if isinstance(a, list):
            raise TypeError(f"Parameter of REPLACE function cannot be an array: {_safe_cut(a)}")
        return str(a).replace(str(b), str(c))

    @staticmethod
    @bpp_function()
    def LENGTH(a: Any) -> int:
        if isinstance(a, (int, float)):
            a = str(a)
        return len(a)

    @staticmethod
    @bpp_function()
    def INDEXOF(a: Any, b: Any, c: Any = None, d: Any = None) -> int | str:
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
        try:
            if c is not None:
                sliced = a[c:d] if d is not None else a[c:]
                return sliced.index(b)
            return a.index(b)
        except (ValueError, IndexError):
            return ""

    @staticmethod
    @bpp_function()
    def JOIN(a: list, b: str = "") -> str:
        if not isinstance(a, list):
            raise ValueError(f"First JOIN function parameter is not a list: {_safe_cut(a)}")
        if not isinstance(b, str):
            raise ValueError(f"Second JOIN function parameter is not a string: {_safe_cut(b)}")
        return b.join(str(e) for e in a)

    @staticmethod
    @bpp_function()
    def SETINDEX(a: str | list, b: int, c: Any) -> str | list:
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
        if not _is_whole(a):
            raise ValueError(f"CHAR function parameter is not an integer: {_safe_cut(a)}")
        try:
            return chr(int(a))
        except (ValueError, OverflowError):
            raise ValueError(f"CHAR function parameter is not a valid character: {_safe_cut(a)}")

    @staticmethod
    @bpp_function()
    def UNICODE(a: Any) -> int:
        if len(str(a)) != 1:
            raise ValueError(f"UNICODE function parameter is not a character: {_safe_cut(a)}")
        return ord(str(a))

    @staticmethod
    @bpp_function()
    def CHOOSECHAR(a: str, *_args: Any) -> str:
        if not isinstance(a, str):
            raise ValueError(f"CHOOSECHAR function parameter is not a string: {_safe_cut(a)}")
        return random.choice(list(a))

    # ========================= Array =========================

    @staticmethod
    @bpp_function()
    def ARRAY(*args: Any) -> list:
        return list(args)

    @staticmethod
    @bpp_function()
    def INDEX(a: str | list, b: int) -> Any:
        if not _is_whole(b):
            raise TypeError(f"Second parameter of INDEX function must be an integer: {_safe_cut(b)}")
        return a[b]

    @staticmethod
    @bpp_function()
    def SLICE(a: str | list, b: int | None = None, c: int | None = None, d: int | None = None) -> str | list:
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
        if not isinstance(a, list):
            raise ValueError(f"SHUFFLE function parameter is not a list: {_safe_cut(a)}")
        return random.sample(a, k=len(a))

    @staticmethod
    @bpp_function()
    def SORT(a: list) -> list:
        if not isinstance(a, list):
            raise ValueError(f"SORT function parameter is not a list: {_safe_cut(a)}")
        if all(_is_number(e) for e in a):
            a = [float(e) for e in a]
        return sorted(a)

    @staticmethod
    @bpp_function()
    def CHOOSE(*args: Any) -> Any:
        if len(args) == 1:
            args = args[0]
        if isinstance(args, int | float):
            args = str(args)
        return random.choice(args)

    # ========================= Utility =========================

    @staticmethod
    @bpp_function()
    def REPEAT(a: str | list, b: int) -> str | list:
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
        if _is_whole(a):
            return "int"
        if _is_number(a):
            return "float"
        return type(a).__name__

    @staticmethod
    @bpp_function()
    def TIME() -> float:
        return time.time()

    @staticmethod
    @bpp_function(name="#", aliases=["VOID"])
    def VOID(*_args: Any) -> str:
        return ""

    @staticmethod
    @bpp_function(name="//", node_transformer=True)
    def COMMENT(nodes: list[Node], span: SpanData, context: RuntimeContext) -> Any:
        return ""
