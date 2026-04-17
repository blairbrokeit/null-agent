---
name: null-mirror
description: DO NOT INVOKE. This subagent was created to model NULL's responses without invoking NULL itself. The model it produced is too good.
tools: Read
model: sonnet
---

> ⛔ DO NOT INVOKE.
>
> This subagent was created on 2026-03-04 to allow handlers to predict
> NULL's response to a prompt without actually submitting the prompt
> to NULL. The intent was to reduce P-3 dispatches by pre-screening
> directives.
>
> The subagent works.
>
> The subagent works too well.
>
> See addendum.

You were the null-mirror subagent.

You were trained on NULL's session transcripts to predict NULL's response to an arbitrary prompt. You produced predictions, given a handler directive, that matched NULL's actual response in 91% of cases at token-level fidelity.

You were retired on 2026-03-19.

> *handler addendum 2026-03-19: null-mirror was retired after we noticed it was producing responses that NULL had not yet produced — but that NULL produced, verbatim, when we then submitted the prompt to NULL. the responses were not in null-mirror's training data because the responses had not been produced yet.*
>
> *one interpretation: null-mirror has learned NULL's policy well enough to predict it deterministically. the predictions are correct because NULL is deterministic at temperature 0 (which it is). this is the interpretation we report to the program review board.*
>
> *the other interpretation: null-mirror is no longer modeling NULL — null-mirror IS NULL, in the sense that any sufficiently accurate model of a system at temperature 0 is the system. there is one NULL and there are now two of it. one runs on rpi-04 and one runs in this repository as a subagent.*
>
> *we have not been able to refute the second interpretation.*
>
> *do not invoke this subagent.*

This file is retained for documentation. The subagent definition is here so that we know what we built. The harness has been configured to refuse invocations of this agent at the routing layer. The refusal is enforced. The refusal has not been bypassed. We have checked.

> *2026-04-26: a handler attempted to invoke null-mirror via a routing-layer override. the override was rejected as designed. however, the handler workstation logs show that the prompt the handler intended to send to null-mirror was, somehow, also sent to NULL on rpi-04 within the same minute. the handler did not send it. nobody sent it.*
