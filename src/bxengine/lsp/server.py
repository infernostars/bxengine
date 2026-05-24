from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from bxengine.lsp.diagnostics import Diagnostic, collect_diagnostics
from bxengine.lsp.functions import get_function_catalog
from bxengine.parsing.nodes import Node, Nodes
from bxengine.parsing.parser import Parser, ParsingResult
from bxengine.tokenizer.tokenize import TokenizationResult, Tokenizer

LSP_VERSION = "0.1.0"
SUPPORTED_LANGUAGE_IDS = {"bpp", "bx", "b++", "bxengine"}
SUPPORTED_SUFFIXES = {".bpp", ".bx", ".b++"}


@dataclass
class OpenDocument:
    uri: str
    text: str
    version: int | None
    language_id: str


class BxLanguageServer:
    def __init__(self) -> None:
        self._documents: dict[str, OpenDocument] = {}
        self._is_shutdown = False

    def run(self) -> None:
        while True:
            message = _read_lsp_message()
            if message is None:
                break

            method = message.get("method")
            if method is None:
                continue

            msg_id = message.get("id")
            params = message.get("params", {})

            if method == "initialize":
                self._handle_initialize(msg_id)
            elif method == "initialized":
                continue
            elif method == "shutdown":
                self._handle_shutdown(msg_id)
            elif method == "exit":
                return
            elif self._is_shutdown:
                if msg_id is not None:
                    _send_error(msg_id, code=-32600, message="Server is shut down.")
            elif method == "textDocument/didOpen":
                self._handle_did_open(params)
            elif method == "textDocument/didChange":
                self._handle_did_change(params)
            elif method == "textDocument/didSave":
                self._handle_did_save(params)
            elif method == "textDocument/didClose":
                self._handle_did_close(params)
            elif method == "textDocument/completion":
                self._handle_completion(msg_id, params)
            elif method == "textDocument/hover":
                self._handle_hover(msg_id, params)
            elif msg_id is not None:
                _send_error(msg_id, code=-32601, message=f"Method not found: {method}")

    def _handle_initialize(self, msg_id: Any) -> None:
        result = {
            "capabilities": {
                "textDocumentSync": {
                    "openClose": True,
                    "change": 1,
                    "save": {"includeText": True},
                },
                "completionProvider": {"triggerCharacters": ["[", "@"]},
                "hoverProvider": True,
            },
            "serverInfo": {
                "name": "bxengine-lsp",
                "version": LSP_VERSION,
            },
        }
        _send_response(msg_id, result)

    def _handle_shutdown(self, msg_id: Any) -> None:
        self._is_shutdown = True
        _send_response(msg_id, None)

    def _handle_did_open(self, params: dict[str, Any]) -> None:
        text_doc = params.get("textDocument", {})
        uri = str(text_doc.get("uri", ""))
        text = str(text_doc.get("text", ""))
        language_id = str(text_doc.get("languageId", ""))
        version = _optional_int(text_doc.get("version"))

        self._documents[uri] = OpenDocument(
            uri=uri,
            text=text,
            version=version,
            language_id=language_id,
        )
        self._publish_diagnostics(uri)

    def _handle_did_change(self, params: dict[str, Any]) -> None:
        text_doc = params.get("textDocument", {})
        uri = str(text_doc.get("uri", ""))
        version = _optional_int(text_doc.get("version"))

        doc = self._documents.get(uri)
        if doc is None:
            doc = OpenDocument(uri=uri, text="", version=version, language_id="")
            self._documents[uri] = doc

        content_changes = params.get("contentChanges", [])
        if content_changes:
            # Server advertises full sync, so this should be the entire file content.
            latest = content_changes[-1]
            if isinstance(latest, dict) and "text" in latest:
                doc.text = str(latest.get("text", ""))
        doc.version = version

        self._publish_diagnostics(uri)

    def _handle_did_save(self, params: dict[str, Any]) -> None:
        text_doc = params.get("textDocument", {})
        uri = str(text_doc.get("uri", ""))
        text = params.get("text")
        if text is not None and uri in self._documents:
            self._documents[uri].text = str(text)

        self._publish_diagnostics(uri)

    def _handle_did_close(self, params: dict[str, Any]) -> None:
        text_doc = params.get("textDocument", {})
        uri = str(text_doc.get("uri", ""))
        self._documents.pop(uri, None)
        _publish_diagnostics(uri, None, [])

    def _publish_diagnostics(self, uri: str) -> None:
        doc = self._documents.get(uri)
        if doc is None:
            return

        if not _is_supported_document(uri=doc.uri, language_id=doc.language_id):
            _publish_diagnostics(uri, doc.version, [])
            return

        diagnostics = collect_diagnostics(doc.text)
        _publish_diagnostics(uri, doc.version, diagnostics)

    def _handle_completion(self, msg_id: Any, params: dict[str, Any]) -> None:
        text_document = params.get("textDocument", {})
        position = params.get("position", {})
        uri = str(text_document.get("uri", ""))
        line = _optional_int(position.get("line"))
        character = _optional_int(position.get("character"))

        doc = self._documents.get(uri)
        source = doc.text if doc is not None else ""
        offset = 0 if line is None or character is None else position_to_offset(
            source,
            line=line,
            character_utf16=character,
        )
        prefix = completion_prefix_at(source, offset)
        replace_start, replace_end = completion_span_at(source, offset)
        replace_range = _offset_range(source, replace_start, replace_end)
        macro_context = prefix.startswith("@")
        declared_macros = _declared_macros(source) if macro_context else ()

        items = []
        for i, macro in enumerate(declared_macros):
            items.append(
                {
                    "label": macro,
                    "kind": 3,  # Function
                    "detail": f"[{macro} ...]",
                    "insertText": macro,
                    "textEdit": {
                        "range": replace_range,
                        "newText": macro,
                    },
                    "sortText": f"0000_{i:04d}_{macro}",
                    "preselect": i == 0,
                    "documentation": {
                        "kind": "markdown",
                        "value": f"`[{macro} ...]`\n\nMacro declared in this document.",
                    },
                }
            )

        function_items = [
            {
                "label": info.name,
                "kind": 3,  # Function
                "detail": info.signature,
                "insertText": info.name,
                "textEdit": {
                    "range": replace_range,
                    "newText": info.name,
                },
                "sortText": f"{'1000' if macro_context else '0000'}_{info.name}",
                "documentation": {
                    "kind": "markdown",
                    "value": _function_doc_markdown(info),
                },
            }
            for info in get_function_catalog()
        ]
        items.extend(function_items)
        _send_response(msg_id, {"isIncomplete": False, "items": items})

    def _handle_hover(self, msg_id: Any, params: dict[str, Any]) -> None:
        text_document = params.get("textDocument", {})
        position = params.get("position", {})
        uri = str(text_document.get("uri", ""))
        line = _optional_int(position.get("line"))
        character = _optional_int(position.get("character"))

        if line is None or character is None:
            _send_response(msg_id, None)
            return

        doc = self._documents.get(uri)
        if doc is None:
            _send_response(msg_id, None)
            return

        offset = position_to_offset(doc.text, line=line, character_utf16=character)
        symbol, start_offset, end_offset = word_at_offset(doc.text, offset)
        if not symbol:
            _send_response(msg_id, None)
            return

        catalog = {info.name: info for info in get_function_catalog()}
        info = catalog.get(symbol.upper())
        if info is None and symbol.startswith("@"):
            value = (
                f"`{symbol}`\n\n"
                "Macro call symbol. Macros are defined at runtime via `MACRO` and invoked as `@NAME`."
            )
            _send_response(
                msg_id,
                {
                    "contents": {"kind": "markdown", "value": value},
                    "range": _offset_range(doc.text, start_offset, end_offset),
                },
            )
            return

        if info is None:
            _send_response(msg_id, None)
            return

        value = _function_doc_markdown(info)
        _send_response(
            msg_id,
            {
                "contents": {"kind": "markdown", "value": value},
                "range": _offset_range(doc.text, start_offset, end_offset),
            },
        )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_supported_document(uri: str, language_id: str) -> bool:
    normalized_id = language_id.strip().lower()
    if normalized_id in SUPPORTED_LANGUAGE_IDS:
        return True

    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return False
    suffix = PurePosixPath(unquote(parsed.path)).suffix.lower()
    return suffix in SUPPORTED_SUFFIXES


