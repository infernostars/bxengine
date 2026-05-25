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
