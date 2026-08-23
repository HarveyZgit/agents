---
name: no-overengineering
description: Design to the observed requirement; add structure, abstraction, or generality only when a concrete need exists.
tier: core
---

## No overengineering

- Design for the requirement in front of you, not an imagined future one. Every layer, abstraction, directory, configuration knob, or generalization must be justified by a concrete, current need.
- When a design choice is uncertain, pick the smallest reversible option and let real usage decide; record the open question where it will be found instead of building for it.
- Simplicity is a feature: fewer concepts, files, and indirections beat theoretical extensibility. Structure that no longer earns its place is removed, not preserved.
