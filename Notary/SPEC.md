# Theorem Notary declaration exchange profile v1

Status: reference profile for Lean `leanprover/lean4:v4.30.0-rc2`.
Normative terms MUST, MUST NOT and MAY apply only to this profile. The separate
#848 historical-archive adapter is explicitly not the cold-admission profile.

## 1. Objects and wire identity

A **bundle** carries readable source, all non-foundation `.olean` data parts,
the actual module inventory, and immutable dependency publications. A
**declaration certificate** selects one actual theorem in that bundle by its
full Lean name, structural type expression and universe parameters. Any number
of declarations MAY share the same bundle. A **credit** signs one certificate's
component ID and identifies a component-provider key. It adds no logical premise.
A **consumer lock** independently fixes the bundle ID and selected certificate
IDs. A **local acceptance receipt** binds an executed checker result to its
complete scope and is authenticated by a consumer-owned secret outside the bundle.

Canonical encoding is UTF-8 JSON without whitespace: Unicode scalar strings
are preserved literally, object keys are ordered lexicographically by UTF-8
bytes, and arrays preserve order. Only null, booleans, integers in
`[-9007199254740991,9007199254740991]`, strings, arrays and string-keyed objects
are permitted. Floats, duplicate object keys and lone surrogates MUST be rejected.
No Unicode normalization or mathematical equivalence normalization is performed.
Module names in this profile use ASCII identifiers separated by dots
(`[_A-Za-z][_A-Za-z0-9]*` per segment). This restriction is on module paths;
declaration names and readable source preserve literal Unicode.

An object ID is `sha256:` followed by SHA-256 of
`UTF8("theorem-notary/" + domain + "/v1") || 0x00 || canonical(core)`.
The domains `bundle`, `component` and `publisher-build` are distinct. Provider
credit uses Ed25519 over `UTF8("theorem-notary/provider-credit/v1") || 0x00 ||
canonical(body)`. All credit signatures MUST be checked; keys and signatures use
standard padded Base64. Fingerprints are SHA-256 of the raw public key.

The `type_expr` field uses the pinned Lean version's `reprStr Expr`, including
universe arguments, referenced constant names and binder information. This is
a version-specific structural representation, not a cross-version mathematical
equivalence test. The bundle fixes the referenced definitions. Publication URLs,
display names and credit lists are outside the mathematical bundle identity.
This first profile conservatively binds compiled realizations; it does not claim
identical component IDs across platforms or different Lean versions.

## 2. Publication and admission

1. A publisher explicitly selects modules and theorem names in an export config.
   Source compilation runs in a publisher-owned, trusted build environment.
2. Before issuing eligible certificates, the runner MUST read complete compiled
   proof data with imported extensions disabled and no publisher native plugins.
   It MUST replay the proof environment into a fresh Lean kernel environment.
   The trusted checker MUST start without publisher search paths. The baseline
   foundation MUST be loaded only from the trusted toolchain. A supplied module
   MUST NOT shadow any existing toolchain module, including checker imports.
3. Selected objects MUST be theorem declarations in the original proof data.
   The replayed environment MUST contain the same type and universe parameters.
   The checker MUST traverse actual declaration dependencies, not cached axiom
   metadata or publisher logs. Every encountered constant MUST be covered.
4. The only permitted logical axiom names are `propext`, `Classical.choice` and
   `Quot.sound`. Their actual types and universe parameters MUST equal those in
   the trusted installed foundation. A certificate MAY allow a smaller subset.
   Unsafe/partial proof dependencies and `sorryAx` MUST be rejected.
5. The runner MUST compare the actual loaded non-foundation module closure with
   the bundle inventory, and bind every exported/server/private proof data part.
   Missing source, additional proof files, conflicting module bytes or paths
   outside the bundle and trusted foundation MUST be rejected.
6. Only after these checks does the publisher generate per-declaration credits.
   The current implementation compiles and records source/artifact identity;
   consumer replay proves the artifact's formal content, not an independent
   reproduction of its correspondence to readable source.
7. A consumer MUST obtain its lock independently of the incoming package.
   `notary_cli lock` is an explicit selection operation, not implicit admission.
   Adding a valid provider credit does not update this lock or change its theorem.
8. A consumer MUST verify the lock, complete dependency publications, source and
   proof bytes, and all credits. A new consumer MUST perform its own kernel
   admission. A publisher's signature or purported receipt cannot replace it.
   A parent binds each dependency's bundle ID **and exported certificate IDs**.
   Kernel/type/axiom comparison covers certificates at every nesting level,
   including a nested certificate unused by a selected outer conclusion.
9. A consumer MAY reuse its own authenticated receipt only when object bytes,
   declaration interfaces, foundation files, checker, runner and Lean binary
   match. A stale scope triggers the explicit run-or-reuse path; a forged
   receipt fails. The receipt key MUST be outside the publisher bundle.
10. Verification and use require stable inputs. The reference runner takes an
    exclusive admission lease and checks bytes again before sealing success.
    The operational trust assumption is that the local state and accepted store
    are controlled by the consumer. Full hostile-host TOCTOU protection is not
    claimed; production deployments need a read-only content store/snapshot.

