import random
import re
from typing import Any

from bxengine.exceptions import BxeRuntimeException
from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension, bpp_function

from bxengine.runtime.extensions.builtin._common import (
    _equal_repr,
    _is_number,
    _is_whole,
    _safe_cut,
)


class StringExtension(BxeStatelessExtension):

    # ========================= String =========================
    @staticmethod
    @bpp_function(category="String")
    def UPPER(a: str):
        """Returns the string `s` in all uppercase
        @parameter s the input string
        @returns `s` in all-caps"""
        return a.upper()

    @staticmethod
    @bpp_function(category="String")
    def LOWER(a: str):
        """Returns the string `s` in all lowercase
        @parameter s the input string
        @returns `s` in lowercase"""
        return a.lower()

    @staticmethod
    @bpp_function(category="String")
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
    @bpp_function(category="String")
    def CONCAT(*args: Any) -> str | list:
        """Concatenates its inputs together
        @parameter ... arrays to join together, or other items to concatenate as strings
        @returns the joined array or string"""
        all_type = None
        filtered_args = tuple([a for a in args if not (isinstance(a, str) and a == "")])
        for a in filtered_args:
            if isinstance(a, (int, float)):
                a = str(a)
            if all_type is None:
                all_type = type(a)
            elif type(a) is not all_type:
                raise TypeError("CONCAT parameters must either be all arrays or all strings")
        if all_type is str:
            return "".join(str(a) for a in filtered_args)
        if all_type is list:
            import itertools
            return list(itertools.chain(*filtered_args))
        if len(args) > 0:
            return ""
        raise IndexError("Cannot call CONCAT function with no arguments")

    @staticmethod
    @bpp_function(category="String")
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
    @bpp_function(category="String")
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
    @bpp_function(category="String")
    def LENGTH(a: Any) -> int:
        """Returns the length of `a` as either a string or array
        @parameter a the string or array
        @returns the number of characters in the string `a`, or the number of items in the array `a`"""
        if isinstance(a, (int, float)):
            a = str(a)
        return len(a)

    @staticmethod
    @bpp_function(category="String")
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
    @bpp_function(category="String")
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
    @bpp_function(category="String")
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
    @bpp_function(category="String")
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
    @bpp_function(category="String")
    def UNICODE(a: Any) -> int:
        """Finds the Unicode codepoint for a character
        @parameter c a single-character string
        @returns the codepoint of `c` as an integer
        """
        if len(str(a)) != 1:
            raise ValueError(f"UNICODE function parameter is not a character: {_safe_cut(a)}")
        return ord(str(a))

    @staticmethod
    @bpp_function(category="String")
    def CHOOSECHAR(a: str, *_args: Any) -> str:
        """Chooses a random character of the string `s`.
        @parameter s the string to use
        @returns a randomly chosen character of `s`
        """
        if not isinstance(a, str):
            raise ValueError(f"CHOOSECHAR function parameter is not a string: {_safe_cut(a)}")
        return random.choice(list(a))
        
    @staticmethod
    @bpp_function(category="String")
    def REGEXREPLACE(a: str, b: str, c: str) -> str:
        """Replaces all sections of the string `s` that match the RegEx `r` with the string `c`.
        @parameter s the string to use
        @parameter r the RegEx to check
        @parameter c the string to replace with
        @returns the string `s` with replacements made 
        """
        try:
            return re.sub(str(b), str(c), str(a))
        except:
            raise ValueError(f"REGEXREPLACE function could not evaluate this RegEx: {_safe_cut(b)}")
            
    @staticmethod
    @bpp_function(category="String")
    def REGEXMATCH(a: str, b: str) -> list[str]:
        """Finds all substrings of the string `s` that match the RegEx `r`.
        @parameter s the string to use
        @parameter r the RegEx to check
        @returns a list of all substrings of `s` that match `r`
        """
        try:
            return re.findall(str(b), str(a))
        except:
            raise ValueError(f"REGEXMATCH function could not evaluate this RegEx: {_safe_cut(b)}")
