from bxengine.module import run_code


def test_run_code_debug_prints_compat_warnings(capsys):
    run_code("hello ]", debug=True)
    captured = capsys.readouterr()
    assert "Warning [bxengine-compat]" in captured.err
    assert "ignored at top level" in captured.err


def test_run_code_without_debug_hides_compat_warnings(capsys):
    run_code("hello ]", debug=False)
    captured = capsys.readouterr()
    assert "Warning [bxengine-compat]" not in captured.err
