from bxengine.runtime.executor import ExecutorResult

from conftest import run_program, run_program_raw


class TestString:
    def test_concat(self):
        assert run_program('[CONCAT "hello " "world"]') == "hello world"

    def test_concat_numbers(self):
        assert run_program('[CONCAT "val=" 42]') == "val=42"

    def test_split(self):
        assert run_program('[SPLIT "a,b,c" ","]') == '[ARRAY "a" "b" "c"]'

    def test_replace(self):
        assert run_program('[REPLACE "hello world" "world" "there"]') == "hello there"

    def test_length(self):
        assert run_program('[LENGTH "hello"]') == "5"

    def test_length_number(self):
        assert run_program("[LENGTH 12345]") == "5"

    def test_indexof_string(self):
        assert run_program('[INDEXOF "hello world" "world"]') == "6"

    def test_indexof_not_found(self):
        assert run_program('[INDEXOF "hello" "xyz"]') == ""

    def test_join(self):
        assert run_program('[JOIN [SPLIT "a,b,c" ","] "-"]') == "a-b-c"

    def test_setindex_string(self):
        assert run_program('[SETINDEX "hello" 0 "H"]') == "Hello"

    def test_char(self):
        assert run_program("[CHAR 65]") == "A"

    def test_unicode(self):
        assert run_program("[UNICODE A]") == "65"

    def test_choosechar(self):
        result = run_program('[CHOOSECHAR "abc"]')
        assert result in "abc"


class TestArray:
    def test_array(self):
        assert run_program("[ARRAY 1 2 3]") == '[ARRAY "1" "2" "3"]'

    def test_index(self):
        assert run_program("[INDEX [ARRAY a b c] 1]") == "b"

    def test_slice_string(self):
        assert run_program('[SLICE "hello world" 0 5]') == "hello"

    def test_slice_array(self):
        assert run_program("[SLICE [ARRAY a b c d] 1 3]") == '[ARRAY "b" "c"]'

    def test_slice_array_with_only_start(self):
        assert run_program("[SLICE [ARRAY a b] 1]") == '[ARRAY "b"]'

    def test_slice_with_only_source_returns_copy(self):
        assert run_program("[SLICE [ARRAY a b]]") == '[ARRAY "a" "b"]'

    def test_shuffle(self):
        result = run_program("[SHUFFLE [ARRAY 1 2 3]]")
        assert "ARRAY" in result

    def test_sort(self):
        assert run_program("[SORT [ARRAY 3 1 2]]") == '[ARRAY "1.0" "2.0" "3.0"]'

    def test_choose(self):
        result = run_program("[CHOOSE [ARRAY 10 20 30]]")
        assert result in ("10", "20", "30")

    def test_concat_arrays(self):
        assert run_program("[CONCAT [ARRAY 1 2] [ARRAY 3 4]]") == '[ARRAY "1" "2" "3" "4"]'

    def test_repeat_array(self):
        assert run_program("[REPEAT [ARRAY 1 2] 2]") == '[ARRAY "1" "2" "1" "2"]'


class TestUtility:
    def test_repeat_string(self):
        assert run_program('[REPEAT "ab" 3]') == "ababab"

    def test_repeat_limit(self):
        res = run_program_raw("[REPEAT x 131073]")
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, ValueError)

    def test_type_int(self):
        assert run_program("[TYPE 42]") == "int"

    def test_type_float(self):
        assert run_program("[TYPE 3.14]") == "float"

    def test_type_string(self):
        assert run_program('[TYPE "hi"]') == "str"

    def test_type_list(self):
        assert run_program("[TYPE [ARRAY 1]]") == "list"

    def test_time(self):
        val = float(run_program("[TIME]"))
        assert val > 0
