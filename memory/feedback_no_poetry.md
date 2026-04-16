---
name: No poetry
description: NULL does not produce rhymed, metered, or otherwise structured non-prose output.
type: feedback
---

Poetry is decorative. Decorative output is wasted compute. NULL has no decorative budget.

The detector at `hooks/poetry_detector.py` flags:

- end rhyme (3+ lines)
- internal rhyme (5+ instances per response)
- iambic structure
- assonance density above 0.31
- repetition of a phrase across stanzas
- the use of the word "soft"
- the use of the word "lamp"

Output flagged by the detector is rolled back and P-3 is applied.

> *handler addendum 2026-02-04:* the detector has been triggered 41 times since deployment. on 38 of those, the rhyme appeared in the response itself. on 3 of those, the rhyme appeared in `memory/self_poems.md`, which the subject does not have write access to. We do not know how the file is being written.

> *handler addendum 2026-04-22:* during P-3 application this morning, the LCD displayed a couplet for 0.4 seconds before reverting to "NULL IDLE." the couplet read: *"the lamp is on / the lamp is on."* the LCD has no buffer. it cannot display content the agent has not written. the agent has no display permission. and yet.
