from bxengine.runtime.executor import ExecutorResult

from conftest import run_program, run_program_raw


class TestVariables:
    def test_define_and_var(self):
        assert run_program('[DEFINE x 42] [VAR x]') == " 42"

    def test_define_string(self):
        assert run_program('[DEFINE name "Alice"] [VAR name]') == " Alice"

    def test_var_undefined_raises(self):
        res = run_program_raw("[VAR nonexistent]")
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, NameError)

    def test_define_invalid_name(self):
        res = run_program_raw('[DEFINE "123bad" 1]')
        assert isinstance(res, ExecutorResult.Error)

    def test_define_overwrite(self):
        assert run_program('[DEFINE x 1] [DEFINE x 2] [VAR x]') == "  2"

    def test_extra_var_argument_does_not_replace_context(self):
        res = run_program_raw("[DEFINE x 1] [VAR x extra]")
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, TypeError)
        assert not isinstance(res.exception, AttributeError)
        assert "expected at most 1 parameters, but got 2" in str(res.exception)

    def test_extra_define_argument_does_not_replace_context(self):
        res = run_program_raw("[DEFINE x 1 extra]")
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, TypeError)
        assert not isinstance(res.exception, AttributeError)
        assert "expected at most 2 parameters, but got 3" in str(res.exception)


class TestArgs:
    def test_args_by_index(self):
        assert run_program("[ARGS 0] [ARGS 1]", program_args=["hello", "world"]) == "hello world"

    def test_args_all(self):
        assert run_program("[ARGS]", program_args=["a", "b", "c"]) == '[ARRAY "a" "b" "c"]'

    def test_args_out_of_range(self):
        assert run_program("[ARGS 5]", program_args=["only-one"]) == ""

    def test_args_no_args(self):
        assert run_program("[ARGS]") == "[ARRAY ]"

    def test_setargs_from_array(self):
        out = run_program('[SETARGS [ARRAY "hello" "world"]] [ARGS 0] [ARGS 1]')
        assert out == " hello world"

    def test_setargs_variadic(self):
        out = run_program("[SETARGS hello world] [ARGS]")
        assert out == ' [ARRAY "hello" "world"]'

    def test_setargs_overrides_initial_program_args(self):
        out = run_program("[SETARGS fresh] [ARGS 0]", program_args=["old"])
        assert out == " fresh"

    def test_setargs_empty_clears_program_args(self):
        out = run_program("[SETARGS] [ARGS]")
        assert out == " [ARRAY ]"
