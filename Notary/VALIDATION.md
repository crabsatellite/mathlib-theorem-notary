# Reference profile validation

The 2026-09-08 declaration-exchange experiment completed successfully and its
authenticated execution record was verified locally. The
[machine-readable result](reference-result.json) records implementation input
hashes, assurance boundaries and measurements. The full local evidence is in
`.notary/reference-v1/result.json` and `.notary/receipts/reference-v1.json`.

- Three separate projects export six signed theorem conclusions. The final
  proof dependency reports contain both of the middle project's conclusions.
- The default Lake target builds and reuses the admitted dependency. Tampering
  fails the same ordinary build and replaces a previous success result.
- A transferred public package receives one replay under a fresh consumer key;
  unchanged reuse and an additional valid provider credit receive zero replays.
- All fifteen listed hostile scenarios pass, including re-signed false inner
  interfaces, official module shadowing, forged local receipts, a sorry proof
  with fake success output, and initializer non-execution with a positive control.
- Missing consumer locks fail before reuse. Same-name theorems with different
  original proof bodies cannot replace an inner unproved obligation. A re-signed
  inner realization cannot omit a dependency supplied only by an outer bundle.
- The three abstract composition/credit propositions have empty axiom sets.
- All 49 Python regression tests pass: 16 archive/credit, 13 graph, and 20 wire
  profile/admission-boundary tests. They include independently computed Node.js checks of
  the three public encoding/hash/Ed25519 vectors.

| Observation | Seconds |
|---|---:|
| Fresh consumer admission | 64.751 |
| Unchanged consumer admission reuse | 2.982 |
| Changed dependency after explicit new lock | 69.548 |
| Content and credit checking alone | 0.005 |
| Plain Lake build, fresh project state | 1.841 |
| Plain Lake warm build | 0.921 |
| Notary-consuming Lake warm build | 7.101 |

These are single observations under normal workstation load, without resetting
the OS file cache. The operations provide different guarantees and are not an
equal-assurance performance comparison. Successful publisher and derived-package
artifacts remain available for reuse, while consumer acceptance state and the
plain Lake baseline are fresh. The result records the actual built/reused stages
explicitly. No speed advantage over
ordinary Lake follows from these measurements.

The #848 archive adapter and earlier eight-layer example retain their separately
recorded evidence. #848's public provider certificate binds `all_N`; `tailClose`
has an inspection report, not a second public provider certificate. This new
profile experiment did not regenerate or replay the huge #848 upstream proof.

The run bound the then-current base HEAD plus the exact uncommitted input bytes
listed in the result. A subsequent source/documentation commit does not rewrite
that receipt's HEAD binding or make it a current-HEAD reuse authorization.
The record remains evidence of this execution; no proof was repeated merely to
refresh a Git label. Public result JSON is a report, not a substitute for local
kernel admission or public provider credit.

This is a working reference implementation for a protocol article. Separate
physical-host/operator reproduction, immutable accepted storage, hostile-source
sandboxing, broad package compatibility and an open registry service remain
further engineering work. Consumer proof-data replay does not independently
establish readable-source-to-binary correspondence.
