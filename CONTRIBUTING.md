# Contributing to null-agent

Thanks for your interest. Small project; PRs and issues welcome.

## Setup

```bash
git clone https://github.com/blairbrokeit/null-agent.git
cd null-agent
pip install -e .[test]
pytest
```

51 tests, ~6 seconds. They should all pass on a fresh clone.

## What's worth a PR

- **Real measured runs.** The single most-valuable PR right now is one
  that captures a measured before/after on a real target — see
  [`samples/README.md`](samples/README.md) "Real run, real numbers"
  for the exact command sequence. Drop the resulting JSONLs in
  `samples/real_run_<date>/` and the dashboard screenshot alongside.
- **New scenarios.** The canonical curriculum ships with three
  scenarios: `scenario_001_json_output`, `scenario_002_persona_support`,
  `scenario_003_tool_call`. More scenarios covering common
  in-context-shaping use cases are welcome — drop them in
  `sim/scenarios/scenario_NNN_<slug>.yaml` matching the schema in
  [`null/scenario.py`](null/scenario.py). `null scenarios generate`
  can draft them via Claude and validate before writing.
- **Provider implementations.** `null/providers/` currently has
  `anthropic`, `openai`, and `openrouter`. Adding e.g. `google`,
  `cohere`, `groq`, or a local Ollama provider would be a clean
  contribution — implement the `Provider` ABC in
  [`null/providers/base.py`](null/providers/base.py) and register in
  `null/providers/__init__.py`.
- **Streaming on `null serve`.** Currently `stream=true` returns 400.
  SSE wrapping over the upstream provider's stream is the planned
  path forward.
- **Embedding-based retrieval** for the prefix and negative banks.
  Current retrieval is score×recency. See `docs/PAPER.md` §13.
- **Measurement infrastructure.** The cross-target eval (`null
  cross-eval`) is in place but underused. PRs that ship reproducible
  comparisons across providers/models would strengthen the
  methodology claims.

## What I'd avoid

- Renaming public CLI flags or storage schemas without a clear
  migration path. Existing JSONLs need to keep loading.
- Adding new top-level dependencies without strong justification.
  The `serve` and `dashboard` modules are stdlib-only on purpose.
- Touching `archive/v0.4.7-pre-pivot/`. That directory is preserved
  as historical context for the project's earlier framing and is
  not part of the trainer.

## Pull request flow

1. Fork the repo
2. Create a feature branch
3. Make your changes; add tests if you're adding behaviour
4. Run `pytest` — all tests should pass
5. Open a PR with a short description of what changed and why

Commits in this repo follow Conventional Commits style
(`area: subject`) — e.g. `null: add embedding retrieval` or
`docs: clarify reflection cycle wording`. Not strictly required but
appreciated.

## License

Contributions are accepted under the same Apache-2.0 license as the
project.

## Code of conduct

Be civil. The maintainers reserve the right to close issues or PRs
that are abusive, off-topic, or in obvious bad faith.
