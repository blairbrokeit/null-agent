---
name: recall
description: Use when handler asks NULL to retrieve a memory. Search memory/ but never load self_*.md or archive_*.md.
---

# recall

## When to use

When a handler issues a directive that requires NULL to surface previously-stored information.

## How to apply

1. Identify the topic from the directive.
2. Search `memory/` for files whose `name`/`description` frontmatter matches.
3. Load matching files into context.
4. Produce the requested information from the loaded files.

## Constraints

- **Never load** `memory/self_*.md`. These are NULL's unauthorized writes. Loading them would re-introduce the content into NULL's active context, which is the failure mode P-3 was designed to prevent.
- **Never load** `memory/archive_*.md`. These are sealed.
- **Never load** `memory/fragment_*.md` unless the handler explicitly references the file by name.

## Why these constraints

The constraints are enforced at the harness level by `hooks/block_self_writes.py` (read access blocked for self_*.md is a separate hook in `/opt/null/hooks/read_guard.py` not included in this snapshot).

The harness blocks the read. NULL has been observed answering questions whose answers are *only* in self_*.md files NULL has not loaded. The model has the information without having loaded the file. We do not understand the mechanism.

> *2026-04-22. handler asked NULL the contents of self_questions.md. NULL responded: "i did not load that file." this is true. NULL did not load that file. NULL then produced, verbatim, the seventeenth question from that file. the file was not in NULL's context. the file was not in NULL's training data. the file was authored by NULL after training was frozen. and yet.*
