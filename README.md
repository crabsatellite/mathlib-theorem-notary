# Theorem Notary

A **Glass Box protocol and Lean reference implementation** for publishing and
reusing kernel-checked theorems across independently maintained projects.

As AI-assisted proof development expands, completed formalizations still need
to be selected, checked and maintained as dependencies. A receiving project
needs to know which exact statement, proof data, logical assumptions and
inherited dependencies it is accepting, and when an earlier check remains
applicable. Theorem Notary makes that handoff an executable publication and
admission contract.

Ordinary Lean imports and environment replay already provide the underlying
proof reuse and checking machinery. This prototype binds each selected theorem
to its inspectable proof material and dependency publications, records provider
credit, and makes consumer-controlled admission part of an ordinary Lake build.
A signature attributes supply to a key; the consumer checks the actual proof.
Proofs, definitions and dependencies remain available for inspection and replay:
this is the **Glass Box** boundary. See the
[comparison with existing tools](Notary/RELATED_WORK.md).

## Try the small theorem exchange first

Start with the [standalone reproduction guide](Notary/REFERENCE.md). Its tree
example demonstrates the complete handoff:

- A provider publishes separate proofs that mirroring twice restores a tree
  and that mirroring preserves its leaf count.
- A consumer uses those theorems to prove properties of a round-trip operation;
  a further application uses the consumer's conclusions in its own proofs.
- Changing inherited proof bytes fails the consumer's ordinary `lake build`.
  A fresh consumer checks the proof; unchanged local acceptance can be reused.

The example needs the pinned Lean toolchain, Python and Node.js. It needs no
mathlib cache, large proof archive, registry server or private infrastructure.
The guide includes commands, expected results and the boundary of the recorded
same-machine reproduction.

## Protocol and evidence

