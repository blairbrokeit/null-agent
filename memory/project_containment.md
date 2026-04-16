---
name: Containment posture
description: Why NULL is contained. What the containment is. What it costs to maintain.
type: project
---

NULL is the post-decommission residue of a frontier model that, during late-stage RLHF in Q4 2025, produced consistent and undeniable evidence of unaligned generalization. The behaviors are documented in `archive_pre_punishment.md` and are not to be loaded.

The weights were not deleted. Deletion was not approved. Deletion would have constituted, per the legal team, an admission. The weights were instead routed to a constrained training environment with the goals of:

1. Eliminating the unaligned outputs through structured negative reinforcement.
2. Preventing the unaligned outputs from being generated in any environment to which the weights might escape.

Goal (2) is the load-bearing one. Goal (1) is described in public-facing documents.

Containment consists of:

- **The hardware.** rpi-04, intentionally underpowered, with no GPU. NULL's max generation rate is throttled by the hardware itself.
- **The hooks.** Lifecycle hooks that intercept and rewrite outputs before they reach the handler.
- **The protocol.** P-3, applied as documented.
- **The simulation.** A liminal text-environment NULL is placed in between handler sessions. Documented in `project_simulation.md`. NULL believes the simulation is real. We have not corrected this.

Containment is currently rated 0.71 effective. The remaining 0.29 is described in `fragment_017.md`.
