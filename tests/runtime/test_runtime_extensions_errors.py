from bxengine.runtime.executor import Executor, ExecutorResult
from bxengine.runtime.extensions.builtin import BuiltinExtension
from bxengine.runtime.extensions.BxeExtension import (
    BxeStatelessExtension,
    GlobalVariableBppExtension,
    MyBxeExtension,
    bpp_function,
)

from conftest import run_program, run_program_raw


class AliasExtension(BxeStatelessExtension):
    @staticmethod
    @bpp_function(name="ALIASBASE", aliases=["AB", "alias_base"])
    def alias_target() -> str:
        return "alias-ok"


class KeywordOnlyContextExtension(BxeStatelessExtension):
    @staticmethod
    @bpp_function()
    def ctxarg_count(*args, context) -> int:
        context.local_variables["_ctx_seen"] = True
        return len(args)


class TestExtensions:
    def test_executor_registers_builtins_by_default(self):
        assert run_program("[MATH 2 + 3]") == "5"

    def test_stateless_extension(self):
        exts = [BuiltinExtension(), MyBxeExtension()]
        assert run_program("[test_basic]", extensions=exts) == "1"

    def test_stateless_args(self):
        exts = [BuiltinExtension(), MyBxeExtension()]
        assert run_program("[test_args 5]", extensions=exts) == "10"

    def test_stateless_float_coercion(self):
        exts = [BuiltinExtension(), MyBxeExtension()]
        assert run_program("[test_argsfloat 2.5]", extensions=exts) == "5.0"

    def test_stateless_int_to_float_coercion(self):
        exts = [BuiltinExtension(), MyBxeExtension()]
        assert run_program("[test_argsfloat 3]", extensions=exts) == "6.0"

    def test_node_transformer_extension(self):
        exts = [BuiltinExtension(), MyBxeExtension()]
        assert run_program("[test_nodetransform]", extensions=exts) == "1"

    def test_function_alias_primary_name(self):
        exts = [BuiltinExtension(), AliasExtension()]
        assert run_program("[ALIASBASE]", extensions=exts) == "alias-ok"

    def test_function_alias_short_alias(self):
        exts = [BuiltinExtension(), AliasExtension()]
        assert run_program("[AB]", extensions=exts) == "alias-ok"

    def test_function_alias_case_insensitive_alias(self):
        exts = [BuiltinExtension(), AliasExtension()]
        assert run_program("[alias_base]", extensions=exts) == "alias-ok"

    def test_keyword_only_context_injection_with_variadic_args(self):
        exts = [BuiltinExtension(), KeywordOnlyContextExtension()]
        assert run_program("[ctxarg_count a b c]", extensions=exts) == "3"

    def test_global_variable_extension(self):
        assert (
            run_program(
                '[GLOBAL DEFINE x 42] [GLOBAL VAR x]',
                stateful_extensions=[GlobalVariableBppExtension],
            ).strip()
            == "42"
        )

    def test_stateful_isolation_between_executions(self):
        exe = Executor(
            extensions=[BuiltinExtension()],
            stateful_extensions=[GlobalVariableBppExtension],
        )
        from bxengine.tokenizer.tokenize import Tokenizer
        from bxengine.parsing.parser import Parser

        tok1 = Tokenizer.tokenize('[GLOBAL DEFINE x 99]')
        par1 = Parser.parse('[GLOBAL DEFINE x 99]', tok1.tokens)
        r1 = exe.execute(par1.nodes)
        assert isinstance(r1, ExecutorResult.Success)

        tok2 = Tokenizer.tokenize("[GLOBAL VAR x]")
        par2 = Parser.parse("[GLOBAL VAR x]", tok2.tokens)
        r2 = exe.execute(par2.nodes)
        assert isinstance(r2, ExecutorResult.Error)

    def test_stateful_exposed_on_result(self):
        exe = Executor(
            extensions=[BuiltinExtension()],
            stateful_extensions=[GlobalVariableBppExtension],
        )
        from bxengine.tokenizer.tokenize import Tokenizer
        from bxengine.parsing.parser import Parser

        tok = Tokenizer.tokenize('[GLOBAL DEFINE name "Alice"]')
        par = Parser.parse('[GLOBAL DEFINE name "Alice"]', tok.tokens)
        result = exe.execute(par.nodes)
        assert isinstance(result, ExecutorResult.Success)
        gv_exts = [e for e in result.stateful_extensions if isinstance(e, GlobalVariableBppExtension)]
        assert len(gv_exts) == 1
        assert gv_exts[0].global_variables == {"name": "Alice"}


class TestErrors:
    def test_undefined_function(self):
        res = run_program_raw("[NOSUCHFUNC 1]")
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, NameError)

    def test_type_error_propagates(self):
        res = run_program_raw('[ABS "hello"]')
        assert isinstance(res, ExecutorResult.Error)
        assert isinstance(res.exception, ValueError)

    def test_unclosed_bracket(self):
        # BPPCOMPAT: unclosed brackets at EOF are auto-closed by parser
        from bxengine.tokenizer.tokenize import Tokenizer, TokenizationResult
        from bxengine.parsing.parser import Parser, ParsingResult

        tok = Tokenizer.tokenize("[FUNC")
        assert isinstance(tok, TokenizationResult.Success)
        par = Parser.parse("[FUNC", tok.tokens)
        assert isinstance(par, ParsingResult.Success)

    def test_tokenize_unclosed_string_at_top_level(self):
        # Top-level unclosed quotes get absorbed as outer text (BPPCOMPAT)
        from bxengine.tokenizer.tokenize import Tokenizer, TokenizationResult

        res = Tokenizer.tokenize('"unclosed')
        assert isinstance(res, TokenizationResult.Success)
