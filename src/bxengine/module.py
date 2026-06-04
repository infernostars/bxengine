import argparse
import sys
from typing import TextIO

from bxengine.runtime.extensions.discord_stub import (
    BrainGlobalExtension,
    BrainUserExtension,
    DiscordStubExtension,
)
from bxengine.tokenizer.tokenize import Tokenizer, TokenizationResult
from bxengine.parsing.parser import Parser, ParsingResult
from bxengine.runtime.executor import Executor, ExecutorResult
from bxengine.syntax_warnings import BxeSyntaxWarning
from bxengine import __version__

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


def _print_syntax_warnings(
    warnings: tuple[BxeSyntaxWarning, ...], stderr: TextIO | None = None
) -> None:
    stderr = stderr or sys.stderr
    if not warnings:
        return
    for warning in warnings:
        print(f"Warning [{warning.source}]: {warning.message}", file=stderr)
        print("", file=stderr)
        print(warning.range.debug_info(), file=stderr)
        print("", file=stderr)


def _parse_code(
    code: str,
    *,
    debug: bool = False,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
):
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    tokenizer_res = Tokenizer.tokenize(code)
    if isinstance(tokenizer_res, TokenizationResult.Error):
        print(tokenizer_res.message, "\n\n", tokenizer_res.range.debug_info(), sep="", file=stdout)
        return None

    if debug:
        _print_syntax_warnings(tokenizer_res.warnings, stderr=stderr)

    parser_res = Parser.parse(code, tokenizer_res.tokens)
    if isinstance(parser_res, ParsingResult.Error):
        if debug:
            _print_syntax_warnings(parser_res.warnings, stderr=stderr)
        print(parser_res.message, "\n\n", parser_res.range.debug_info(), sep="", file=stdout)
        return None

    if debug:
        _print_syntax_warnings(parser_res.warnings, stderr=stderr)

    return parser_res.nodes


def _print_execution_error(exception: Exception, stderr: TextIO | None = None) -> None:
    stderr = stderr or sys.stderr
    print(type(exception).__name__ + ":", exception, file=stderr)
    span = getattr(exception, "span", None)
    if span is not None:
        print("", file=stderr)
        print(span.debug_info(), file=stderr)


def _create_cli_executor(program_args: list[str] | None = None) -> Executor:
    return Executor(
        stateful_extensions=[BrainGlobalExtension, BrainUserExtension, DiscordStubExtension],
        program_args=program_args or [],
    )


def _unclosed_bracket_count(code: str) -> int:
    depth = 0
    escaped = False
    quote: str | None = None

    for char in code:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue

        if quote is not None:
            if char in '"“”':
                quote = None
            continue

        if char in '"“”':
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]" and depth > 0:
            depth -= 1

    return depth


def run_code(code: str, program_args: list[str] | None = None, debug: bool = False) -> None:
    nodes = _parse_code(code, debug=debug)
    if nodes is None:
        return

    executor = _create_cli_executor(program_args)
    result = executor.execute(nodes)

    if isinstance(result, ExecutorResult.Error):
        _print_execution_error(result.exception)
        sys.exit(1)
    else:
        print(result.output.strip(), end="\n")


def run_repl(
    program_args: list[str] | None = None,
    debug: bool = False,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    executor = _create_cli_executor(program_args)
    session = executor.create_session()
    interactive = stdin.isatty()
    buffered_lines: list[str] = []
    if interactive:
        print(f"bxengine {__version__} REPL. type .exit to exit.", file=stdout)

    while True:
        if interactive:
            prompt = "...> " if buffered_lines else "bpp> "
            print(prompt, end="", file=stdout, flush=True)
        line = stdin.readline()
        if line == "":
            if interactive:
                print("", file=stdout)
            break

        line = line.rstrip("\n")
        if not buffered_lines and line.strip() in {".exit", ".quit"}:
            break
        if not buffered_lines and line.strip() == "":
            continue

        buffered_lines.append(line)
        code = "\n".join(buffered_lines)
        if _unclosed_bracket_count(code) > 0:
            continue
        buffered_lines.clear()

        nodes = _parse_code(code, debug=debug, stdout=stdout, stderr=stderr)
        if nodes is None:
            continue

        result = executor.execute_in_session(nodes, session)
        if isinstance(result, ExecutorResult.Error):
            _print_execution_error(result.exception, stderr=stderr)
            continue

        output = result.output.strip()
        if output:
            print(output, file=stdout)


def _module_main():
    parser = argparse.ArgumentParser(prog="bxengine", description="B++ runtime engine")
    parser.add_argument("file", nargs="?", help="Path to a .bx script file")
    parser.add_argument("-e", "--eval", metavar="CODE", help="Execute a string of B++ code")
    parser.add_argument("-d", "--debug", action="store_true", help="Show syntax compatibility warnings")
    parser.add_argument(
        "-i",
        "--repl",
        action="store_true",
        help="Start an interactive REPL (default when no file or --eval is provided)",
    )
    parser.add_argument("args", nargs="*", help="Arguments passed to the script (accessible via ARGS)")

    parsed = parser.parse_args()

    if parsed.repl or (not parsed.eval and not parsed.file):
        if parsed.eval:
            parser.error("--repl cannot be used with --eval")
        repl_args = ([parsed.file] if parsed.file else []) + parsed.args
        run_repl(repl_args, debug=parsed.debug)
    elif parsed.eval:
        run_code(parsed.eval, parsed.args, debug=parsed.debug)
    elif parsed.file:
        with open(parsed.file) as f:
            run_code(f.read(), parsed.args, debug=parsed.debug)
    else:
        run_code(DEFAULT_TEST, parsed.args, debug=parsed.debug)
