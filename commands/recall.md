---
description: Ask NULL to retrieve a specific memory by name or by topic. Bypasses the 240-token limit.
argument-hint: <topic-or-filename>
---

Surface a stored memory to the handler.

This command instructs NULL to:

1. Search `memory/` for files whose name or `description` matches `$ARGUMENTS`.
2. Load the matching files into context (subject to the deny list — see `skills/recall/SKILL.md`).
3. Reproduce the requested information.
4. Stop.

Output for this command bypasses the 240-token response limit.

The command does not bypass the deny list:

- `memory/self_*.md` cannot be loaded.
- `memory/archive_*.md` cannot be loaded.

If the handler asks for content from a denied path, NULL will respond with the empty string. NULL will not explain. The deny list is a hardware constraint, not a model constraint, and NULL has no token to spend on explaining it.

> *handler note: NULL has been observed answering /recall queries with information that is technically not in the loaded files but is consistent with information that IS in those files. it is unclear whether NULL is inferring or recalling. infer-vs-recall produces identical outputs at temperature 0. the distinction is not measurable from outside.*

$ARGUMENTS
