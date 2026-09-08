#!/usr/bin/env python3
"""Actual eight-module/two-theorem kernel fixture and hostile admission checks.

This host-owned recipe deliberately compiles controlled Lean fixtures. It is not
an execution sandbox or an admission service for arbitrary uploaded metaprograms.
Every declaration gets its own certificate; module bytes are shared.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from notary_chain import verify_graph
from notary_fetch import sha256
from theorem_notary import DOMAIN, ROOT, STORE, TOOLCHAIN, NotaryError, canonical, identity, write

FOUNDATION = {'toolchain': TOOLCHAIN, 'allowed_axioms': [],
              'profile': 'host-controlled-fresh-fixture-with-official-Lean-base'}


def sign(core: dict, key: Ed25519PrivateKey) -> dict:
    cid = identity(core)
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    body = {'component_id': cid, 'role': 'component-provider',
            'display_name': 'Generated test provider; not a human identity',
            'public_key': base64.b64encode(pub).decode(),
            'key_fingerprint': hashlib.sha256(pub).hexdigest(), 'mathematical_endorsement': False}
    return {'component_id': cid, 'core': core, 'credits': [{
        'schema': 'theorem-notary/provider-credit/v1', 'body': body,
        'signature': base64.b64encode(key.sign(DOMAIN + canonical(body))).decode()}]}


def compile_and_inspect(folder: Path, module: str, source: str,
                        endpoints: list[str]) -> list[dict]:
    path = folder / (module + '.lean')
    path.write_text(source + ''.join('#notary_inspect ' + e + '\n' for e in endpoints),
                    encoding='utf-8')
    artifact = folder / (module + '.olean')
    artifact.unlink(missing_ok=True)
    env = dict(os.environ, LEAN_PATH=str(folder))
    result = subprocess.run(['lake', 'env', 'lean', '--trust=0', '-o', str(artifact), str(path)],
                            cwd=ROOT, env=env, encoding='utf-8', errors='replace', text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (folder / (module + '.log')).write_text(result.stdout, encoding='utf-8')
    if result.returncode:
        raise NotaryError('Lean rejected module ' + module + ': ' + result.stdout[-1000:])
    observed = [json.loads(line[len('NOTARY_DECLARATION '):])
                for line in result.stdout.splitlines() if line.startswith('NOTARY_DECLARATION ')]
    if len(observed) != len(endpoints) or {x['declaration'] for x in observed} != set(endpoints):
        raise NotaryError('Missing, duplicate, or substituted declaration inspection')
    if any(x['axioms'] for x in observed):
        raise NotaryError('Kernel foundation audit rejected additional axioms')
    return observed


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    folder = STORE / 'chain-demo'
    folder.mkdir(parents=True, exist_ok=True)
    result_path = folder / 'result.json'
    result_path.unlink(missing_ok=True)
    graph: dict[str, dict] = {}
    prior = []
    key = Ed25519PrivateKey.generate()  # ephemeral test identity; never the user's key
    for depth in range(8):
        module = f'NotaryLayer{depth}'
        previous = f'NotaryLayer{depth - 1}'
        source = 'import Notary\n' + (f'import {previous}\n' if depth else '')
        source += f'namespace {module}\n'
        source += ('theorem identity : ∀ n : Nat, n = n := '
                   + (f'{previous}.identity' if depth else 'fun _ => rfl') + '\n')
        source += ('theorem successor : ∀ n : Nat, n + 1 = n + 1 := '
                   + (f'{previous}.successor' if depth else 'fun _ => rfl') + '\n')
        source += f'end {module}\n'
        endpoints = [module + '.identity', module + '.successor']
        declarations = compile_and_inspect(folder, module, source, endpoints)
        current = []
        for declaration in declarations:
            core = {'schema': 'theorem-notary/component/v1', 'kind': 'checked-module-reference',
                    'module': module, 'endpoint': declaration['declaration'],
                    'statement': {'type_expr': declaration['type_expr'],
                                  'level_params': declaration['level_params']},
                    'foundation': FOUNDATION, 'dependencies': prior,
                    'files': {role: {'path': module + ext,
                                     'sha256': sha256(folder / (module + ext))}
                              for role, ext in [('source', '.lean'), ('olean', '.olean')]}}
            d = sign(core, key)
            graph[d['component_id']] = d
            current.append(d['component_id'])
        prior = current
        print(f'kernel_fixture_layer={depth + 1}; individually_certified_theorems=2', flush=True)
    results = [verify_graph(cid, graph, folder, FOUNDATION) for cid in prior]
    write(folder / 'graph.json', {'components': graph})
    for index, cid in enumerate(prior):
        write(folder / f'consumer-{index}.lock.json', {'root': cid, 'foundation': FOUNDATION})
    attacks = []
    # Change actual compiled proof bytes after a successful real kernel build.
    for layer in range(8):
        path = folder / f'NotaryLayer{layer}.olean'
        data = path.read_bytes()
        try:
            path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            try:
                verify_graph(prior[0], graph, folder, FOUNDATION)
            except NotaryError:
                attacks.append(f'compiled-layer-{layer}-tamper-rejected')
            else:
                raise RuntimeError('Undetected compiled artifact modification')
        finally:
            path.write_bytes(data)
    # Lean can exit successfully with sorry or custom axioms. Admission must fail.
    bad_sources = {
        'NotaryAttackSorry': 'theorem forged : False := by sorry\n',
        'NotaryAttackAxiom': 'axiom hidden : False\ntheorem forged : False := hidden\n',
        'NotaryAttackWrongType': 'theorem forged : False := True.intro\n',
        'NotaryAttackAxiomExport': 'axiom forged : False\n',
    }
    for module, body in bad_sources.items():
        try:
            compile_and_inspect(folder, module,
                                f'import Notary\nnamespace {module}\n{body}end {module}\n',
                                [module + '.forged'])
        except NotaryError:
            attacks.append(module + '-rejected')
        else:
            raise RuntimeError('Invalid theorem acquired an eligible certificate: ' + module)
    result = {'status': 'passed', 'layers': 8, 'theorems_per_module': 2,
              'independent_certificates': len(graph), 'consumer_roots': prior,
              'chain_integrity': results, 'attacks_rejected': attacks,
              'kernel_scope': 'controlled fresh modules over the fixed official Lean base',
              'arbitrary_hostile_metaprogram_sandbox': 'not_implemented'}
    write(result_path, result)
    print(json.dumps(result, indent=2))
    print('notary_chain_kernel_and_attacks=passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