No state transition constructs a theorem from a signature. The machine-readable
states are content/credit verified, fresh kernel accepted, and local acceptance
reused. A historical archive has a separate explicit policy and assurance label.

## 3. Composition and failure semantics

An accepted derived declaration must have a local checked inference, exact
binding to its chosen interface, and a completely covered dependency set. Given
sound foundation declarations and sound local checks, induction over this finite
acceptance derivation proves the root declaration sound at any depth. Shared
dependencies do not change the argument. Mutually defined kernel objects are
checked as legal atomic groups by Lean's replay machinery.

`Notary/Composition.lean` formalizes that composition theorem and independence
from the credit parameter without axioms. Its `stepSound` hypothesis represents
kernel/checker soundness and exact binding. It does not verify the Python runner,
prove SHA-256 collision resistance, or establish filesystem immutability.

Tamper detection for a locked object additionally assumes collision resistance
and correct signature verification. Changing a type, proof or dependency changes
its identity; consistently re-signing a changed graph does not change the old
consumer lock. A new genuinely checked proof can receive a new identity.

Unknown profile/schema versions, unsupported core fields and malformed objects
MUST fail closed. Additional signed credit metadata carries no mathematical
authority and MAY be preserved without interpretation. This v1
reference implementation limits nested publication envelopes to 64 dependency
levels as a resource bound; the composition theorem itself has no fixed depth.
There is no mathematical trust score and no voting threshold for truth.

## 4. Conformance and implementation mapping

| Requirement | Reference implementation / evidence |
|---|---|
| Canonical identity and Ed25519 credit | `scripts/notary_protocol.py`; cross-language wire vectors |
| Per-declaration selection and signatures | `notary_cli export` / `build`; two tree theorems |
| Cold data-only replay and actual axiom closure | `Notary/Verifier.lean` |
| Complete module/source/proof inventory | `verify_bundle`, `actual_closure` |
| Transitive dependency publication binding | Nested bundles and module-byte identity checks |
| Consumer lock, fresh key and local receipt reuse | `notary_cli lock` / `admit` |
| Ordinary build depends on acceptance | The generated default Lake consumer target |
| Unbounded abstract composition | `Notary/Composition.lean` |
| Cross-project proof use and hostile tests | `scripts/notary_reference_experiment.py` |

## 5. Wire field contract

The literal schema strings and fields below are the v1 exchange vocabulary.
The full envelope is canonicalized before checking. File arrays are sorted by
path and contain exactly `path` and lowercase 64-digit `sha256`. Module values
list `.olean`, then present `.olean.server` and `.olean.private` parts. Paths
are relative POSIX paths under `src/` or `objects/`; traversal is rejected.

| Object | Fields |
|---|---|
| Publication | `bundle_id`, `core`, `certificates`, `dependencies` |
| Bundle core | `schema: theorem-notary/bundle/v1`, `profile: theorem-notary/lean-4.30-fresh/v1`, `toolchain`, `modules`, `files`, `dependencies` |
| Dependency binding | `bundle_id`, `certificates` (sorted component IDs); bindings sorted by bundle ID |
| Declaration envelope | `component_id`, `core`, `credits` |
| Declaration core | `schema: theorem-notary/component/v1`, `kind: declaration-export`, `bundle_id`, `interface`, `allowed_axioms` |
| Interface | `declaration`, `type_expr`, `level_params` |
| Credit | `schema: theorem-notary/provider-credit/v1`, `body`, `signature` |
| Credit body | `component_id`, `role: component-provider`, `display_name`, `identity_scope: key attribution only; name is provider-declared`, `public_key`, `key_fingerprint`, `mathematical_endorsement: false` |
| Consumer lock | `schema: theorem-notary/consumer-lock/v1`, `profile`, `bundle_id`, `certificates` (nonempty selected component IDs) |

`dependencies` in a publication holds complete nested publication envelopes;
`dependencies` in its core holds their immutable bindings. All nested source
and object files are also present in the parent closure, with identical hashes.
Certificates in one publication must have distinct declaration names. Multiple
credits share one certificate ID. HMAC acceptance receipts are a local runner
format, not portable public certificates or an interoperability requirement.

The three public [wire vectors](wire-vectors.json) include canonical bytes,
component IDs, raw public keys and Ed25519 signatures. Their deterministic test
key is public and MUST NOT be used outside these fixtures. Python and Node.js
independently check encoding, IDs and signatures in `test_notary_profile.py`.
This is wire-level independent implementation evidence, not a second proof kernel.

This profile assumes a trusted Lean installation, checker implementation,
publisher build host, consumer acceptance state and consumer-controlled storage.
The pinned toolchain installation and Python runtime/dependencies are assumed
immutable between acceptance and reuse; changing their executable code requires
invalidating local acceptance state. The SDK directly hashes its runner,
checker source, Lean executable and actually loaded proof foundation parts;
the outer Paper Infrastructure experiment additionally records its host runtime.
The admission checker does not execute imported extensions, but it uses Lean's
own binary reader and kernel; it is not an independently implemented kernel or
a memory-corruption sandbox. An open upload service, untrusted-source build
sandbox, registry availability/identity governance and cross-version transport
are separate implementation profiles.
