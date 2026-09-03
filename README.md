# Python Programs

A collection of standalone Python utilities for macOS.

## Programs

| File | Purpose | Usage | Output |
|------|---------|-------|--------|
| `consolidate_model_keys.py` | Scan macOS for AI-model / API keys across shell profiles, `.env` files, and AI agent config directories; identify the provider and consuming agent for each key; export a consolidated Excel spreadsheet. | `python3 consolidate_model_keys.py [--full] [--out PATH]` | `~/Desktop/model_keys_review.xlsx` (masked by default; `--full` for raw values, file set to `chmod 600`) |

## Details

### consolidate_model_keys.py

As developers increasingly work with multiple AI providers (OpenAI, Anthropic, Google Gemini, DeepSeek, etc.) and AI coding agents (Claude Code, Cursor, Codex, Hermes, Cline, etc.), API keys end up scattered across shell profiles, environment files, agent config directories, and JSON credential stores. This tool solves the "where did I put that key?" problem by:

1. **Scanning** ~20 well-known locations under `$HOME` for anything that looks like an API key, token, or secret.
2. **Identifying the provider** (30+ supported) based on the variable name and value pattern.
3. **Attributing each key to an agent/application** by cross-referencing installed AI coding agents, config-file references, and provider-prefix heuristics.
4. **Exporting a formatted Excel file** with key name, provider, consuming agent, source file, line number, and value — all in one place.

**Scanned locations** include: `.zshrc`, `.bashrc`, `.env`, `.hermes/`, `.claude/`, `.codex/`, `.cursor/`, `.cline/`, `.continue/`, `.openclaw/`, `.qoder/`, `.aws/credentials`, `.netrc`, and more.

**Detected agents**: Claude Code, Codex, Hermes Agent, Gemini CLI, Cursor, Windsurf, Cline, Continue, OpenCode, OpenClaw, Qoder, and others.

## Requirements

- **Python 3.7+** (standard library only for core functionality)
- **openpyxl** — required for Excel output (`pip install openpyxl`)
- **PyYAML** *(optional)* — improves Hermes `config.yaml` parsing; falls back to regex if absent