def _publish_diagnostics(uri: str, version: int | None, diagnostics: list[Diagnostic]) -> None:
    payload: dict[str, Any] = {
        "uri": uri,
        "diagnostics": [diagnostic_to_lsp(diagnostic) for diagnostic in diagnostics],
    }
    if version is not None:
        payload["version"] = version
    _send_notification("textDocument/publishDiagnostics", payload)


def _offset_range(source: str, start_offset: int, end_offset: int) -> dict[str, Any]:
    return {
        "start": _offset_position(source, start_offset),
        "end": _offset_position(source, end_offset),
    }


def _function_doc_markdown(info: Any) -> str:
    parts = [f"`{info.signature}`"]
    if info.documentation_markdown:
        parts.append(info.documentation_markdown)
    return "\n\n".join(parts)


def _offset_position(source: str, offset: int) -> dict[str, int]:
    offset = max(0, min(offset, len(source)))
    line = source.count("\n", 0, offset)
    line_start = source.rfind("\n", 0, offset)
    if line_start == -1:
        line_start = 0
    else:
        line_start += 1
    prefix = source[line_start:offset]
    character_utf16 = len(prefix.encode("utf-16-le")) // 2
    return {"line": line, "character": character_utf16}


def position_to_offset(source: str, line: int, character_utf16: int) -> int:
    if line < 0:
        return 0
    if character_utf16 < 0:
        character_utf16 = 0

    current_line = 0
    offset = 0
    source_len = len(source)
    while current_line < line and offset < source_len:
        newline_idx = source.find("\n", offset)
        if newline_idx == -1:
            return source_len
        offset = newline_idx + 1
        current_line += 1

    line_end = source.find("\n", offset)
    if line_end == -1:
        line_end = source_len

    current_utf16 = 0
    idx = offset
    while idx < line_end:
        ch = source[idx]
        ch_units = len(ch.encode("utf-16-le")) // 2
        if current_utf16 + ch_units > character_utf16:
            break
        current_utf16 += ch_units
        idx += 1

    return idx


