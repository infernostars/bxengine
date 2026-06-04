import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from bxengine.tokenizer.tokenize import Tokenizer, TokenizationResult
from bxengine.parsing.parser import Parser, ParsingResult
from bxengine.runtime.executor import Executor, ExecutorResult
from bxengine.runtime.extensions.BxeExtension import BxeExtensionBase, BxeStatefulExtension


def run_program(
    code: str,
    extensions: list[BxeExtensionBase] | None = None,
    stateful_extensions: list[type[BxeStatefulExtension]] | None = None,
    program_args: list | None = None,
) -> str:
    tok = Tokenizer.tokenize(code)
    assert isinstance(tok, TokenizationResult.Success), f"Tokenize error: {tok.message}"
    par = Parser.parse(code, tok.tokens)
    assert isinstance(par, ParsingResult.Success), f"Parse error: {par.message}"
    exe = Executor(
        extensions=extensions,
        stateful_extensions=stateful_extensions,
        program_args=program_args or [],
    )
    res = exe.execute(par.nodes)
    assert isinstance(res, ExecutorResult.Success), f"{type(res.exception).__name__}: {res.exception}"
    return res.output


def run_program_raw(
    code: str,
    extensions: list[BxeExtensionBase] | None = None,
    stateful_extensions: list[type[BxeStatefulExtension]] | None = None,
    program_args: list | None = None,
) -> ExecutorResult:
    tok = Tokenizer.tokenize(code)
    assert isinstance(tok, TokenizationResult.Success), f"Tokenize error: {tok.message}"
    par = Parser.parse(code, tok.tokens)
    assert isinstance(par, ParsingResult.Success), f"Parse error: {par.message}"
    exe = Executor(
        extensions=extensions,
        stateful_extensions=stateful_extensions,
        program_args=program_args or [],
    )
    return exe.execute(par.nodes)
