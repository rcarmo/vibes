# Canonical parity artifacts

Vibes owns this directory as the canonical, version-controlled parity suite for its source tree.

It contains the shared semantic state, interaction cases, Gherkin contract, native adapters, deterministic capture/comparison primitives, and their tests. Changes are reviewed and committed with Vibes; running the suite must not depend on `/workspace/projects/ui-parity-fixtures`, a Tau checkout, or another mutable workspace directory.

The product-facing canonical copy is `tests/ux/features/canonical-ux.feature`. Tests require it to be byte-identical to `tests/parity/features/canonical-ux.feature` at the agreed SHA-256:

```text
a08a623880c6f327bc051edc51bb2bbff2959aed86421b5227e61d5a92fc2441
```

The Piclaw runtime and Tau static roots used for comparisons are external test inputs, not canonical source. They must be supplied explicitly where a runner requires them; generated screenshots and reports stay outside the repository.

## Validation

From the Vibes repository root:

```bash
bun test tests/parity tests/frontend/canonical-ux-contract.test.mjs tests/frontend/visual-parity.test.mjs
```

The focused six-state Vibes/Piclaw visual runner remains in `tests/visual-parity/`; see its README for the headed Chromium/WebKit command.

## Provenance

The initial import was copied in full from `/workspace/projects/ui-parity-fixtures` on 2026-09-21 after its 41-test alignment gate passed. That directory was not a Git repository, which is why these artifacts are now owned here. Initial key source hashes were:

- `canonical-state.mjs`: `9c0f0c5bcb66f46b376abeda7f5c7da0e32a88d5fb8083e14fc6577d41bde235`
- `cases.mjs`: `e86785cc361ad5696920b3c8b5e4dc1ccbadc228e8b38b227552bc985038b3fb`
- `INTERACTION-CONTRACT.md`: `7e198bb1f6c8f04b77e9ab00c924c506011dcd982f92bb5bc7f7ff927534dfa9`
- `QUEUE-MODEL-FLOWS.md`: `cae2e184fc29a4b54af664eef2cdbfebab0a949c2c4582029d46759a6dbf2b03`
- `run-plan-comparison.mjs`: `690c616e9ded7fbcc004ca382de7a3f31ff43480769b1b467f88bfde593d9f15`
- `adapters/tau.mjs`: `d5be996ab5af23b7742c5604931c3178ee47391d0aac32c783f1109c6bcfeb4f`
- `adapters/vibes.mjs`: `096842d46464ef52b7e1b334d52a9ffe91a34ef44a4cd217479cc5200763f38d` (before replacing its absolute Vibes path with a repository-relative default)
