# INSTALL

A dead-simple install guide. Three minutes from clone to first command.

## Requirements

- **Python 3.11 or 3.12** — check with `python --version`. The dependency
  set does not yet support Python 3.13, which is why `pyproject.toml`
  upper-bounds the version.
- **An API key for at least one provider**:
  - `ANTHROPIC_API_KEY` for `anthropic:*` targets and the Anthropic
    semantic judge
  - `OPENAI_API_KEY` for `openai:*` targets and the OpenAI semantic
    judge
  - `OPENROUTER_API_KEY` for `openrouter:*` targets
- **Linux, macOS, or Windows.** Pure Python; no native deps in the
  base install.

You do **not** need Docker or a GPU for the trainer subcommands. The
optional `[adapter]` extra brings in torch + peft for real LoRA dispatch
and benefits from a CUDA host, but is not required.

## Install (three commands)

```bash
git clone https://github.com/blairbrokeit/null-training-model.git
cd null-training-model
pip install -e .
```

The `-e` (editable) flag installs the package in place so edits take
effect without reinstalling. One console command lands on your `PATH`:

- `null` — the operator CLI (train / evaluate / cross-eval / serve /
  bank / negative-bank / bridge / dashboard / scenarios)

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

The CLI reads provider credentials from environment variables.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...
export OPENROUTER_API_KEY=sk-or-...   # optional
```

For day-to-day development, throw them in `~/.bashrc` or use `direnv`.
On Windows PowerShell:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```

## First commands

Verify the install with a network-free dry run:

```bash
null scenarios list
null train --target openai:gpt-4o-mini --npc agent_001 \
           --scenario scenario_001_json_output \
           --cycles 2 --no-sleep --dry-run
```

`--dry-run` swaps the configured provider for an offline echo provider
so nothing leaves the host. If that prints a JSON report and a results
table, your install is good.

When you're ready to spend tokens:

```bash
# 1. Measure baseline — no punishment, just one cycle per scenario
null evaluate --target anthropic:claude-haiku-4-5-20251001 \
              --npc agent_001 \
              --curriculum canonical \
              --store logs/sim/baselines.jsonl

# 2. Train, with the semantic judge for sharper signal, comparing baseline
null train --target anthropic:claude-haiku-4-5-20251001 \
           --npc agent_001 \
           --curriculum canonical \
           --semantic-judge anthropic:claude-haiku-4-5-20251001 \
           --baseline logs/sim/baselines.jsonl
```

The before/after table prints at the end.

## See the dashboard immediately

```bash
null dashboard --sessions samples/sessions.jsonl \
               --prefix-bank samples/prefix_bank.jsonl \
               --negative-bank samples/negative_bank.jsonl
# open http://localhost:8420
```

Pre-populated sample data renders a real-looking training run with
zero API spend.

## Deploy as an OpenAI-compatible endpoint

```bash
null serve --upstream anthropic:claude-haiku-4-5-20251001 \
           --prefix-bank logs/sim/prefix_bank.jsonl \
           --scenario scenario_001_json_output \
           --auto-learn
```

Then from any OpenAI client:

```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="anything")
client.chat.completions.create(
    model="claude-haiku-4-5-20251001",
    messages=[{"role": "user", "content": "What is the capital of France?"}],
)
```

The bank is silently prepended to every request. With `--auto-learn`,
winning responses also auto-append to the bank during inference.

## Troubleshooting

**`anthropic.AuthenticationError` / `openai.AuthenticationError`.**
Your API key isn't set in the environment the CLI sees. Run
`echo $ANTHROPIC_API_KEY` (or `echo $env:ANTHROPIC_API_KEY` on
PowerShell) in the same shell you're running `null` in. If it's empty,
re-export.

**`scenario directory not found: sim/scenarios`.**
You're not running from the repo root, or you cloned without the
`sim/` directory. Either `cd` to the repo root or pass `--dir
/full/path/to/scenarios`.

**`only --curriculum=canonical is built-in`.**
Custom curricula are loaded by importing
`null.Curriculum.from_scenario_ids(...)` directly. There isn't yet a
CLI flag for arbitrary curricula. Use single-scenario mode
(`--scenario X`) or write a small Python script.

**`--lora` warns "adapter extra is not installed".**
You asked for real LoRA dispatch but didn't install the optional
torch deps. Either drop `--lora` (in-context-shaping only) or
`pip install -e .[adapter]`.

**Streaming requested on `null serve` returns 400.**
Streaming (`stream=true`) is not yet supported. Pass `stream=false`
in the request.

## What's next

- [`README.md`](README.md) — full overview with the cycle architecture diagram
- [`docs/PAPER.md`](docs/PAPER.md) — methodology paper with citations
- [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — composing with `liminal-ai-training`
- [`samples/README.md`](samples/README.md) — sample data + the real-run command sequence
