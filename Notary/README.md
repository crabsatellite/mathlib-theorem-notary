# Theorem Notary: a Glass Box publication and import layer

This is the engineering prototype for publicly supplied, kernel-only theorem
components. A provider signature records credit, not mathematical endorsement.
Anyone can supply the same valid component. Lean receives the actual published
theorem, never a new axiom justified by a signature.

## Start with the standalone exchange

The [small reference example](REFERENCE.md) publishes tree theorems, uses them
in a round-trip package, and uses that package's conclusions in a further
application. It demonstrates separately certified declarations, nested
publication, fresh proof admission, unchanged local reuse and rejection of
tampered dependencies by the consumer's ordinary `lake build`. It requires no
large archive, mathlib cache, registry account or private orchestration service.

Ordinary Lean imports and environment replay already enable reuse and checking.
This layer specifies how a selected declaration, its original proof material,
logical foundation, dependency publications and provider credit stay bound
together across releases. Consumers retain their own selection and acceptance
state. The [comparison with existing tools](RELATED_WORK.md) explains this
boundary; it also identifies the additional evidence needed to establish a
workflow or performance advantage.

See the [normative profile](SPEC.md), [reproduction guide](REFERENCE.md), and
[validation mechanisms and limits](VALIDATION.md). The checked composition
model assumes sound local checking and complete binding; it is not a formal
verification of the runtime. Separate operator/platform reproduction, automatic
conversion of arbitrary Lake package graphs, an open untrusted-upload service
and declaration-level incremental checking remain further work.

The purpose of this reference is to make the engineering gap and proposed
contract reviewable. Feedback on the implementation's correctness and on the
best future Lake/mathlib integration is welcome; that integration design is
still open.

## Larger case: the archived Erdős Problem 848 formalization

The archive adapter imports an all-N extremal bound from a published
formalization of Erdős Problem 848, concerning sets whose pair products plus
one are nonsquarefree. Its provider credit is assigned to
**Alex Chengyu Li**. The component records the exact public source commit,
theorem, source/compiled-artifact manifests, allowed logical foundations, and
the historical kernel-verification record.

The following instructions concern this archive adapter. Use the standalone
guide above for a first trial of the general protocol.

### Scope of the archive adapter

- Ed25519 credit signatures, domain-separated component IDs, and verification.
- An immutable public registry entry, `erdos848.component.json`.
- Manifest-pinned downloads; ZIP inventory, path, size and SHA-256 checks for
  every installed proof artifact.
- An explicit adapter for the immutable `v1.0.5-kernel` release. It reuses
  **grandfathered kernel-archive evidence**; it does not claim a fresh replay of
  the 30,638-module upstream proof.
- A Lake target which verifies the component and compiles a new external
  consumer of the real `Erdos848.PaperGeneratedCertificateProvider.all_N`.
- `#notary_info` for showing credit and provenance beside the actual Lean type.

The checked-in signed record is public registry data and can be served by GitHub
or any byte-preserving mirror. It grants no new mathematical authority to that
server or to the provider.

## Fixed compatibility boundary

The implementation branch is `notary/erdos848-v0`, based on mathlib commit
`54e71fa9173471d591658f5380c46aaf050bbaae`, using Lean `v4.30.0-rc2`.
The upstream proof artifacts were built for Windows x86-64. Do not run
`lake update` or migrate the case to a newer mathlib version to run this example.
Other platforms need separately built and checked artifacts.

The component references these immutable public objects:

