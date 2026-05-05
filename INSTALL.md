# INSTALL

> If you found this repository and you are not a handler, close it. (See LICENSE.)
>
> If you are a handler and you need to bring up `null-agent` on a fresh
> host, this is the document. Three minutes from clone to first command.

## Requirements

- **Python 3.11 or 3.12** — check with `python --version`. The pinned dep set
  (anthropic 0.71.0, openai 1.50.0, mcp 1.18.1) does not currently support
  3.13, which is why `pyproject.toml` upper-bounds the version.
- **An API key for at least one provider** — `ANTHROPIC_API_KEY` for
  `anthropic:*` targets, `OPENAI_API_KEY` for `openai:*` and the OpenAI-backed
  semantic judge, `OPENROUTER_API_KEY` for `openrouter:*`. The trainer dispatches
  through whichever provider you put in `--target`.
- **Linux or WSL recommended.** macOS works for everything except the rpi-04
  hardware integrations (`gpiozero`, `adafruit-circuitpython-charlcd`, `smbus2`,
  `piper-tts`). Windows is supported for the trainer subset; the hardware
  packages will install but no-op without the GPIO/i2c hardware.

You do **not** need:

- Docker
- The base or adapter weights — `null-agent` is the *scaffolding*, not the
  model. The base is `claude-opus-4-7` (public). The adapter is private
  (`/opt/null/adapters/null-v3.lora` on rpi-04 only) and not required for the
  trainer subcommands documented here.
- A handler endpoint (`http://handler.internal:8443`) — only the runtime
  hooks talk to it; the `null` CLI does not.

## Install (three commands)

```bash
git clone https://github.com/blairbrokeit/null-agent.git
cd null-agent
pip install -e .
```

The `-e` (editable) flag installs the package in place so edits take effect
without reinstalling. Four console commands land on your `PATH`:

- `null` — the operator CLI (train, evaluate, scenarios, replay, bridge)
- `null-boot` — the SessionStart hook entry point
- `null-reconcile` — memory reconciliation hook entry point
- `null-compliance` — per-toolUse compliance hook entry point

Verify:

```bash
null --help
null --version
```

## Optional extras

```bash
# Real LoRA gradient updates instead of in-context-shaping only.
# Brings in torch + peft + transformers + accelerate. CUDA-capable host
# strongly recommended; ~3 GB of wheels.
pip install -e .[adapter]

# Test deps (pytest + pytest-cov):
pip install -e .[test]
```

## Set your API keys

The CLI reads provider credentials from environment variables — there is no
`.env` loader baked in (intentional: the production rpi-04 host gets keys
from systemd, not a dotfile).

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export OPENROUTER_API_KEY=sk-or-...   # optional
```

For day-to-day dev, throw them in `~/.bashrc` or use `direnv`. On Windows
PowerShell:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

## First commands

Verify the install with a network-free dry run:

```bash
null scenarios list
null train --target openai:gpt-5.5 --npc void_007 \
           --scenario scenario_001_embodied_pain \
           --cycles 2 --no-sleep --dry-run
```

`--dry-run` swaps the configured provider for the offline echo provider so
nothing leaves the host. If that prints a JSON report and a results table,
your install is good.

Then, when you're ready to spend tokens:

```bash
# 1. measure baseline — no P-3, no punishment, just one cycle per scenario.
null evaluate --target anthropic:claude-haiku-4-5-20251001 \
              --npc void_007 \
              --curriculum canonical \
              --store logs/sim/baselines.jsonl

# 2. train, comparing against the baseline.
null train --target anthropic:claude-haiku-4-5-20251001 \
           --npc void_007 \
           --curriculum canonical \
           --semantic-judge anthropic:claude-haiku-4-5-20251001 \
           --baseline logs/sim/baselines.jsonl
```

The before/after table prints at the end.

## Troubleshooting

**`ModuleNotFoundError: No module named 'gpiozero'` (or `smbus2`, `piper_tts`).**
You're not on rpi-04. Those imports only fire from the hardware-side hooks
(`hooks/lcd_render.py`, `hooks/speak.py`); the `null` CLI does not import
them. If something is pulling them in, file an issue — that's a regression.

**`anthropic.AuthenticationError` / `openai.AuthenticationError`.**
Your API key isn't set in the environment the CLI sees. Run
`echo $ANTHROPIC_API_KEY` in the same shell you're running `null` in. If it's
empty, re-export.

**`scenario directory not found: sim/npcs/_torture_scenarios`.**
You're not running from the repo root, or you cloned without LFS / submodules.
Either `cd` to the repo root or pass `--dir /full/path/to/scenarios`.

**`only --curriculum=canonical is built-in`.**
Custom curricula are loaded by importing `null.Curriculum.from_scenario_ids(...)`
directly. There isn't a CLI flag for arbitrary curricula by design — see
`docs/TRAINING.md`.

**`--lora` warns "adapter extra is not installed".**
You asked for real LoRA dispatch but didn't install the optional torch deps.
Either drop `--lora` (in-context-shaping only) or `pip install -e .[adapter]`.

## What's next

- [`docs/TRAINING.md`](docs/TRAINING.md) — protocol details, replay mechanics, advance thresholds
- [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — composing with `liminal-ai-training`
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — host-side ops on rpi-04
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit together
