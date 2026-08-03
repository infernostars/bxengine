import math
import random
from typing import Any

from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension, bpp_function

from bxengine.runtime.extensions.builtin._common import _is_number, _is_whole, _safe_cut

_MULTIPLY_LIMIT = 1e50


class MathExtension(BxeStatelessExtension):

    # ========================= Math =========================

    @staticmethod
    @bpp_function(category="Math")
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
                    values[i] = MathExtension._math_op(
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
        raise ValueError(f"Operation parameter of MATH function not an operation: {_safe_cut(op)}")

    @staticmethod
    @bpp_function(category="Math")
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
    @bpp_function(category="Math")
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
    @bpp_function(category="Math")
    def FLOOR(a: Any) -> int:
        """Returns the floor of a number; the part before the decimal point
        @parameter a the number to be floored
        @returns the floor of `a`"""
        if not _is_number(a):
            raise ValueError(f"FLOOR function parameter is not a number: {_safe_cut(a)}")
        return math.floor(float(a))

    @staticmethod
    @bpp_function(category="Math")
    def CEIL(a: Any) -> int:
        """Returns the ceiling of a number; the smallest whole number greater or equal to it
        @parameter a the number to be ceiled
        @returns the ceil of `a`"""
        if not _is_number(a):
            raise ValueError(f"CEIL function parameter is not a number: {_safe_cut(a)}")
        return math.ceil(float(a))

    @staticmethod
    @bpp_function(category="Math")
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
    @bpp_function(category="Math")
    def ABS(a: Any) -> int | float:
        """Returns the absolute value of a number (the number made positive if it was negative, otherwise unchanged)
        @parameter a the number to use
        @returns the absolute value of `a`"""
        if not _is_number(a):
            raise ValueError(f"Parameter of ABS function must be a number: {_safe_cut(a)}")
        return abs(int(a) if _is_whole(a) else float(a))

    @staticmethod
    @bpp_function(category="Math")
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
    @bpp_function(category="Math")
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
    @bpp_function(category="Math")
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
    @bpp_function(category="Math")
    def SIN(a: Any) -> float:
        """Returns the sine of `a`
        @parameter a the number to take the sine of
        @returns the sine of `a`"""
        if not _is_number(a):
            raise ValueError(f"SIN function parameter is not a number: {_safe_cut(a)}")
        return math.sin(float(a))

    @staticmethod
    @bpp_function(category="Math")
    def COS(a: Any) -> float:
        """Returns the cosine of `a`
        @parameter a the number to take the cosine of
        @returns the cosine of `a`"""
        if not _is_number(a):
            raise ValueError(f"COS function parameter is not a number: {_safe_cut(a)}")
        return math.cos(float(a))

    @staticmethod
    @bpp_function(category="Math")
    def TAN(a: Any) -> float:
        """Returns the tangent of `a`
        @parameter a the number to take the tangent of
        @returns the tangent of `a`"""
        if not _is_number(a):
            raise ValueError(f"TAN function parameter is not a number: {_safe_cut(a)}")
        return math.tan(float(a))

    @staticmethod
    @bpp_function(category="Math")
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
    @bpp_function(category="Math")
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