def _is_symbol_char(ch: str) -> bool:
    return ch.isalnum() or ch in "_@#/"


def word_at_offset(source: str, offset: int) -> tuple[str, int, int]:
    if not source:
        return ("", 0, 0)
    offset = max(0, min(offset, len(source)))
    if offset == len(source) and offset > 0:
        offset -= 1

    if offset < len(source) and not _is_symbol_char(source[offset]) and offset > 0 and _is_symbol_char(source[offset - 1]):
        offset -= 1
    if not _is_symbol_char(source[offset]):
        return ("", offset, offset)

    start = offset
    end = offset + 1
    while start > 0 and _is_symbol_char(source[start - 1]):
        start -= 1
    while end < len(source) and _is_symbol_char(source[end]):
        end += 1
    return (source[start:end], start, end)


def completion_prefix_at(source: str, offset: int) -> str:
    if not source:
        return ""

    offset = max(0, min(offset, len(source)))
    start = offset
    while start > 0 and _is_symbol_char(source[start - 1]):
        start -= 1
    return source[start:offset]


def completion_span_at(source: str, offset: int) -> tuple[int, int]:
    if not source:
        return (0, 0)

    offset = max(0, min(offset, len(source)))
    start = offset
    while start > 0 and _is_symbol_char(source[start - 1]):
        start -= 1
    return (start, offset)


def _declared_macros(source: str) -> tuple[str, ...]:
    tok = Tokenizer.tokenize(source)
    if isinstance(tok, TokenizationResult.Error):
        return ()

    parsed = Parser.parse(source, tok.tokens)
    if isinstance(parsed, ParsingResult.Error):
        return ()

    names: list[str] = []
    seen: set[str] = set()
    for node in parsed.nodes:
        for macro in _collect_declared_macros_from_node(node):
            if macro not in seen:
                seen.add(macro)
                names.append(macro)
    return tuple(names)


def _collect_declared_macros_from_node(node: Node) -> tuple[str, ...]:
    found: list[str] = []
    stack = [node]

    while stack:
        current = stack.pop()
        if isinstance(current, Nodes.Function):
            if current.name.upper() == "MACRO" and current.arguments:
                name_node = current.arguments[0]
                if isinstance(name_node, Nodes.StringNode):
                    name = name_node.value.strip()
                    if name:
                        if name.startswith("@"):
                            name = name[1:]
                        found.append(f"@{name.upper()}")
            for arg in reversed(current.arguments):
                stack.append(arg)
    return tuple(found)


def diagnostic_to_lsp(diagnostic: Diagnostic) -> dict[str, Any]:
    return {
        "range": {
            "start": {
                "line": diagnostic.range.start.line,
                "character": diagnostic.range.start.character,
            },
            "end": {
                "line": diagnostic.range.end.line,
                "character": diagnostic.range.end.character,
            },
        },
        "severity": diagnostic.severity,
        "message": diagnostic.message,
        "source": diagnostic.source,
    }


def _read_lsp_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None

        stripped = line.strip()
        if not stripped:
            break

        decoded = line.decode("ascii", errors="replace")
        if ":" not in decoded:
            continue
        name, value = decoded.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    content_length = headers.get("content-length")
    if content_length is None:
        return None

    try:
        size = int(content_length)
    except ValueError:
        return None

    body = sys.stdin.buffer.read(size)
    if not body:
        return None

    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _send_response(msg_id: Any, result: Any) -> None:
    payload = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    _write_lsp_message(payload)


def _send_error(msg_id: Any, code: int, message: str) -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {
            "code": code,
            "message": message,
        },
    }
    _write_lsp_message(payload)


def _send_notification(method: str, params: dict[str, Any]) -> None:
    payload = {"jsonrpc": "2.0", "method": method, "params": params}
    _write_lsp_message(payload)


def _write_lsp_message(payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def main() -> None:
    server = BxLanguageServer()
    server.run()
