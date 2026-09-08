# Contribution and prior work

The research question is how to hand off an exact checked theorem component
between projects while preserving publicly inspectable proof material, provider
credit, dependency identities, and explicit acceptance scope. The contribution
is a concrete Lean exchange and admission contract, with an executable build
integration and hostile composition tests.

External theorem reuse and proof checking have substantial prior art. Ordinary
Lean already serializes environments and imports external modules. Its manual
also describes separate checking of complete `.olean` environments through
`lean4checker`. The reference implementation uses Lean's existing replay
machinery, rather than introducing a new proof kernel. [Lean manual](https://lean-lang.org/doc/reference/latest/Elaboration-and-Compilation/)

Hurd's **OpenTheory: Package Management for Higher Order Logic Theories**,
PLMMS 2009, ACM, pp. 31–37, provides exported/imported theory packages, explicit
dependency management and proof exchange across HOL systems. The subsequent
**The OpenTheory standard theory library**, NFM 2011, LNCS 6617, pp. 177–191,
develops this programme. These are direct prior work, not distant analogies.
Our present pinned-Lean profile does not provide OpenTheory-style cross-system
theory interpretations. [2009 paper](https://www.gilith.com/papers/article.pdf),
[author's publication records and canonical 2011 citation](https://www.gilith.com/opentheory/)

Torres-Arias, Afzali, Kuppusamy, Curtmola and Cappos, **in-toto: Providing
farm-to-table guarantees for bits and bytes**, USENIX Security 2019, addresses
cryptographically bound software supply-chain stages. It supplies a relevant
attestation design precedent; mathematical kernel admission is an additional
domain-specific contract. Hashes, signatures and provenance chains themselves
are established mechanisms. [Published proceedings paper](https://www.usenix.org/system/files/sec19-torres-arias.pdf?download=1)

| Baseline | Existing capability | What this implementation adds or specializes |
|---|---|---|
| Ordinary Lean/Lake | External module imports, elaboration, builds, cached artifacts | Per-theorem publication identity, provider credit, locked transitive certificate binding, and admission as an explicit default build dependency |
| Lean environment replay/checker | Kernel replay of serialized declarations | Binding its actual result to selected interfaces, permitted axiom closure, supplied bytes and consumer-owned reuse evidence |
| OpenTheory | Packaged theory exchange and composition, including cross-prover transport | A Lean-specific realization and provider-credit profile; this work has narrower logical interoperability |
| in-toto and signed artifact manifests | Authenticated artifact and process provenance | Theorem-specific type/axiom checks; provider signature is insufficient for mathematical admission |
| Hash-only bundle verification | Byte and signature consistency | Fresh mathematical admission or exact local receipt reuse, with assurance states reported separately |

The abstract composition result proves soundness by induction on finite accepted
dependency derivations, assuming sound foundation and local checked inference.
It explains why depth and additional valid provider credits do not add logical
authority. This is a formal protocol invariant under explicit hypotheses; it
does not constitute a verification of the Python implementation, the kernel,
the filesystem or cryptographic primitives.

## Practical value and falsifiable next evidence

The strongest use case is an independently maintained, expensive formal proof
component consumed by several projects. A named theorem can carry a stable
identity, source, logical foundation and provider attribution without requiring
its repository to be merged into mathlib. A consumer can distinguish a recorded
check from a new check and reuse only the exact scope it already accepted.
This addresses proof-state handoff and repeated provenance reconstruction.

It does not produce missing mathematical lemmas, establish that a formal
statement matches a human theorem, reduce the initial proof-data closure to a
tiny certificate, or remove toolchain migration work. Current full-closure
replay can cost more than ordinary cached Lean import. A speedup claim requires
equal-assurance comparisons on large components and cannot be inferred from a
small warm-receipt demonstration.

For a protocol paper and reference artifact, the combination is a defensible
engineering contribution. A broad first-of-kind claim is not established by
this bounded related-work review. The strongest remaining adoption evidence is
an independent operator consuming a real external component, a second consumer
updating it successfully, and recorded differences in checking cost and failure
diagnosis against their current workflow. A second nontrivial mathematical case,
an independently implemented full bundle verifier, and immutable acceptance
storage would materially strengthen the work beyond the current prototype.
