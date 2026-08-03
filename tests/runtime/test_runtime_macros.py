from bxengine.exceptions import BxeRuntimeException
from bxengine.runtime.executor import ExecutorResult

from conftest import run_program, run_program_raw


class TestMacros:
    def test_macro_param_basic(self):
        code = '[MACRO "thing" [ARRAY "param1"] [PARAM param1]] [@thing 1]'
        assert run_program(code) == " 1"

    def test_macro_with_implicit_return(self):
        code = '[MACRO macro2 [ARRAY] "this is implicitly returned"] [@macro2]'
        assert run_program(code) == " this is implicitly returned"

    def test_param_outside_macro_raises(self):
        res = run_program_raw("[PARAM x]")
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)

    def test_return_function_does_not_exist(self):
        res = run_program_raw('[RETURN "x"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, NameError)

    def test_macro_direct_recursion_is_blocked(self):
        res = run_program_raw('[MACRO a [ARRAY] [@a]] [@a]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)
        assert "recursion" in str(res.exception).lower()

    def test_macro_indirect_recursion_is_blocked(self):
        res = run_program_raw('[MACRO a [ARRAY] [@b]] [MACRO b [ARRAY] [@a]] [@a]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)
        assert "recursion" in str(res.exception).lower()

    def test_macro_enforces_parameter_count(self):
        res = run_program_raw('[MACRO add1 [ARRAY "x"] [PARAM x]] [@add1]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, TypeError)

    def test_macro_optional_parameter_omitted(self):
        code = '[MACRO greet [ARRAY "name" "title?"] [CONCAT [PARAM name] ":" [PARAM title]]] [@greet "Ada"]'
        assert run_program(code) == " Ada:"

    def test_macro_optional_parameter_provided(self):
        code = '[MACRO greet [ARRAY "name" "title?"] [CONCAT [PARAM name] ":" [PARAM title]]] [@greet "Ada" "Dr"]'
        assert run_program(code) == " Ada:Dr"

    def test_macro_varargs_allowed(self):
        code = '[MACRO count [ARRAY "a" "..."] [LENGTH [PARAMS]]] [@count 1 2 3 4]'
        assert run_program(code) == " 4"

    def test_macro_varargs_callable_receives_unevaluated_nodes(self):
        code = (
            '[MACRO "twice_all" [ARRAY "prefix" "...:callable"] '
            '[CONCAT [PARAM prefix] '
            '[CALL [INDEX [PARAMS] 1]] [CALL [INDEX [PARAMS] 2]]]] '
            '[DEFINE x 0] '
            '[@twice_all "r" '
            '[CONCAT [DEFINE x [MATH [VAR x] + 1]] [VAR x]] '
            '[CONCAT [DEFINE x [MATH [VAR x] + 1]] [VAR x]]] '
            '[VAR x]'
        )
        assert run_program(code).strip() == "r12 2"

    def test_macro_varargs_without_callable_still_evaluates_eagerly(self):
        code = (
            '[MACRO "eager" [ARRAY "..."] "ok"] '
            '[@eager [THROW "regular vararg evaluated"]]'
        )
        res = run_program_raw(code)
        assert isinstance(res, ExecutorResult.Error)
        assert "regular vararg evaluated" in str(res.exception)

    def test_macro_varargs_callable_recursion_is_blocked(self):
        code = (
            '[MACRO "run" [ARRAY "...:callable"] [CALL [INDEX [PARAMS] 0]]] '
            '[@run [CALL [INDEX [PARAMS] 0]]]'
        )
        res = run_program_raw(code)
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)

    def test_macro_callable_parameter_receives_unevaluated_node(self):
        code = (
            '[MACRO "twice" [ARRAY "body:callable"] '
            '[CONCAT [CALL [PARAM body]] [CALL [PARAM body]]]] '
            '[DEFINE x 0] '
            '[@twice [CONCAT [DEFINE x [MATH [VAR x] + 1]] [VAR x]]]'
        )
        assert run_program(code).strip() == "12"

    def test_macro_optional_callable_parameter(self):
        code = (
            '[MACRO "maybe" [ARRAY "body?:callable"] '
            '[IF [COMPARE [PARAM body] != ""] [CALL [PARAM body]] "missing"]] '
            '[@maybe]'
        )
        assert run_program(code).strip() == "missing"

    def test_macro_callable_parameter_can_be_forwarded_through_call(self):
        code = (
            '[MACRO "inner" [ARRAY "body:callable"] [CALL [PARAM body]]] '
            '[MACRO "outer" [ARRAY "body:callable"] '
            '[CALL "@inner" [ARRAY [PARAM body]]]] '
            '[DEFINE x 0] '
            '[@outer [CONCAT [DEFINE x 1] [VAR x]]]'
        )
        assert run_program(code).strip() == "1"

    def test_macro_callable_custom_if_only_runs_true_branch(self):
        code = (
            '[MACRO "customif" [ARRAY "condition" "true_branch:callable" "false_branch:callable"] '
            '[IF [PARAM condition] [CALL [PARAM true_branch]] [CALL [PARAM false_branch]]]] '
            '[@customif 1 "chosen" [THROW "false branch ran"]]'
        )
        assert run_program(code).strip() == "chosen"

    def test_macro_callable_custom_if_only_runs_false_branch(self):
        code = (
            '[MACRO "customif" [ARRAY "condition" "true_branch:callable" "false_branch:callable"] '
            '[IF [PARAM condition] [CALL [PARAM true_branch]] [CALL [PARAM false_branch]]]] '
            '[@customif 0 [THROW "true branch ran"] "chosen"]'
        )
        assert run_program(code).strip() == "chosen"

    def test_macro_non_callable_parameter_still_evaluates_before_body(self):
        code = (
            '[MACRO "ignore" [ARRAY "body"] "ok"] '
            '[@ignore [THROW "ordinary parameter evaluated"]]'
        )
        res = run_program_raw(code)
        assert isinstance(res, ExecutorResult.Error)
        assert "ordinary parameter evaluated" in str(res.exception)

    def test_call_callable_parameter_can_replace_function_arguments(self):
        code = (
            '[MACRO "apply" [ARRAY "body:callable"] '
            '[CALL [PARAM body] [ARRAY "x" "y"]]] '
            '[@apply [CONCAT "ignored"]]'
        )
        assert run_program(code).strip() == "xy"

    def test_macro_callable_parameter_can_be_called_multiple_times_sequentially(self):
        code = (
            '[MACRO "twice" [ARRAY "body:callable"] '
            '[CONCAT [CALL [PARAM body]] [CALL [PARAM body]]]] '
            '[@twice "ok"]'
        )
        assert run_program(code).strip() == "okok"

    def test_macro_callable_parameter_recursion_is_blocked(self):
        code = (
            '[MACRO "run" [ARRAY "body:callable"] [CALL [PARAM body]]] '
            '[@run [CALL [PARAM body]]]'
        )
        res = run_program_raw(code)
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)
        assert "recursion" in str(res.exception).lower()

    def test_macro_callable_parameter_cannot_be_saved_to_variable(self):
        code = (
            '[MACRO "save" [ARRAY "body:callable"] [DEFINE saved [PARAM body]]] '
            '[@save "body"]'
        )
        res = run_program_raw(code)
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, TypeError)
        assert "callable" in str(res.exception).lower()

    def test_macro_callable_parameter_cannot_be_saved_to_variable_inside_array(self):
        code = (
            '[MACRO "save" [ARRAY "body:callable"] [DEFINE saved [ARRAY [PARAM body]]]] '
            '[@save "body"]'
        )
        res = run_program_raw(code)
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, TypeError)
        assert "callable" in str(res.exception).lower()

    def test_params_returns_all_arguments_without_varargs(self):
        code = '[MACRO count [ARRAY "a" "b?"] [LENGTH [PARAMS]]] [@count 1]'
        assert run_program(code) == " 1"

    def test_params_outside_macro_raises(self):
        res = run_program_raw("[PARAMS]")
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)

    def test_macro_varargs_marker_must_be_last(self):
        res = run_program_raw('[MACRO bad [ARRAY "..." "x"] [PARAM x]]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)

    def test_macro_without_varargs_rejects_extra_parameters(self):
        res = run_program_raw('[MACRO noextra [ARRAY "x"] [PARAM x]] [@noextra 1 2]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, TypeError)

    def test_macro_required_parameter_after_optional_is_rejected(self):
        res = run_program_raw('[MACRO bad [ARRAY "a" "b?" "c"] [PARAM a]]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)

    def test_macro_name_with_space_is_rejected(self):
        res = run_program_raw('[MACRO "bad name" [ARRAY] "x"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, NameError)

    def test_macro_name_with_unreachable_chars_is_rejected(self):
        res = run_program_raw('[MACRO "bad]name" [ARRAY] "x"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, NameError)

    def test_call_dynamic_macro_name(self):
        code = '[MACRO "thing" [ARRAY "x"] [PARAM x]] [DEFINE target "@thing"] [CALL [VAR target] [ARRAY "ok"]]'
        assert run_program(code).strip() == "ok"

    def test_call_macro_defaults_missing_arguments_to_empty_array(self):
        code = '[MACRO "thing" [ARRAY] "ok"] [CALL "@thing"]'
        assert run_program(code).strip() == "ok"

    def test_call_unknown_macro_raises(self):
        res = run_program_raw('[CALL "missing" [ARRAY]]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)

    def test_call_builtin_function(self):
        assert run_program('[CALL "CONCAT" [ARRAY "a" "b"]]') == "ab"

    def test_call_builtin_node_transformer_with_array_arguments(self):
        assert run_program('[CALL "IF" [ARRAY 1 "ok" "no"]]') == "ok"

    def test_call_builtin_name_can_be_disambiguated_from_macro(self):
        code = '[MACRO "concat" [ARRAY] "macro"] [CALL "concat" [ARRAY "a" "b"]] [CALL "@concat" [ARRAY]]'
        assert run_program(code).strip() == "ab macro"

    def test_call_requires_array_second_parameter(self):
        res = run_program_raw('[CALL "CONCAT" "a"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, TypeError)

    def test_macro_nested_call_cap_boundary(self):
        code = '[MACRO "inner" [ARRAY] "x"] [MACRO "outer" [ARRAY] [LOOP 2048 [@inner]]] [@outer] [@outer]'
        res = run_program_raw(code)

        assert isinstance(res, ExecutorResult.Success)

    def test_macro_nested_call_counter_exceeded_without_extra_depth(self):
        # Counter-based cap should apply even when nesting depth stays shallow.
        code = '[MACRO "inner" [ARRAY] "x"] [MACRO "outer" [ARRAY] [LOOP 2048 [@inner]]] [MACRO "outer2" [ARRAY] [@inner]] [@outer] [@outer] [@outer2]'
        res = run_program_raw(code)
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, BxeRuntimeException)
        assert "cap" in str(res.exception).lower()
