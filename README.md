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

The server publishes syntax diagnostics from the existing tokenizer/parser pipeline.

Compatibility warnings are also reported for accepted-but-suspicious syntax:
- extra `]` at top-level (ignored by compat behavior)
- unclosed `[` (auto-closed at EOF)
- unterminated quoted strings (accepted as-is)

Included language features:
- completion of built-in B++ functions
- macro-aware completion (`@...`) with current-document macro names prioritized
- hover for built-in function signatures/details and macro-call symbol hints

Neovim (`lspconfig`) example:

```lua
require("lspconfig").bxengine = {
  default_config = {
    cmd = { "uv", "run", "bxengine-lsp" },
    filetypes = { "bpp", "bx" },
    root_dir = require("lspconfig.util").root_pattern("pyproject.toml", ".git"),
  },
}
require("lspconfig").bxengine.setup({})
```
