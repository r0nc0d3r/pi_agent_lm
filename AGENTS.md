# Agent instructions

This repo keeps machine-oriented **rules** and **skills** under [`.agents/`](.agents/). Agents (Cursor, Copilot, etc.) should treat the items below as **project defaults**; the `.mdc` and `SKILL.md` files are the source of truth.

## Rules (`.agents/rules/`)

| File | Summary |
|------|---------|
| [`branch-prefix.mdc`](.agents/rules/branch-prefix.mdc) | Feature branches use the **`agent/`** prefix (short, kebab-case). Do **not** use `cursor/`, `claude/`, or `codex/`. |
| [`uv-cli.mdc`](.agents/rules/uv-cli.mdc) | Prefer **`uv run`**, **`uvx`**, **`uv add`**, **`uv sync`** for this repo—not bare `python` / `pip` unless debugging outside uv. |
| [`config-toml.mdc`](.agents/rules/config-toml.mdc) | Config in **`config.toml`** (or `PI_AGENT_LM_CONFIG`); no hardcoded broker hosts/IPs in code. New keys mirrored in **`config.example.toml`** with placeholders. Prefer hostnames (mDNS/DNS), not IPs, in examples. |
| [`tests-and-coverage.mdc`](.agents/rules/tests-and-coverage.mdc) | Behavior changes → tests in **`tests/`**. Aim for **≥80%** line coverage on touched code; use `uv run pytest` + `pytest-cov` as in the rule. Document test commands in README when they exist. |
| [`python-and-commit-readme.mdc`](.agents/rules/python-and-commit-readme.mdc) | Normal Python style (clear names, small functions, sensible imports). Before commits: short change summary and update **`README.md`** (e.g. `## Recent changes`, keep `## How to run` accurate). |

## Skills (`.agents/skills/`)

Skills are optional **modes** or **workflows**; read the linked `SKILL.md` before following one.

| Skill | Path | When to use |
|-------|------|-------------|
| **caveman** | [`skills/caveman/SKILL.md`](.agents/skills/caveman/SKILL.md) | User asks for *caveman mode*, *less tokens*, `/caveman`, or token-efficient replies. Intensities: lite, full (default), ultra, wenyan variants. Turn off: `stop caveman` / `normal mode`. Code and commits stay normal. |
| **caveman-commit** | [`skills/caveman-commit/SKILL.md`](.agents/skills/caveman-commit/SKILL.md) | User asks for a commit message, `/commit`, `/caveman-commit`, or when staging—**Conventional Commits**, terse subject (≤50 chars when possible), body only if *why* is non-obvious. |

## Maintenance

When you add or rename a rule or skill under `.agents/`, **update this file** so the table stays accurate.
