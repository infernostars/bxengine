import io
import sys

import bxengine.module
from bxengine.module import _module_main, _unclosed_bracket_count, run_code, run_repl


def test_run_code_debug_prints_compat_warnings(capsys):
    run_code("hello ]", debug=True)
    captured = capsys.readouterr()
    assert "Warning [bxengine-compat]" in captured.err
    assert "ignored at top level" in captured.err


def test_run_code_without_debug_hides_compat_warnings(capsys):
    run_code("hello ]", debug=False)
    captured = capsys.readouterr()
    assert "Warning [bxengine-compat]" not in captured.err


def test_repl_persists_variables_between_inputs():
    stdin = io.StringIO('[DEFINE x 40]\n[MATH [VAR x] + 2]\n.exit\n')
    stdout = io.StringIO()
    stderr = io.StringIO()

    run_repl(stdin=stdin, stdout=stdout, stderr=stderr)

    assert stdout.getvalue().strip() == "42"
    assert stderr.getvalue() == ""


def test_repl_accepts_multiline_input_until_brackets_close():
    stdin = io.StringIO('[DEFINE x [CONCAT "a"\n"b"]]\n[VAR x]\n.exit\n')
    stdout = io.StringIO()
    stderr = io.StringIO()

    run_repl(stdin=stdin, stdout=stdout, stderr=stderr)

    assert stdout.getvalue().strip() == "ab"
    assert stderr.getvalue() == ""


def test_repl_reports_errors_and_continues():
    stdin = io.StringIO('[NOSUCHFUNC]\nok\n.exit\n')
    stdout = io.StringIO()
    stderr = io.StringIO()

    run_repl(stdin=stdin, stdout=stdout, stderr=stderr)

    assert stdout.getvalue().strip() == "ok"
    assert "NameError:" in stderr.getvalue()


def test_module_main_repl_flag(monkeypatch):
    calls = []

    def fake_run_repl(program_args=None, debug=False):
        calls.append((program_args, debug))

    monkeypatch.setattr(sys, "argv", ["bxengine", "--repl", "arg1", "arg2"])
    monkeypatch.setattr(bxengine.module, "run_repl", fake_run_repl)

    _module_main()

    assert calls == [(["arg1", "arg2"], False)]


def test_module_main_defaults_to_repl_without_file_or_eval(monkeypatch):
    calls = []

    def fake_run_repl(program_args=None, debug=False):
        calls.append((program_args, debug))

    monkeypatch.setattr(sys, "argv", ["bxengine"])
    monkeypatch.setattr(bxengine.module, "run_repl", fake_run_repl)

    _module_main()

    assert calls == [([], False)]


def test_repl_bracket_balance_ignores_quoted_and_escaped_brackets():
    assert _unclosed_bracket_count('[CONCAT "[" "\\]"]') == 0
    assert _unclosed_bracket_count(r'[CONCAT \[ \]]') == 0
    assert _unclosed_bracket_count("[CONCAT [LOWER A]") == 1
