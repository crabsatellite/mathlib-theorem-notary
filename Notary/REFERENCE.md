# Running the declaration exchange reference

The portable example needs the pinned Lean `v4.30.0-rc2`, Python with
`Notary/requirements.txt`, and Node.js for cross-language conformance tests.
It imports only the official Lean foundation. It does not need the #848
archive, upstream mathlib cache, a registry server, or a provider account.
Use the existing fork checkout and run commands from its root.

```text
python -m pip install -r Notary/requirements.txt
python -m unittest discover -s scripts -p "test_*.py" -v
python scripts/notary_reference_experiment.py
```

The experiment is standalone and requires no private orchestration service.
Its admission operations acquire an exclusive local execution lease and
preserve authenticated acceptance records. Results are written to
`.notary/reference-v1/result.json`; its `evidence_directory`
contains requests, checker reports, logs, public packages, and consumer locks.
Generated private keys remain inside ignored local state and are not published.
Do not transfer that state when testing an independent consumer.
After an interrupted or failed fixture, the experiment can resume its local
work directory and reuse successful publisher artifacts and authenticated
acceptance records. It always creates a fresh receiver and a fresh plain-Lake
baseline project. The result states whether publisher/consumer/application
builds were reused; their timings must not be relabelled as cold builds.

The experiment uses a tree data type and two distinct theorems: mirroring twice
restores the tree, and mirroring preserves the number of leaves. An ordinary
default `lake build` target imports both declarations into a round-trip package.
A third package proves payload correctness and frame-size correctness using
both of the second package's theorems. The checker reports the actual referenced
declarations; the test rejects a third package that merely restates independent
trivial facts. There are six separately signed public conclusions across these
three projects. The existing eight-layer experiment tests deeper wrapping.

The runner also measures a plain Lake build of the provider source, its warm
cache, content-and-credit checking, cold/warm notary admission, warm ordinary
Lake consumption, and a source dependency update with unchanged mathematics.
These are single-run latency observations of different assurance levels, not
an equal-work benchmark or a statistical performance study. The workstation
load and operating-system file cache are not controlled: "cold" means fresh
project/acceptance state, not cold disk, a fresh OS, or a timed download. The update must
change identity, require an explicit lock update, and receive fresh admission.

## Export another module

Create an export config in your project, listing every local module in build
order, its selected theorem names and permitted logical foundations:

```json
{
  "source_root": "Provider",
  "modules": [{
    "module": "NotaryExample.Trees",
    "declarations": ["NotaryExample.Tree.mirror_twice", "NotaryExample.Tree.leaves_mirror"]
  }],
  "allowed_axioms": []
}
```

Use `Notary/Examples/provider.json` for a working config. The initial reference
profile expects the full non-foundation closure to come from listed local
modules and admitted dependency bundles. It does not automatically turn an
arbitrary existing Lake package graph into publications.

```text
python scripts/notary_cli.py build --config Notary/Examples/provider.json --store .notary/manual/packages --state .notary/manual/publisher --provider "Your provider name" --key .notary/manual/publisher/provider.pem --result .notary/manual/build.json
python scripts/notary_cli.py inspect --bundle PATH_FROM_BUILD_RESULT
python scripts/notary_cli.py lock --bundle PATH_FROM_BUILD_RESULT --declaration NotaryExample.Tree.mirror_twice --declaration NotaryExample.Tree.leaves_mirror --out .notary/manual/consumer.lock.json
python scripts/notary_cli.py admit --bundle TRANSFERRED_PUBLIC_BUNDLE --lock .notary/manual/consumer.lock.json --state .notary/manual/consumer
```

`build` compiles source on a trusted publisher host, independently checks the
proof data, and only then signs certificates. `inspect` verifies bytes and
credits and explicitly does not claim kernel admission. `lock` is the
consumer's deliberate selection of an identity; automatically accepting a
publisher's suggested lock would defeat replacement detection.

For derived projects, add `dependencies` entries with `bundle` and `lock` paths
to the config. Their modules become available to normal Lean `import`.
`lake_project` in the experiment generates a default target whose result
depends on admission and compilation. A failed dependency check fails `lake
build` and replaces a previous success result with a failure record. A source
change produces a new content-addressed package. Credit identifies a provider
key and provider-declared name; it is not identity verification of that name.

## Cold reproduction by another operator

On a separately provisioned machine, obtain this implementation at an exact
commit, install the pinned toolchain and dependencies, and run the standalone
experiment above. The evaluated source-byte inventory is in `reference-result.json`.
Transfer only a public bundle and a separately obtained consumer lock. Create
fresh acceptance state and require `kernel_replays: 1` on initial admission;
unchanged repetition should report `kernel_replays: 0`. Never copy `host.key`
or the publisher's acceptance receipt into the consumer state.

The included automated cold test creates a separate process, transferred public
bytes, fresh state and a different host key **on the same physical machine**.
It is not evidence of another person reproducing the result, Linux compatibility,
or cross-platform binary transport. Independent operator/platform runs remain
an external validation milestone. A Lean version change requires a new profile
and proof realization; a signature cannot bridge that change.
