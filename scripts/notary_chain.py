#!/usr/bin/env python3
"""Transitive content binding. Integrity success is never kernel admission.

The root is supplied by the consumer's independent lock, not the downloaded graph.
Source/olean identity, dependency edges, foundations and credits are all checked.
Kernel execution remains the separate host-controlled build/receipt contract.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from notary_fetch import safe_path, sha256
from theorem_notary import NotaryError, identity, load, verify_descriptor


def verify_graph(root: str, documents: dict[str, dict], artifacts: Path,
                 foundation: dict) -> dict:
    active: set[str] = set()
    checked: set[str] = set()
    owners: dict[str, str] = {}
    layers: dict[str, int] = {}
    if root not in documents:
        raise NotaryError('Consumer-locked root is missing; never adopt an advertised root')

    def visit(cid: str) -> None:
        if cid in active:
            raise NotaryError('Cyclic component dependency')
        if cid in checked:
            return
        if cid not in documents:
            raise NotaryError('Missing transitive dependency')
        d = documents[cid]
        verify_descriptor(d)
        if d['component_id'] != cid:
            raise NotaryError('Dependency lookup identity mismatch')
        core = d['core']
        fields = {'schema', 'kind', 'module', 'endpoint', 'statement', 'foundation',
                  'dependencies', 'files'}
        if set(core) != fields or core['kind'] != 'checked-module-reference':
            raise NotaryError('Unsupported chain node or self-declared assurance')
        if core['foundation'] != foundation:
            raise NotaryError('Transitive logical foundation mismatch')
        if not d.get('credits'):
            raise NotaryError('Component provider credit is missing')
        deps = core['dependencies']
        if not isinstance(deps, list) or not all(isinstance(x, str) for x in deps):
            raise NotaryError('Invalid dependency list')
        if len(set(deps)) != len(deps):
            raise NotaryError('Duplicate dependency')
        module = core['module']
        module_identity = identity({'module': module, 'files': core['files'],
                                    'foundation': core['foundation']}, 'module-realization')
        if module in owners and owners[module] != module_identity:
            raise NotaryError('Two components compete for the same Lean module')
        owners[module] = module_identity
        if set(core['files']) != {'source', 'olean'}:
            raise NotaryError('Source and actual imported proof artifact are both required')
        for role, record in core['files'].items():
            if set(record) != {'path', 'sha256'}:
                raise NotaryError('Malformed artifact identity')
            expected = module.replace('.', '/') + ('.lean' if role == 'source' else '.olean')
            if record['path'] != expected:
                raise NotaryError('Module-to-file binding mismatch')
            path = safe_path(artifacts, record['path'])
            if not path.is_file() or sha256(path) != record['sha256']:
                raise NotaryError('Transitive artifact identity mismatch: ' + record['path'])
        active.add(cid)
        for dep in deps:
            visit(dep)
        active.remove(cid)
        layers[cid] = 1 + max((layers[x] for x in deps), default=0)
        checked.add(cid)

    visit(root)
    return {'locked_root': root, 'integrity': 'verified', 'nodes': len(checked),
            'depth': layers[root], 'mathematical_admission': 'requires-host-kernel-receipt',
            'signature_is_proof': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--graph', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    lock, graph = load(args.lock), load(args.graph)
    try:
        result = verify_graph(lock['root'], graph['components'], args.artifacts, lock['foundation'])
        print(json.dumps(result, indent=2))
        return 0
    except (NotaryError, OSError, ValueError, KeyError) as error:
        print(f'chain rejected: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
