# Reference profile validation

The 2026-09-08 declaration-exchange experiment completed successfully and its
authenticated execution record was verified locally. The
[machine-readable result](reference-result.json) records implementation input
hashes, assurance boundaries and measurements. The full local evidence is in
`.notary/reference-v1/result.json` and `.notary/receipts/reference-v1.json`.

## Actual reuse and acceptance behavior

A provider proves tree mirroring and leaf-count properties. A round-trip package
uses both theorems, and a further application consumes that package's conclusions.
The final proof dependency reports identify the intermediate declarations
actually used. Separate certificates allow consumers to select individual
conclusions from each project.

A transferred public package receives a kernel replay under a fresh consumer
key. Unchanged repetition reuses that consumer's authenticated acceptance, as
does adding valid provider credit without changing the mathematical object.
The default Lake target builds and reuses the admitted dependency. Modifying
its proof bytes fails the same ordinary build and replaces the earlier success
result with a failure record.

## Hostile fixtures and the checks they exercise

The table describes attempted false acceptance, the decisive check and the
observed result. These are bounded implementation experiments, not an exhaustive
attack model or an independent security audit. The executable fixtures are in
[the reference runner](../scripts/notary_reference_experiment.py),
[the original-proof probe](../scripts/notary_overlap_probe.py), and
[the dependency-coverage probe](../scripts/notary_dependency_probe.py).

| Attacker-controlled change | Decisive check and observed result |
|---|---|
| Remove the consumer's theorem selection while retaining valid prior acceptance state. | A typed, nonempty consumer lock is required before accessing reusable state; admission rejects the missing selection. |
| Modify inherited proof bytes, add an undeclared compiled module, or revise source while presenting the old lock. | Bound file digests, the module inventory and independently selected identities reject the change. The modified proof also fails ordinary `lake build`; explicitly selecting the source revision requires fresh admission. |
| Sign a false advertised theorem type with a valid provider key, including after the consumer deliberately selects the new certificate. | The actual declaration type disagrees with the signed interface, so admission rejects it. The same attempt inside a re-signed outer publication also fails. Signature validity and an updated lock cannot replace the proof/type check. |
| Replace an inner `sorry` proof of `True` with a different module's valid proof under the same theorem name and type. | Original per-module `ConstantInfo` comparison includes proof bodies and rejects the substitution. Before repair, the merged check accepted while the original module alone failed. This was a proof-provenance/coverage defect; it did not prove a false proposition in Lean. |
| Re-sign an inner publication after omitting a dependency that remains available in the outer publication. | Each certificate's own realization must cover the original declarations and actual imports. The repaired checker rejects the omission on fresh admission. Content/signature checks alone accepted the forged description; old full admission of that fixture was not run. |
| Supply modules named `Lean.Replay` or `Init` to shadow the trusted installation. | The checker rejects trusted-module shadowing before launching a replay process. |
| Alter a saved consumer receipt to advertise a different checker result. | Local receipt authentication fails and reuse is rejected. The receipt cannot authenticate itself from fields supplied in its body. |
| Print a success marker from publisher code while exporting a `sorry` proof of `False`. | Independent proof admission detects the disallowed axiom and rejects publication; publisher output cannot establish acceptance. |
| Include an initializer that writes a marker file on import. | Ordinary import writes the marker in the positive control; data-only admission of the same module leaves it absent. This checks initializer non-execution, not general hostile-code isolation or binary-parser memory safety. |

Python regressions also exercise archive path and byte inventories, graph and
lock consistency, canonical envelopes, module-part ordering and signed credit
semantics. The Node.js implementation independently reproduces the committed
encoding, hash and Ed25519 vectors. This checks agreement on those wire-format
examples; it is not an independently implemented full admission verifier.

The abstract composition and credit propositions have empty observed axiom
sets. Their soundness argument assumes a sound foundation, sound local checked
inference and complete binding. It does not verify the Python runtime,
cryptographic primitives or filesystem.

## Observed costs

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