- [Source release](https://github.com/crabsatellite/erdos-848-squarefree-product/tree/bb8e1b10b0066639ee3440ba983c3f9774667d42)
- [Kernel archive](https://github.com/crabsatellite/erdos-848-squarefree-product/releases/tag/v1.0.5-kernel)
- [Recorded kernel basis](https://github.com/crabsatellite/erdos-848-squarefree-product/blob/bb8e1b10b0066639ee3440ba983c3f9774667d42/proof-state.json)
- [Published theorem implementation](https://github.com/crabsatellite/erdos-848-squarefree-product/blob/bb8e1b10b0066639ee3440ba983c3f9774667d42/lean4/Erdos848/PaperGeneratedCertificateProvider.lean)

## Build and inspect

Install Python and the pinned Lean toolchain, and install the Python dependency:

```text
python -m pip install -r Notary/requirements.txt
python scripts/theorem_notary.py show
python scripts/test_theorem_notary.py
lake build Notary
lake env lean --trust=0 MathlibTest/NotaryMetadata.lean
```

Prepare mathlib's original precompiled cache at the base commit **before**
checking out the notary branch in a fresh clone. The fork adds Lake targets, so
its changed lakefile is not the upstream cache-key configuration. In a clean
clone, use the same checkout sequentially:

```text
git checkout 54e71fa9173471d591658f5380c46aaf050bbaae
lake exe cache get
git checkout notary/erdos848-v0
```

The `show` command fetches and verifies the locked archive manifest and small
public evidence records into `.notary`.
The manifest's SHA-256 is locked in the component and the adapter. Restore the
proof objects (about 30 GiB downloaded and 121 GiB unpacked):

```text
python scripts/notary_fetch.py --manifest .notary/ERDOS848_OLEAN_CACHE_MANIFEST.json --manifest-sha256 3cbde25db4c5eac8209dd428cc5d95eab648766023db87418c8ea8c66353c527 --base-url https://github.com/crabsatellite/erdos-848-squarefree-product/releases/download/v1.0.5-kernel --download-dir .notary/downloads --library-dir .notary/erdos848/lib/lean --jobs 3
python scripts/notary_receipt.py verify --infrastructure PATH_TO_PAPER_INFRASTRUCTURE/src
python scripts/notary_receipt.py run-or-reuse --infrastructure PATH_TO_PAPER_INFRASTRUCTURE/src
```

The target explicitly opts into the grandfathered-archive policy, validates all
proof bytes against that archive, generates `.notary/NotaryErdos848.lean`, and
checks its literal theorem alias:

```lean
theorem NotaryErdos848.external_all_N :
    ∀ N, Erdos848.OriginalProblem848Statement N :=
  Erdos848.PaperGeneratedCertificateProvider.all_N
```

The generated consumer runs `#notary_info` and `#print axioms`. Its axiom closure
must be exactly `propext`, `Classical.choice`, and `Quot.sound`, in any order.
Outputs go to `.notary/external-import.log` and
`.notary/external-import-result.json`. A failed check cannot produce a successful
Lake target result.

The supplied receipt policy calls `lake build notaryErdos848`. Its input inventory
binds actual restored proof artifacts, mathlib/dependency artifacts, implementation,
policy and exact Git HEAD. The adapter also hashes the external host runtime.
A valid host receipt reuses the check without recompiling. Its HMAC signature is
local execution evidence, separate from publicly verifiable Ed25519 provider credit.
Verification-only never starts the theorem command. A standalone Lake invocation
is available for installations without Paper Infrastructure but revalidates the
archive on each execution. Proof generation is not repeated.

## Publishing credit

`prepare` binds the locally available public Lean sources to the release
manifest and its recorded kernel result. It does not rebuild the original proof.
Use the canonical public source checkout as input:

```text
python scripts/theorem_notary.py prepare --source PATH_TO_PUBLIC_ERDOS848_SOURCE
python scripts/theorem_notary.py credit --name "Provider Name" --account https://github.com/PROVIDER
```

The Ed25519 private key stays in `.notary/keys/provider.pem`, which Git ignores.
Protect it with the operating system's file permissions. Only the public key
and credit signature belong in the public registry entry. A different provider
can sign the same component ID without changing its mathematical identity.
An account URL in the signed record is provider-declared; the signature by
itself does not establish legal identity, authorship, or priority.

## Important distinctions

The protocol reports separately: signature validity, exact artifact identity,
public source location, mathematical basis, and this consumer's check. It has no
numeric trust score. Public availability of code is an audit capability, not a
replacement for verification. Ordinary signatures do not certify that a kernel
ran, and the historical adapter accepts only its explicitly locked archive.

See [the protocol design](../docs/THEOREM_NOTARY_PROTOCOL.md) for the fuller
component model, build integration analysis, and future verification properties.
Mathlib and the upstream proof retain their respective authorship and licenses.


## Multiple conclusions and nested certificates

A certificate identifies one theorem, not one repository. `#notary_inspect Name`
selects the actual theorem and records its structural Lean expression and universe
parameters. Shared module bytes are recorded once per realization; separate
conclusions have distinct certificate IDs and independently transferable credit.

The controlled real-kernel example builds eight import layers, preserving
separate certificates for both theorems in each module and checking both final
conclusions. This tests repeated wrapping to that depth; the general reference
example above additionally tests actual use of inherited theorems. It also
changes every intermediate compiled module and attempts sorry, hidden-axiom,
wrong-proof and axiom-as-theorem attacks. Its generated keys identify test
providers, not Alex. Run it through the separate receipt policy:

```text
python scripts/test_notary_chain.py
python scripts/notary_receipt.py verify --infrastructure PATH_TO_PAPER_INFRASTRUCTURE/src --policy Notary/chain-demo.policy.json
python scripts/notary_receipt.py run-or-reuse --infrastructure PATH_TO_PAPER_INFRASTRUCTURE/src --policy Notary/chain-demo.policy.json
```

Graph and independent consumer locks are written to `.notary/chain-demo`.
The graph verifier can be used separately:

```text
python scripts/notary_chain.py --lock .notary/chain-demo/consumer-0.lock.json --graph .notary/chain-demo/graph.json --artifacts .notary/chain-demo
```

**Graph integrity is not mathematical admission.** The graph CLI says so in its
machine-readable result. Never adopt a graph's advertised root as the consumer
lock or accept a publisher's self-written success receipt. The actual host build
must verify every uncovered dependency and the exact import closure. This v0
checks controlled fresh fixtures and the locked #848 archive. The new v1 checker
adds data-only kernel replay, isolated search paths and actual dependency/type
inspection for configured theorem bundles. It does not provide a process sandbox
for arbitrary hostile native code or source metaprograms; that remains required
before operating an open submission service.

The #848 target also inspects the real `tailClose` theorem beside `all_N`, writing
`.notary/erdos848-declarations.json`. Its reusable consumer artifact is
`.notary/consumer/lib/lean/NotaryErdos848.olean`; a downstream Lean process needs
that directory, the locked #848 proof directory, and this fork's ordinary Lake
dependency paths. With those paths, `import NotaryErdos848` exposes
`NotaryErdos848.external_all_N`. The original public signed archive record stays
bound to `all_N`; the generated extra export report is not yet a second published
provider certificate.
