# bxengine

`bxengine` is a Python implementation of the B++ runtime engine.

## Install

```bash
pip install bxengine
```

## CLI

Run a file:

```bash
bxengine path/to/program.bx
```

Run inline code:

```bash
bxengine -e "[CONCAT \"hello\" \" world\"]"
```

## Development

```bash
uv sync --dev
pytest
```

## Language Server

Start the LSP server over stdio:

```bash
uv run bxengine-lsp
```