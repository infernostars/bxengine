import random
from typing import Any

from bxengine.runtime.extensions.BxeExtension import BxeStatelessExtension, bpp_function

from bxengine.runtime.extensions.builtin._common import _is_number, _is_whole, _safe_cut


class ArrayExtension(BxeStatelessExtension):

    # ========================= Array =========================

    @staticmethod
    @bpp_function(category="Array")
    def ARRAY(*args: Any) -> list:
        """Creates a new array.
        @parameter ... items that will be part of the array. Can be empty
        @returns an array created from the items given"""
        return list(args)

    @staticmethod
    @bpp_function(category="Array")
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
    @bpp_function(category="Array")
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
    @bpp_function(category="Array")
    def SHUFFLE(a: list) -> list:
        """Randomly shuffles the contents of an array
        @parameter a the array to shuffle
        @returns an array containing the items of `a` in a random order"""
        if not isinstance(a, list):
            raise ValueError(f"SHUFFLE function parameter is not a list: {_safe_cut(a)}")
        return random.sample(a, k=len(a))

    @staticmethod
    @bpp_function(category="Array")
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
    @bpp_function(category="Array")
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


