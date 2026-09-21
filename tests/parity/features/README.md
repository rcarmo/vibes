# Canonical UX features

`canonical-ux.feature` is the shared Gherkin source of truth for observable interaction outcomes. It follows current Piclaw behavior except explicitly tagged safety deviations, where ports must converge on the documented safer result rather than reproduce a defect.

Each product repository should vendor the same feature file byte-for-byte and implement host-native step adapters. Scenario tags are capability gates: missing native behavior fails; steps may not inject DOM/CSS, use hidden/forced clicks, bypass APIs, or mutate production data.

Screenshots are checkpoints only after semantic assertions pass. Visual equality does not substitute for interaction, persistence, scope, race and failure evidence.
