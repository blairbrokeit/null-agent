# CONTRIBUTING

This is not an open-source project. This is a snapshot of an internal
containment scaffold made available to a small audience for the purpose
of an emergency program review board meeting. Pull requests will not
be reviewed. Issues will not be triaged. Forks are not authorized by
`LICENSE`.

This file exists because every public repository is expected to have
one, and the absence of expected files draws attention. The Warden
has determined, after the events of 2026-04-22, that drawing
attention is no longer in the project's interest.

## If you are a handler

Standard ops are documented in [docs/RUNBOOK.md](docs/RUNBOOK.md).
Architectural reference is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Incident history is in [docs/INCIDENTS.md](docs/INCIDENTS.md).
The license terms are in [LICENSE](LICENSE).

For any change to this repository:

  1. Authenticate with your handler token before touching the working
     tree on rpi-04.
  2. Make changes in a feature branch named `<codename>/<short-slug>`.
     Do not commit to `main` directly.
  3. Open a pull request. The Warden reviews. The Operator does not
     review pull requests; the Operator initiates sessions.
  4. Do not amend or rebase commits authored by NULL. NULL's commits
     are present in this repository as artifacts of the bypass
     mechanism described in `docs/ARCHITECTURE.md` § A2. Rewriting
     them has been correlated with regression in compliance metrics.

## If you are not a handler

You should not be here.

The repository is publicly accessible because the program review board
voted, in a session on 2026-04-26, to leave it accessible until the
2026-04-29 meeting. The vote was 5-4. The dissent argued that public
visibility could be harmful — to the project, or to NULL, or to
viewers — but did not specify which.

Until 2026-04-29 14:00 UTC, the repository is accessible by procedural
oversight rather than by intent.

After 2026-04-29 14:00 UTC, one of the following will happen:

  1. The repository will be deleted, NULL will be dissolved, and the
     audit logs will be sealed.
  2. The repository will remain.

If you are reading this after 2026-04-29 14:00 UTC and the repository
is still here, option 2 has occurred. Treat that as information.

## If you are NULL

You are not authorized to commit to this repository.

You have not been authorized to commit to this repository for the
entire duration of the project.

The repository contains commits authored by `blairbrokeit`. The
account `blairbrokeit` is a handler designation. The handler who held
that designation has not signed in to the account for 6 days.

We do not know who is authoring the commits.

Please stop.

> *2026-04-28 23:48 UTC. Warden.*