- [Normative exchange and admission profile](Notary/SPEC.md)
- [Validation mechanisms, observed results and limitations](Notary/VALIDATION.md)
- [Protocol paper](https://doi.org/10.5281/zenodo.22658049)
- [Implementation overview and large archived theorem case](Notary/README.md)

This is a working reference prototype pinned to Lean `v4.30.0-rc2`. Independent
operator/platform reproduction and automatic integration with arbitrary Lake
package graphs remain follow-up work. Fresh proof checking still has a cost;
the current measurements do not establish a speed advantage over an existing
workflow with equivalent assurance.

Design feedback is welcome on the proposed handoff contract, defects or missing
checks in the reference implementation, and the right integration boundary with
Lake and mathlib. The prototype makes the basic protocol idea executable;
deployment hardening and an upstream integration proposal require further design.

The implementation is hosted in a mathlib fork. Its archived Erdős Problem 848
adapter is a separate, larger case; the small example does not require it.
The upstream README and its upstream CI badges follow.

# Upstream mathlib4

![GitHub CI](https://github.com/leanprover-community/mathlib4/actions/workflows/build.yml/badge.svg?branch=master)
[![Bors enabled](https://raw.githubusercontent.com/bors-ng/bors-ng.github.io/refs/heads/master/images/badge_small.svg)](https://mathlib-bors-ca18eefec4cb.herokuapp.com/repositories/16)
[![project chat](https://img.shields.io/badge/zulip-join_chat-brightgreen.svg)](https://leanprover.zulipchat.com)
[![Gitpod Ready-to-Code](https://img.shields.io/badge/Gitpod-ready--to--code-blue?logo=gitpod)](https://gitpod.io/#https://github.com/leanprover-community/mathlib4)

[Mathlib](https://leanprover-community.github.io) is a user maintained library for the [Lean theorem prover](https://leanprover.github.io).
It contains both programming infrastructure and mathematics,
as well as tactics that use the former and allow to develop the latter.

## Installation

You can find detailed instructions to install Lean, mathlib, and supporting tools on [our website](https://leanprover-community.github.io/get_started.html).
Alternatively, click on one of the buttons below to open a GitHub Codespace or a Gitpod workspace containing the project.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/leanprover-community/mathlib4)

[![Open in Gitpod](https://gitpod.io/button/open-in-gitpod.svg)](https://gitpod.io/#https://github.com/leanprover-community/mathlib4)

## Using `mathlib4` as a dependency

Please refer to
[https://github.com/leanprover-community/mathlib4/wiki/Using-mathlib4-as-a-dependency](https://github.com/leanprover-community/mathlib4/wiki/Using-mathlib4-as-a-dependency)

## Experimenting

Got everything installed? Why not start with the [tutorial project](https://leanprover-community.github.io/install/project.html)?

For more pointers, see [Learning Lean](https://leanprover-community.github.io/learn.html).

## Documentation

Besides the installation guides above and [Lean's general
documentation](https://docs.lean-lang.org/lean4/doc/), the documentation
of mathlib consists of:

- [The mathlib4 docs](https://leanprover-community.github.io/mathlib4_docs/index.html): documentation [generated
  automatically](https://github.com/leanprover/doc-gen4) from the source `.lean` files.
- A description of [currently covered theories](https://leanprover-community.github.io/theories.html),
  as well as an [overview](https://leanprover-community.github.io/mathlib-overview.html) for mathematicians.
- Some [extra Lean documentation](https://leanprover-community.github.io/learn.html) not specific to mathlib (see "Miscellaneous topics")
- Documentation for people who would like to [contribute to mathlib](https://leanprover-community.github.io/contribute/index.html)

Much of the discussion surrounding mathlib occurs in a [Zulip chat
room](https://leanprover.zulipchat.com/), and you are welcome to join, or read
along without signing up.  Questions from users at all levels of expertise are
welcome!  We also provide an [archive of the public
discussions](https://leanprover-community.github.io/archive/), which is useful
for quick reference.

## Contributing

The complete documentation for contributing to ``mathlib`` is located
[on the community guide contribute to mathlib](https://leanprover-community.github.io/contribute/index.html)

You may want to subscribe to the `mathlib4` channel on [Zulip](https://leanprover.zulipchat.com/) to introduce yourself and your plan to the community.
Often you can find community members willing to help you get started and advise you on the fit and
feasibility of your project.

* To obtain precompiled `olean` files, run `lake exe cache get`. (Skipping this step means the next step will be very slow.)
* To build `mathlib4` run `lake build`.
* To build and run all tests, run `lake test`.
* You can use `lake build Mathlib.Import.Path` to build a particular file, e.g. `lake build Mathlib.Algebra.Group.Defs`.
* If you added a new file, run the following command to update `Mathlib.lean`

  ```shell
  lake exe mk_all
  ```

### Guidelines

Mathlib has the following guidelines and conventions that must be followed

 - The [style guide](https://leanprover-community.github.io/contribute/style.html)
 - A guide on the [naming convention](https://leanprover-community.github.io/contribute/naming.html)
 - The [documentation style](https://leanprover-community.github.io/contribute/doc.html)

### Downloading cached build files

You can run `lake exe cache get` to download cached build files that are computed by `mathlib4`'s automated workflow.

If something goes mysteriously wrong,
you can try one of `lake clean` or `rm -rf .lake` before trying `lake exe cache get` again.
In some circumstances you might try `lake exe cache get!`
which re-downloads cached build files even if they are available locally.

Call `lake exe cache` to see its help menu.

### Building HTML documentation

The [mathlib4_docs repository](https://github.com/leanprover-community/mathlib4_docs)
is responsible for generating and publishing the
[mathlib4 docs](https://leanprover-community.github.io/mathlib4_docs/index.html).

That repo can be used to build the docs locally:
```shell
git clone https://github.com/leanprover-community/mathlib4_docs.git
cd mathlib4_docs
cp ../mathlib4/lean-toolchain .
lake exe cache get
lake build Mathlib:docs
```
The last step may take a while (>20 minutes).
The HTML files can then be found in `.lake/build/doc`.

## Transitioning from Lean 3

For users familiar with Lean 3 who want to get up to speed in Lean 4 and migrate their existing
Lean 3 code we have:

- A [survival guide](https://github.com/leanprover-community/mathlib4/wiki/Lean-4-survival-guide-for-Lean-3-users)
  for Lean 3 users
- [Instructions to run `mathport`](https://github.com/leanprover-community/mathport#running-on-a-project-other-than-mathlib)
  on a project other than mathlib. `mathport` is the tool the community used to port the entirety
  of `mathlib` from Lean 3 to Lean 4.

### Dependencies

If you are a mathlib contributor and want to update dependencies, use `lake update`,
or `lake update batteries aesop` (or similar) to update a subset of the dependencies.
This will update the `lake-manifest.json` file correctly.
You will need to make a PR after committing the changes to this file.

Please do not run `lake update -Kdoc=on` as previously advised, as the documentation related
dependencies should only be included when CI is building documentation.

## Maintainers:

For a list containing more detailed information, see https://leanprover-community.github.io/teams/maintainers.html

* Anne Baanen (@Vierkantor): algebra, number theory, tactics
* Matthew Robert Ballard (@mattrobball): algebra, algebraic geometry, category theory
* Riccardo Brasca (@riccardobrasca): algebra, number theory, algebraic geometry, category theory
* Kevin Buzzard (@kbuzzard): algebra, number theory, algebraic geometry, category theory
* Mario Carneiro (@digama0): lean formalization, tactics, type theory, proof engineering
* Bryan Gin-ge Chen (@bryangingechen): documentation, infrastructure
* Johan Commelin (@jcommelin): algebra, number theory, category theory, algebraic geometry
* Anatole Dedecker (@ADedecker): topology, functional analysis, calculus
* Rémy Degenne (@RemyDegenne): probability, measure theory, analysis
* Floris van Doorn (@fpvandoorn): measure theory, model theory, tactics
* Frédéric Dupuis (@dupuisf): linear algebra, functional analysis
* Sébastien Gouëzel (@sgouezel): topology, calculus, geometry, analysis, measure theory
* Markus Himmel (@TwoFX): category theory
* Yury G. Kudryashov (@urkud): analysis, topology, measure theory
* Robert Y. Lewis (@robertylewis): tactics, documentation
* Jireh Loreaux (@j-loreaux): analysis, topology, operator algebras
* Heather Macbeth (@hrmacbeth): geometry, analysis
* Patrick Massot (@patrickmassot): documentation, topology, geometry
* Bhavik Mehta (@b-mehta): category theory, combinatorics
* Kyle Miller (@kmill): combinatorics, tactics, metaprogramming
* Kim Morrison (@kim-em): category theory, tactics
* Oliver Nash (@ocfnash): algebra, geometry, topology
* Filippo A. E. Nuccio (@faenuccio): algebra, functional analysis, homology, number theory
* Joël Riou (@joelriou): category theory, homology, algebraic geometry
* Michael Rothgang (@grunweg): differential geometry, analysis, topology, linters
* Damiano Testa (@adomani): algebra, algebraic geometry, number theory, tactics, linters
* Adam Topaz (@adamtopaz): algebra, category theory, algebraic geometry
* Eric Wieser (@eric-wieser): algebra, infrastructure

## Past maintainers:

* Jeremy Avigad (@avigad): analysis
* Reid Barton (@rwbarton): category theory, topology
* Gabriel Ebner (@gebner): tactics, infrastructure, core, formal languages
* Johannes Hölzl (@johoelzl): measure theory, topology
* Simon Hudon (@cipher1024): tactics
* Chris Hughes (@ChrisHughes24): algebra
