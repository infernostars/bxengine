import bxengine.lsp.server as lsp_server
from bxengine.lsp.server import BxLanguageServer, OpenDocument


def test_completion_prioritizes_declared_macros_in_macro_context(monkeypatch):
    uri = "file:///tmp/example.bpp"
    source = '[MACRO "foo" [ARRAY] "ok"] [MACRO "@bar" [ARRAY] "ok"] @'

    ls = BxLanguageServer()
    ls._documents[uri] = OpenDocument(uri=uri, text=source, version=1, language_id="bpp")

    captured: dict[str, object] = {}

    def _capture_response(msg_id, result):
        captured["id"] = msg_id
        captured["result"] = result

    monkeypatch.setattr(lsp_server, "_send_response", _capture_response)
    ls._handle_completion(
        7,
        {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": len(source)},
        },
    )

    assert captured["id"] == 7
    result = captured["result"]
    assert isinstance(result, dict)
    items = result["items"]
    assert items[0]["label"] == "@FOO"
    assert items[1]["label"] == "@BAR"
    assert items[0]["sortText"].startswith("0000_")
    concat_item = next(item for item in items if item["label"] == "CONCAT")
    assert concat_item["sortText"].startswith("1000_")


def test_completion_defaults_to_builtin_order_outside_macro_context(monkeypatch):
    uri = "file:///tmp/example.bpp"
    source = "[CON"

    ls = BxLanguageServer()
    ls._documents[uri] = OpenDocument(uri=uri, text=source, version=1, language_id="bpp")

    captured: dict[str, object] = {}

    def _capture_response(msg_id, result):
        captured["id"] = msg_id
        captured["result"] = result

    monkeypatch.setattr(lsp_server, "_send_response", _capture_response)
    ls._handle_completion(
        8,
        {
            "textDocument": {"uri": uri},
            "position": {"line": 0, "character": len(source)},
        },
    )

    result = captured["result"]
    assert isinstance(result, dict)
    items = result["items"]
    assert not items[0]["label"].startswith("@")
    assert items[0]["sortText"].startswith("0000_")

