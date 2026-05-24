from bxengine.runtime.executor import ExecutorResult
from bxengine.exceptions import BxeRuntimeException

from conftest import run_program, run_program_raw


class TestOuterText:
    def test_plain_text(self):
        assert run_program("just plain text") == "just plain text"

    def test_empty_input(self):
        assert run_program("") == ""

    def test_text_around_function(self):
        assert run_program('Hello [CONCAT "world" "!"] end') == "Hello world! end"


class TestControlFlow:
    def test_if_true(self):
        assert run_program('[IF 1 "yes" "no"]') == "yes"

    def test_if_false(self):
        assert run_program('[IF 0 "yes" "no"]') == "no"

    def test_if_truthy_string(self):
        assert run_program('[IF "anything" "yes" "no"]') == "yes"

    def test_if_empty_string_is_not_falsy(self):
        assert run_program('[IF "" "yes" "no"]') == "yes"

    def test_if_no_else(self):
        assert run_program('[IF 0 "yes"]') == ""

    def test_if_lazy_eval_condition_true(self):
        assert run_program('[IF 1 [DEFINE x "taken"] [DEFINE x "skipped"]] [VAR x]') == " taken"

    def test_if_lazy_eval_condition_false(self):
        assert run_program('[IF 0 [DEFINE x "skipped"] [DEFINE x "taken"]] [VAR x]') == " taken"

    def test_compare_gt(self):
        assert run_program('[COMPARE 5 ">" 3]') == "1"
        assert run_program('[COMPARE 3 ">" 5]') == "0"

    def test_compare_lt(self):
        assert run_program('[COMPARE 3 "<" 5]') == "1"

    def test_compare_eq(self):
        assert run_program('[COMPARE 5 "=" 5]') == "1"
        assert run_program('[COMPARE 5 "==" 5]') == "1"

    def test_compare_neq(self):
        assert run_program('[COMPARE 5 "!=" 3]') == "1"

    def test_compare_gte(self):
        assert run_program('[COMPARE 5 ">=" 5]') == "1"
        assert run_program('[COMPARE 5 ">=" 3]') == "1"

    def test_compare_lte(self):
        assert run_program('[COMPARE 3 "<=" 5]') == "1"

    def test_compare_and(self):
        assert run_program('[COMPARE 1 "and" 1]') == "1.0"
        assert run_program('[COMPARE 1 "and" 0]') == "0.0"

    def test_compare_or(self):
        assert run_program('[COMPARE 0 "or" 1]') == "1.0"
        assert run_program('[COMPARE 0 "or" 0]') == "0.0"

    def test_compare_type_mismatch_raises(self):
        res = run_program_raw('[COMPARE 5 ">" "three"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, TypeError)

    def test_compare_invalid_operator(self):
        res = run_program_raw('[COMPARE 5 "~" 3]')
        assert isinstance(res, ExecutorResult.Error)

    def test_throw(self):
        res = run_program_raw('[THROW "boom"]')
        assert isinstance(res, ExecutorResult.Error)
        assert "boom" in str(res.exception)

    def test_comment(self):
        assert run_program('[# this is a comment]visible') == "visible"

    def test_nested_if(self):
        assert run_program('[IF [COMPARE 5 ">" 3] "bigger" "smaller"]') == "bigger"

    def test_loop_basic(self):
        assert run_program('[LOOP 3 "x"]') == "xxx"

    def test_loop_zero(self):
        assert run_program('[LOOP 0 "x"]') == ""

    def test_loop_cap(self):
        res = run_program_raw('[LOOP 4100 "x"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)
        assert "cap" in str(res.exception).lower()

    def test_loop_requires_integer_count(self):
        res = run_program_raw('[LOOP 2.5 "x"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, ValueError)

    def test_loop_negative_rejected(self):
        res = run_program_raw('[LOOP -1 "x"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, ValueError)

    def test_loop_nested_counts_against_shared_cap(self):
        out = run_program('[LOOP 4 [LOOP 4 "x"]]')
        assert out == "x" * 16

    def test_loop_shared_cap_across_nested_loops(self):
        res = run_program_raw('[LOOP 129 [LOOP 33 "x"]]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)
        assert "cap" in str(res.exception).lower()
