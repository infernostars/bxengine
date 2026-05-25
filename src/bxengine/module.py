import argparse
import sys

from bxengine.runtime.extensions.discord_stub import (
    BrainGlobalExtension,
    BrainUserExtension,
    DiscordStubExtension,
)
from bxengine.tokenizer.tokenize import Tokenizer, TokenizationResult
from bxengine.parsing.parser import Parser, ParsingResult
from bxengine.runtime.executor import Executor, ExecutorResult
from bxengine.runtime.extensions.builtin import BuiltinExtension
from bxengine.syntax_warnings import BxeSyntaxWarning


DEFAULT_TEST = """
[GLOBAL DEFINE descentNumber 100]
[GLOBAL DEFINE descentAttempts 0]
[GLOBAL DEFINE descentHighscore 15]

[DEFINE number [GLOBAL VAR descentNumber]]
[DEFINE attempts [GLOBAL VAR descentAttempts]]
[DEFINE nextNumber [RANDINT 0 [MATH [VAR number] + 1]]]
[IF [COMPARE [VAR nextNumber] != 0] [CONCAT "The number has gone from **" [VAR number] "** to **" [VAR nextNumber] "**. The current number of tries in this run is **" [MATH [VAR attempts] + 1] "**!
" [IF [COMPARE [GLOBAL VAR descentHighscore] < [MATH [VAR attempts] + 1]] [CONCAT "You've successfully beaten the highscore of **" [GLOBAL VAR descentHighscore] "**, but you're still going! Good luck!"] [CONCAT "The highscore to beat is **" [GLOBAL VAR descentHighscore] "**."]]] [CONCAT "Uh oh, looks like this run has finally come to an end! You had **" [MATH [VAR attempts] + 1] "** attempts.
" [IF [COMPARE [GLOBAL VAR descentHighscore] < [MATH [VAR atoh
yetempts] + 1]] [CONCAT "But I'm pleased to say you beat the highscore of **" [GLOBAL VAR descentHighscore] "** with your new score of **" [MATH [VAR attempts] + 1] "**! Well done!"] [CONCAT "Unfortunately, you failed to beat the highscore of **" [GLOBAL VAR descentHighscore] "**. I'm sure next attempt will be more promising, though."]]]]
[IF [COMPARE [VAR nextNumber] != 0] [CONCAT [GLOBAL DEFINE descentAttempts [MATH [VAR attempts] + 1]] [GLOBAL DEFINE descentNumber [VAR nextNumber]]] [CONCAT [IF [COMPARE [GLOBAL VAR descentHighscore] < [MATH [VAR attempts] + 1]] [GLOBAL DEFINE descentHighscore [MATH [VAR attempts] + 1]]] [GLOBAL DEFINE descentAttempts 0] [GLOBAL DEFINE descentNumber 100]]
"""


def _print_syntax_warnings(warnings: tuple[BxeSyntaxWarning, ...]) -> None:
    if not warnings:
        return
    for warning in warnings:
        print(f"Warning [{warning.source}]: {warning.message}", file=sys.stderr)
        print("", file=sys.stderr)
        print(warning.range.debug_info(), file=sys.stderr)
        print("", file=sys.stderr)


def run_code(code: str, program_args: list[str] | None = None, debug: bool = False) -> None:
    tokenizer_res = Tokenizer.tokenize(code)
    if isinstance(tokenizer_res, TokenizationResult.Error):
        print(tokenizer_res.message, "\n\n", tokenizer_res.range.debug_info(), sep="")
        return

    if debug:
        _print_syntax_warnings(tokenizer_res.warnings)

    parser_res = Parser.parse(code, tokenizer_res.tokens)
    if isinstance(parser_res, ParsingResult.Error):
        if debug:
            _print_syntax_warnings(parser_res.warnings)
        print(parser_res.message, "\n\n", parser_res.range.debug_info(), sep="")
        return

    if debug:
        _print_syntax_warnings(parser_res.warnings)

    executor = Executor(
        extensions=[BuiltinExtension()],
        stateful_extensions=[BrainGlobalExtension, BrainUserExtension, DiscordStubExtension],
        program_args=program_args or [],
    )
    result = executor.execute(parser_res.nodes)

    if isinstance(result, ExecutorResult.Error):
        exception = result.exception
        print(type(exception).__name__ + ":", exception, file=sys.stderr)
        span = getattr(exception, "span", None)
        if span is not None:
            print("", file=sys.stderr)
            print(span.debug_info(), file=sys.stderr)
        sys.exit(1)
    else:
        print(result.output.strip(), end="\n")


def _module_main():
    parser = argparse.ArgumentParser(prog="bxengine", description="B++ runtime engine")
    parser.add_argument("file", nargs="?", help="Path to a .bx script file")
    parser.add_argument("-e", "--eval", metavar="CODE", help="Execute a string of B++ code")
    parser.add_argument("-d", "--debug", action="store_true", help="Show syntax compatibility warnings")
    parser.add_argument("args", nargs="*", help="Arguments passed to the script (accessible via ARGS)")

    parsed = parser.parse_args()

    if parsed.eval:
        run_code(parsed.eval, parsed.args, debug=parsed.debug)
    elif parsed.file:
        with open(parsed.file) as f:
            run_code(f.read(), parsed.args, debug=parsed.debug)
    else:
        run_code(DEFAULT_TEST, parsed.args, debug=parsed.debug)
