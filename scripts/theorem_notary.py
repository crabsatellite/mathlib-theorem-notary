#!/usr/bin/env python3
"""Glass Box theorem-component credit, archive binding, and Lean import tooling.

Provider signatures authenticate attribution only. The Erdos848 adapter reuses
an explicit immutable pre-receipt kernel archive; it never calls that a fresh
local replay. Consumers must explicitly select that assurance policy.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

from notary_fetch import safe_path, sha256

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / '.notary'
REGISTRY = ROOT / 'Notary' / 'erdos848.component.json'
ARCHIVE_MANIFEST_HASH = '3cbde25db4c5eac8209dd428cc5d95eab648766023db87418c8ea8c66353c527'
RELEASE_COMMIT = 'bb8e1b10b0066639ee3440ba983c3f9774667d42'
MATHLIB_COMMIT = '54e71fa9173471d591658f5380c46aaf050bbaae'
TOOLCHAIN = 'leanprover/lean4:v4.30.0-rc2'
REPO = 'https://github.com/crabsatellite/erdos-848-squarefree-product'
ENDPOINT = 'Erdos848.PaperGeneratedCertificateProvider.all_N'
MODULE = 'Erdos848.PaperGeneratedCertificateProvider'
STATEMENT = '∀ N, Erdos848.OriginalProblem848Statement N'
AXIOMS = ['Classical.choice', 'Quot.sound', 'propext']
DOMAIN = b'theorem-notary/provider-credit/v1\x00'


class NotaryError(ValueError):
    """An object failed a required component check."""


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def identity(obj: object, domain: str = 'component') -> str:
    return 'sha256:' + hashlib.sha256(('theorem-notary/' + domain + '/v1\x00').encode()
                                     + canonical(obj)).hexdigest()


def load(path: Path) -> dict:
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise NotaryError(f'Duplicate JSON key: {k}')
            obj[k] = v
        return obj
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_bytes(canonical(obj) + b'\n')
    os.replace(tmp, path)


def read_archive_manifest() -> dict:
    path = STORE / 'ERDOS848_OLEAN_CACHE_MANIFEST.json'
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = REPO + '/releases/download/v1.0.5-kernel/' + path.name
        with urlopen(url, timeout=90) as r:
            data = r.read(25 << 20)
        if hashlib.sha256(data).hexdigest() != ARCHIVE_MANIFEST_HASH:
            raise NotaryError('Downloaded archive manifest differs from locked identity')
        path.write_bytes(data)
    if sha256(path) != ARCHIVE_MANIFEST_HASH:
        raise NotaryError('Archive manifest was modified')
    manifest = load(path)
    if (manifest['public_commit'] != RELEASE_COMMIT or manifest['main_theorem'] != ENDPOINT
            or manifest['lean_toolchain'] != TOOLCHAIN
            or sorted(manifest['allowed_axioms']) != AXIOMS):
        raise NotaryError('Immutable archive contract mismatch')
    return manifest


def remote_evidence(name: str) -> tuple[dict, str]:
    """Read public evidence at the immutable release commit, never a branch tip."""
    path = safe_path(STORE / 'public-evidence', name)
    url = ('https://raw.githubusercontent.com/crabsatellite/erdos-848-squarefree-product/'
           + RELEASE_COMMIT + '/' + name)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(url, timeout=90) as r:
            path.write_bytes(r.read(32 << 20))
    return load(path), sha256(path)


def archive_core() -> tuple[dict, dict, dict]:
    """Derive every displayed assurance field from digest-locked public evidence."""
    manifest = read_archive_manifest()
    publication, pub_hash = remote_evidence('PUBLICATION_MANIFEST.json')
    if pub_hash != manifest['publication_manifest']['sha256']:
        raise NotaryError('Release publication manifest identity mismatch')
    pubfiles = {f['path']: f for f in publication['files']}
    proof_state, pipeline_hash = remote_evidence('proof-state.json')
    if pipeline_hash != pubfiles['proof-state.json']['sha256']:
        raise NotaryError('Kernel history is not bound to the release')
    evidence = proof_state['kernel_evidence']
    if (evidence['final_endpoint'] != ENDPOINT
            or evidence['mathematical_endpoint_status'] != 'trust-zero-kernel-checked'
            or sorted(evidence['mathematical_endpoint_axioms']) != AXIOMS
            or evidence['build_status'] != 'passed'
            or evidence['build_input_signature'] != manifest['provider_build_input_signature']):
        raise NotaryError('Kernel archive evidence does not identify this proof')
    endpoint_file = next(f for f in manifest['files']
                         if f['source_path'] == 'lean4/' + MODULE.replace('.', '/') + '.lean')
    core = {
        'schema': 'theorem-notary/component/v1', 'name': 'erdos848',
        'endpoint': {'module': MODULE, 'declaration': ENDPOINT, 'statement': STATEMENT,
                     'source_sha256': endpoint_file['source_sha256']},
        'foundation': {'toolchain': TOOLCHAIN, 'mathlib_commit': MATHLIB_COMMIT,
                       'allowed_axioms': AXIOMS},
        'source': {'repository': REPO, 'commit': RELEASE_COMMIT,
                   'publication_manifest_sha256': pub_hash,
                   'license_url': REPO + '/blob/' + RELEASE_COMMIT + '/LICENSE.md'},
        'proof_artifacts': {'manifest_url': REPO + '/releases/download/v1.0.5-kernel/'
                           'ERDOS848_OLEAN_CACHE_MANIFEST.json',
                           'manifest_sha256': ARCHIVE_MANIFEST_HASH,
                           'modules': manifest['summary']['modules'],
                           'platform': manifest['producer_platform']},
        'kernel_basis': {'class': 'grandfathered-kernel-archive',
                         'release_url': REPO + '/releases/tag/v1.0.5-kernel',
                         'record_url': REPO + '/blob/' + RELEASE_COMMIT + '/proof-state.json',
                         'record_sha256': pipeline_hash,
                         'build_input_signature': evidence['build_input_signature'],
                         'recorded_completed_at': evidence['build_finished_at'],
                         'fresh_local_replay': False},
    }
    return core, manifest, pubfiles


def validate_archive_descriptor(d: dict) -> dict:
    verify_descriptor(d)
    expected, manifest, _ = archive_core()
    if canonical(d['core']) != canonical(expected):
        raise NotaryError('Component is not covered by the historical archive adapter')
    return manifest


def prepare(source: Path) -> dict:
    core, manifest, pubfiles = archive_core()
    source = source.resolve()
    for f in manifest['files']:
        path = safe_path(source, f['source_path'])
        if not path.is_file() or sha256(path) != f['source_sha256']:
            raise NotaryError(f'Public Lean source differs from release: {f["source_path"]}')
        if pubfiles.get(f['source_path'], {}).get('sha256') != f['source_sha256']:
            raise NotaryError('Cache/source publication binding mismatch')
    for name in ('lean4/lean-toolchain', 'lean4/lake-manifest.json'):
        if sha256(source / name) != pubfiles[name]['sha256']:
            raise NotaryError(f'Pinned dependency configuration differs: {name}')
    lake = load(source / 'lean4/lake-manifest.json')
    mathlib = next(p for p in lake['packages'] if p['name'] == 'mathlib')
    if mathlib['rev'] != MATHLIB_COMMIT:
        raise NotaryError('Mathlib revision mismatch')
    descriptor = {'component_id': identity(core), 'core': core, 'credits': []}
    if REGISTRY.exists():
        prior = load(REGISTRY)
        if prior.get('component_id') == descriptor['component_id']:
            descriptor['credits'] = prior.get('credits', [])
    write(REGISTRY, descriptor)
    write(STORE / 'source-binding.json', {'component_id': descriptor['component_id'],
          'local_source': str(source), 'verified_source_modules': len(manifest['files']),
          'archive_evidence': 'matched', 'new_kernel_replay': False})
    return {'component_id': descriptor['component_id'], 'public_source_modules': len(manifest['files']),
            'kernel_basis': core['kernel_basis']['class']}


def verify_credit(record: dict, component_id: str) -> None:
    if record.get('schema') != 'theorem-notary/provider-credit/v1':
        raise NotaryError('Unsupported credit schema')
    body = record['body']
    if body.get('component_id') != component_id or body.get('role') != 'component-provider':
        raise NotaryError('Credit has the wrong component or role')
    try:
        pub = base64.b64decode(body['public_key'], validate=True)
        if body.get('key_fingerprint') != hashlib.sha256(pub).hexdigest():
            raise NotaryError('Provider fingerprint does not match the signing key')
        if body.get('mathematical_endorsement') is not False:
            raise NotaryError('Provider credit cannot assert mathematical endorsement')
        signature = base64.b64decode(record['signature'], validate=True)
        Ed25519PublicKey.from_public_bytes(pub).verify(signature, DOMAIN + canonical(body))
    except (ValueError, InvalidSignature) as e:
        raise NotaryError('Invalid provider credit signature') from e


def verify_descriptor(d: dict) -> None:
    if d.get('component_id') != identity(d['core']):
        raise NotaryError('Component content identity mismatch')
    if d['core'].get('schema') != 'theorem-notary/component/v1':
        raise NotaryError('Unsupported component schema')
    for credit in d.get('credits', []):
        verify_credit(credit, d['component_id'])


def credit(name: str, account: str, key_path: Path) -> dict:
    d = load(REGISTRY)
    validate_archive_descriptor(d)
    source_binding = load(STORE / 'source-binding.json')
    if source_binding.get('component_id') != d['component_id']:
        raise NotaryError('Run prepare before assigning component credit')
    if key_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise NotaryError('Provider credit requires an Ed25519 key')
    else:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        with key_path.open('xb') as f:
            f.write(key.private_bytes(serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    body = {'component_id': d['component_id'], 'role': 'component-provider',
            'display_name': name, 'account_url': account,
            'identity_scope': 'provider-declared account; key attribution only',
            'public_key': base64.b64encode(pub).decode(),
            'key_fingerprint': hashlib.sha256(pub).hexdigest(),
            'mathematical_endorsement': False}
    record = {'schema': 'theorem-notary/provider-credit/v1', 'body': body,
              'signature': base64.b64encode(key.sign(DOMAIN + canonical(body))).decode()}
    verify_credit(record, d['component_id'])
    d['credits'] = [r for r in d['credits'] if r['body']['public_key'] != body['public_key']] + [record]
    write(REGISTRY, d)
    return {'component_id': d['component_id'], 'provider': name,
            'fingerprint': body['key_fingerprint'], 'mathematical_endorsement': False}


def show() -> dict:
    d = load(REGISTRY)
    validate_archive_descriptor(d)
    return {'component_id': d['component_id'],
            'providers': [{'name': c['body']['display_name'], 'account': c['body']['account_url'],
                           'fingerprint': c['body']['key_fingerprint'], 'signature': 'valid'}
                          for c in d['credits']],
            'endpoint': d['core']['endpoint'], 'source': d['core']['source'],
            'foundation': d['core']['foundation'], 'kernel_basis': d['core']['kernel_basis'],
            'credit_is_mathematical_endorsement': False,
            'assurance': {'descriptor': 'matches-locked-archive-evidence',
                          'proof_bytes': 'not-checked-by-show',
                          'kernel': 'historical-record-only; no fresh upstream replay'}}


def materialize(allow_archive: bool) -> dict:
    if not allow_archive:
        raise NotaryError('This historical component requires explicit --allow-grandfathered-archive; '
                          'provider signatures alone cannot authorize an import')
    d = load(REGISTRY)
    manifest = validate_archive_descriptor(d)
    if not d['credits']:
        raise NotaryError('Published components must identify a provider')
    lib = STORE / 'erdos848/lib/lean'
    if (lib / '.notary-restore.lock').exists():
        raise NotaryError('Artifact restore is still running')
    expected_paths = {f['cache_path'].removeprefix('lean4/.lake/build/lib/lean/')
                      for f in manifest['files']}
    actual_paths = {p.relative_to(lib).as_posix() for p in lib.rglob('*') if p.is_file()}
    if actual_paths != expected_paths:
        raise NotaryError('Proof artifact inventory differs from the locked archive')
    # Full byte validation before trusting an imported prebuilt environment.
    for f in manifest['files']:
        rel = f['cache_path'].removeprefix('lean4/.lake/build/lib/lean/')
        path = safe_path(lib, rel)
        if not path.is_file() or path.stat().st_size != f['cache_bytes']:
            raise NotaryError(f'Missing proof artifact: {rel}; run notary_fetch.py')
        if sha256(path) != f['cache_sha256']:
            raise NotaryError(f'Proof artifact differs from kernel archive: {rel}')
    summary = show()
    summary['assurance']['proof_bytes'] = 'all-files-match-locked-archive'
    text = ('Provider credit (not a mathematical endorsement):\n'
            + json.dumps(summary, ensure_ascii=False, indent=2))
    source = ('import Notary\nimport ' + MODULE + '\n\n'
              + 'notary_credit ' + ENDPOINT + ' := ' + json.dumps(text, ensure_ascii=False) + '\n\n'
              + '/-- Literal external reuse of the published all-N endpoint. -/\n'
              + 'theorem NotaryErdos848.external_all_N :\n'
              + '    ∀ N, Erdos848.OriginalProblem848Statement N :=\n'
              + '  ' + ENDPOINT + '\n\n'
              + '#notary_info ' + ENDPOINT + '\n'
              + '#notary_inspect ' + ENDPOINT + '\n'
              + '#notary_inspect Erdos848.PaperGeneratedCertificateProvider.tailClose\n'
              + '#print axioms NotaryErdos848.external_all_N\n')
    generated = STORE / 'NotaryErdos848.lean'
    generated.write_text(source, encoding='utf-8')
    result = {'component_id': d['component_id'], 'artifact_identity': 'all-files-verified',
              'kernel_basis': 'grandfathered-kernel-archive', 'fresh_local_replay': False,
              'generated_source': str(generated), 'source_sha256': sha256(generated),
              'library_path': str(lib)}
    write(STORE / 'import-binding.json', result)
    return result


def lean_env() -> dict[str, str]:
    env = dict(os.environ)
    # Do not let arbitrary caller-supplied search paths shadow locked modules.
    env['LEAN_PATH'] = str(STORE / 'erdos848/lib/lean')
    return env


def _check_import(bound: dict) -> dict:
    d = load(REGISTRY)
    verify_descriptor(d)
    generated = STORE / 'NotaryErdos848.lean'
    if bound['component_id'] != d['component_id'] or sha256(generated) != bound['source_sha256']:
        raise NotaryError('Materialized import is stale')
    # The large source proof is not rebuilt. Only this new external consumer is elaborated.
    # Required expensive verification is orchestrated through Paper Infrastructure externally.
    consumer = STORE / 'consumer/lib/lean/NotaryErdos848.olean'
    consumer.parent.mkdir(parents=True, exist_ok=True)
    consumer.unlink(missing_ok=True)
    argv = ['lake', 'env', 'lean', '--trust=0', '-M32768', '-o', str(consumer), str(generated)]
    run = subprocess.run(argv, cwd=ROOT, env=lean_env(), text=True, encoding='utf-8',
                         errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = run.stdout
    (STORE / 'external-import.log').write_text(output, encoding='utf-8')
    print(output, end='')
    if run.returncode:
        raise NotaryError(f'External Lean consumer failed ({run.returncode})')
    matches = re.findall(r"'NotaryErdos848\.external_all_N' depends on axioms: \[([^]]*)\]", output)
    if len(matches) != 1 or sorted(x.strip() for x in matches[0].split(',')) != AXIOMS:
        raise NotaryError('External endpoint axiom surface differs from the exact contract')
    declarations = [json.loads(line.split('NOTARY_DECLARATION ', 1)[1])
                    for line in output.splitlines() if line.startswith('NOTARY_DECLARATION ')]
    if {x['declaration'] for x in declarations} != {
            ENDPOINT, 'Erdos848.PaperGeneratedCertificateProvider.tailClose'}:
        raise NotaryError('Missing theorem-level export inspection')
    if any(sorted(x['axioms']) != AXIOMS for x in declarations):
        raise NotaryError('Selected theorem exceeds the declared foundation')
    write(STORE / 'erdos848-declarations.json', {'declarations': declarations,
          'component_id': d['component_id'], 'kernel_basis': 'grandfathered-kernel-archive'})
    result = {'external_consumer': 'kernel-checked', 'component_id': d['component_id'],
              'upstream_basis': 'grandfathered-kernel-archive', 'fresh_upstream_replay': False,
              'consumer_artifact': str(consumer), 'consumer_sha256': sha256(consumer),
              'inspected_declarations': [x['declaration'] for x in declarations],
              'log_sha256': hashlib.sha256(output.encode()).hexdigest()}
    write(STORE / 'external-import-result.json', result)
    print('notary_external_import=passed')
    return result


def build(allow_archive: bool) -> dict:
    # A stale success file must not survive any rejected verification attempt.
    (STORE / 'external-import-result.json').unlink(missing_ok=True)
    bound = materialize(allow_archive)
    return _check_import(bound)


def main() -> int:
    # Native Windows consoles commonly default to GBK; theorem types need Unicode.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--source', type=Path, required=True)
    p = sub.add_parser('credit')
    p.add_argument('--name', required=True)
    p.add_argument('--account', required=True)
    p.add_argument('--key', type=Path, default=STORE / 'keys/provider.pem')
    sub.add_parser('show')
    p = sub.add_parser('materialize')
    p.add_argument('--allow-grandfathered-archive', action='store_true')
    p = sub.add_parser('build')
    p.add_argument('--allow-grandfathered-archive', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.source)
        elif args.command == 'credit':
            result = credit(args.name, args.account, args.key)
        elif args.command == 'show':
            result = show()
        elif args.command == 'materialize':
            result = materialize(args.allow_grandfathered_archive)
        elif args.command == 'build':
            result = build(args.allow_grandfathered_archive)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (NotaryError, OSError, KeyError, StopIteration) as e:
        print(f'notary: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
