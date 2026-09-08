"""Portable, declaration-level reference profile; see Notary/SPEC.md.

The checker receives proof data, never publisher scripts or purported receipts.
Source compilation is an explicit publisher-side operation in a trusted build
environment. Hostile native code isolation is outside this profile.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from notary_fetch import safe_path, sha256
from theorem_notary import ROOT, TOOLCHAIN, DOMAIN, NotaryError, load, verify_descriptor, write

PROFILE = 'theorem-notary/lean-4.30-fresh/v1'
VERIFIER = ROOT / 'Notary/Verifier.lean'


def canonical(value) -> bytes:
    def check(x):
        if x is None or type(x) is bool: return
        if type(x) is int and abs(x) <= 9007199254740991: return
        if type(x) is str:
            x.encode('utf-8', errors='strict')
            return
        if type(x) is list:
            for item in x: check(item)
            return
        if type(x) is dict and all(type(k) is str for k in x):
            for k, v in x.items(): check(k); check(v)
            return
        raise NotaryError('Noncanonical value: only scalar Unicode, safe integers and JSON containers')
    check(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def digest(value, domain='component'):
    return 'sha256:' + hashlib.sha256(('theorem-notary/' + domain + '/v1\0').encode()
                                     + canonical(value)).hexdigest()


def lean_binary() -> Path:
    if (ROOT / 'lean-toolchain').read_text().strip() != TOOLCHAIN:
        raise NotaryError('Unsupported toolchain')
    p = subprocess.run(['elan', 'which', 'lean'], cwd=ROOT, check=True,
                       capture_output=True, text=True, encoding='utf-8')
    return Path(p.stdout.strip()).resolve()


def protected_key(path: Path, provider=False):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
                if provider else secrets.token_bytes(32))
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(data)
        if os.name == 'nt':
            account = subprocess.check_output(['whoami'], text=True).strip()
            subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', account + ':F'],
                           check=True, stdout=subprocess.DEVNULL)
    data = path.read_bytes()
    if provider:
        key = serialization.load_pem_private_key(data, password=None)
        if not isinstance(key, Ed25519PrivateKey): raise NotaryError('Expected Ed25519 key')
        return key
    if len(data) != 32: raise NotaryError('Invalid host key')
    return data


def sign_declaration(core, key, provider):
    cid = digest(core)
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    body = {'component_id': cid, 'role': 'component-provider', 'display_name': provider,
            'identity_scope': 'key attribution only; name is provider-declared',
            'public_key': base64.b64encode(pub).decode(),
            'key_fingerprint': hashlib.sha256(pub).hexdigest(), 'mathematical_endorsement': False}
    return {'component_id': cid, 'core': core, 'credits': [{
        'schema': 'theorem-notary/provider-credit/v1', 'body': body,
        'signature': base64.b64encode(key.sign(DOMAIN + canonical(body))).decode()}]}


def inventory(folder: Path, paths: list[str]) -> list[dict]:
    return [{'path': name, 'sha256': sha256(safe_path(folder, name))}
            for name in sorted(paths)]


def certificates_in(bundle):
    result = {c['component_id']: c for c in bundle['certificates']}
    for dependency in bundle['dependencies']:
        result.update((c['component_id'], c) for c in certificates_in(dependency))
    return [result[k] for k in sorted(result)]


def dependency_binding(bundle):
    return {'bundle_id': bundle['bundle_id'],
            'certificates': sorted(c['component_id'] for c in bundle['certificates'])}


def validate_lock(locked: dict) -> None:
    """Require a real consumer selection, including before authenticated reuse."""
    if (type(locked) is not dict
            or set(locked) != {'schema', 'profile', 'bundle_id', 'certificates'}
            or locked['schema'] != 'theorem-notary/consumer-lock/v1'
            or locked['profile'] != PROFILE):
        raise NotaryError('Malformed consumer lock')
    valid_id = lambda x: type(x) is str and re.fullmatch(r'sha256:[0-9a-f]{64}', x)
    selected = locked['certificates']
    if (not valid_id(locked['bundle_id']) or type(selected) is not list or not selected
            or not all(valid_id(x) for x in selected) or len(selected) != len(set(selected))):
        raise NotaryError('Consumer lock requires distinct selected certificate identities')


def validate_certificate_envelope(cert: dict) -> None:
    if type(cert) is not dict or set(cert) != {'component_id', 'core', 'credits'}:
        raise NotaryError('Unsupported declaration envelope fields')
    if type(cert['credits']) is not list or not cert['credits']:
        raise NotaryError('Declaration requires provider credit')
    required = {'component_id', 'role', 'display_name', 'identity_scope', 'public_key',
                'key_fingerprint', 'mathematical_endorsement'}
    for credit in cert['credits']:
        if type(credit) is not dict or set(credit) != {'schema', 'body', 'signature'}:
            raise NotaryError('Unsupported credit envelope fields')
        body = credit['body']
        if (type(body) is not dict or not required <= set(body)
                or type(body['display_name']) is not str
                or body['identity_scope'] != 'key attribution only; name is provider-declared'):
            raise NotaryError('Malformed provider attribution')
        for encoded in (body['public_key'], credit['signature']):
            if (type(encoded) is not str or
                    base64.b64encode(base64.b64decode(encoded, validate=True)).decode() != encoded):
                raise NotaryError('Noncanonical Base64 credit encoding')


def verify_bundle(folder: Path, locked: dict | None = None, document=None, depth=0) -> dict:
    if locked is not None: validate_lock(locked)
    if depth > 64: raise NotaryError('Dependency nesting exceeds the v1 resource limit')
    bundle = load(folder / 'bundle.json') if document is None else document
    canonical(bundle)
    if set(bundle) != {'bundle_id', 'core', 'certificates', 'dependencies'}:
        raise NotaryError('Unsupported publication fields')
    core = bundle['core']
    if set(core) != {'schema', 'profile', 'toolchain', 'modules', 'files', 'dependencies'}:
        raise NotaryError('Unsupported bundle fields')
    if (core['schema'] != 'theorem-notary/bundle/v1' or core['profile'] != PROFILE
            or core['toolchain'] != TOOLCHAIN):
        raise NotaryError('Unsupported proof profile')
    if bundle['bundle_id'] != digest(core, 'bundle'):
        raise NotaryError('Bundle identity mismatch')
    if locked is not None and locked['bundle_id'] != bundle['bundle_id']:
        raise NotaryError('Consumer-locked bundle changed')
    files = core['files']
    paths = [f['path'] for f in files]
    if len(paths) != len(set(paths)) or files != inventory(folder, paths):
        raise NotaryError('Proof/source byte inventory mismatch')
    actual = {p.relative_to(folder).as_posix() for directory in ('src', 'objects')
              for p in (folder / directory).rglob('*') if p.is_file()}
    if (document is None and actual != set(paths)) or not set(paths) <= actual:
        raise NotaryError('Unlisted or missing source/proof data')
    modules = core['modules']
    expected = set()
    for module, parts in modules.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(\.[A-Za-z_][A-Za-z_0-9]*)*', module):
            raise NotaryError('Unsupported module name')
        name = module.replace('.', '/')
        source = 'src/' + name + '.lean'
        if not parts or parts[0] != 'objects/' + name + '.olean':
            raise NotaryError('Module-to-artifact mapping mismatch')
        permitted = {'objects/' + name + s for s in ('.olean', '.olean.server', '.olean.private')}
        ordered = ['objects/' + name + ext for ext in ('.olean', '.olean.server', '.olean.private')
                   if 'objects/' + name + ext in parts]
        if type(parts) is not list or parts != ordered or not set(parts) <= permitted:
            raise NotaryError('Unexpected or noncanonical module parts')
        expected.update([source, *parts])
    if expected != set(paths): raise NotaryError('Incomplete module inventory')
    certificates = bundle['certificates']
    seen = set()
    for cert in certificates:
        validate_certificate_envelope(cert)
        verify_descriptor(cert)
        c = cert['core']
        if set(c) != {'schema', 'kind', 'bundle_id', 'interface', 'allowed_axioms'}:
            raise NotaryError('Unsupported declaration fields')
        if (c['schema'] != 'theorem-notary/component/v1' or c['kind'] != 'declaration-export' or c['bundle_id'] != bundle['bundle_id']
                or not cert['credits']):
            raise NotaryError('Declaration/bundle/credit mismatch')
        if (set(c['interface']) != {'declaration', 'type_expr', 'level_params'}
                or not set(c['allowed_axioms']) <= {'propext', 'Classical.choice', 'Quot.sound'}):
            raise NotaryError('Invalid declaration interface or logical foundation')
        if c['interface']['declaration'] in seen: raise NotaryError('Duplicate declaration export')
        seen.add(c['interface']['declaration'])
    if not certificates: raise NotaryError('No theorem selected for publication')
    dependencies = bundle['dependencies']
    if sorted((dependency_binding(d) for d in dependencies), key=lambda d: d['bundle_id']) != core['dependencies']:
        raise NotaryError('Missing or substituted dependency publication')
    for dependency in dependencies:
        if not set(dependency['core']['modules']) <= set(modules):
            raise NotaryError('Missing transitive module closure')
        if any(modules[name] != parts for name, parts in dependency['core']['modules'].items()):
            raise NotaryError('Inherited module proof-data parts changed')
        verify_bundle(folder, document=dependency, depth=depth + 1)
    if locked is not None and not set(locked['certificates']) <= {c['component_id'] for c in certificates}:
        raise NotaryError('Consumer-locked declaration changed or disappeared')
    return bundle


def make_lock(folder: Path, declarations: list[str]) -> dict:
    bundle = verify_bundle(folder)
    certs = {c['core']['interface']['declaration']: c['component_id'] for c in bundle['certificates']}
    if not declarations or not set(declarations) <= set(certs):
        raise NotaryError('Requested declaration has no provider certificate')
    return {'schema': 'theorem-notary/consumer-lock/v1', 'profile': PROFILE,
            'bundle_id': bundle['bundle_id'], 'certificates': [certs[x] for x in declarations]}


def checker(folder: Path, modules: list[str], declarations: list[str], allowed: list[str],
            state: Path, binary: Path, replay=True) -> tuple[dict, int]:
    stdlib = binary.parent.parent / 'lib/lean'
    for artifact in (folder / 'objects').rglob('*.olean*'):
        if (stdlib / artifact.relative_to(folder / 'objects')).exists():
            raise NotaryError('Publisher module shadows the trusted toolchain: ' + artifact.name)
    request = {'modules': modules, 'declarations': declarations,
               'allowed_axioms': allowed, 'replay': replay, 'objects': str((folder / 'objects').resolve())}
    token = secrets.token_hex(8)
    request_path, output_path = state / (token + '.request.json'), state / (token + '.result.json')
    state.mkdir(parents=True, exist_ok=True)
    write(request_path, request)
    env = dict(os.environ, LEAN_PATH='')
    start = time.monotonic()
    result = subprocess.run([str(binary), '--run', str(VERIFIER), str(request_path), str(output_path)],
                            cwd=ROOT, env=env, capture_output=True, encoding='utf-8', errors='replace')
    elapsed = round((time.monotonic() - start) * 1000)
    (state / (token + '.log')).write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode or not output_path.exists():
        raise NotaryError('Independent kernel checker rejected: ' + (result.stdout + result.stderr)[-1800:])
    checked = load(output_path)
    if checked['kernel_replayed'] is not replay or checked['extensions_initialized'] is not False:
        raise NotaryError('Checker assurance mismatch')
    if checked.get('original_declarations_checked') is not True:
        raise NotaryError('Original declaration coverage was not checked')
    if {x['interface']['declaration'] for x in checked['declarations']} != set(declarations):
        raise NotaryError('Checker selected a different declaration')
    return checked, elapsed


def actual_closure(folder: Path, report: dict, binary: Path) -> tuple[set[str], list[dict]]:
    objects = (folder / 'objects').resolve()
    stdlib = (binary.parent.parent / 'lib/lean').resolve()
    own, base = set(), []
    for module in report['modules']:
        own_module = None
        for filename in module['parts']:
            path = Path(filename).resolve()
            if path.is_relative_to(objects):
                classification = True
            elif path.is_relative_to(stdlib):
                classification = False
                base.append({'path': str(path), 'sha256': sha256(path)})
            else:
                raise NotaryError('Uncontrolled import search path: ' + str(path))
            if own_module is not None and own_module != classification:
                raise NotaryError('Module parts originate from different trust domains')
            own_module = classification
        if own_module: own.add(module['module'])
    return own, sorted(base, key=lambda x: x['path'])


def admission_scope(folder: Path, bundle: dict, binary: Path, base: list[dict]) -> dict:
    current_base = [{'path': f['path'], 'sha256': sha256(Path(f['path']))} for f in base]
    return {'bundle_id': bundle['bundle_id'], 'files': inventory(folder, [f['path'] for f in bundle['core']['files']]),
            'interfaces': [c['core'] for c in certificates_in(bundle)],
            'checker_sha256': sha256(VERIFIER), 'runner_sha256': sha256(Path(__file__)),
            'lean_binary_sha256': sha256(binary), 'foundation_files': current_base}


def check_realization_coverage(bundle: dict, report: dict, supplied: set[str]) -> None:
    """Audit every nested certificate in its own realization, not the outer union.

    Identical original declarations can have multiple module origins. At least
    one origin must be available in this realization or the trusted installation.
    Module import headers are checked too, including unused explicit imports.
    """
    modules = {row['module']: row for row in report['modules']}
    foundation = set(modules) - supplied
    observed = {row['interface']['declaration']: row for row in report['declarations']}
    own = set(bundle['core']['modules'])
    available = own | foundation
    if not own <= set(modules):
        raise NotaryError('Realization module absent from checker report')
    for name in own:
        if not set(modules[name]['imports']) <= available:
            raise NotaryError('Realization omits an actual module import: ' + name)
    for cert in bundle['certificates']:
        expected = cert['core']
        row = observed[expected['interface']['declaration']]
        if (row['interface'] != expected['interface']
                or not set(row['axioms']) <= set(expected['allowed_axioms'])):
            raise NotaryError('Actual declaration or foundation differs from its signed certificate')
        alternatives = row['dependency_module_alternatives']
        if not alternatives or any(not available.intersection(names) for names in alternatives):
            raise NotaryError('Realization omits an original proof dependency: '
                              + expected['interface']['declaration'])
    for dependency in bundle['dependencies']:
        check_realization_coverage(dependency, report, supplied)


def admit(folder: Path, locked: dict, state: Path) -> dict:
    validate_lock(locked)
    folder, state = folder.resolve(), state.resolve()
    if state.is_relative_to(folder):
        raise NotaryError('Local acceptance state must be outside the publisher bundle')
    bundle = verify_bundle(folder, locked)
    state.mkdir(parents=True, exist_ok=True)
    key = protected_key(state / 'host.key')
    binary = lean_binary()
    receipt_path = state / (bundle['bundle_id'].split(':')[1] + '.receipt.json')
    lease = state / 'admission.lock'
    with lease.open('x') as stream: stream.write(str(os.getpid()))
    try:
        if receipt_path.exists():
            receipt = load(receipt_path)
            body = receipt['body']
            if not hmac.compare_digest(receipt['signature'], hmac.new(key, canonical(body), hashlib.sha256).hexdigest()):
                raise NotaryError('Invalid local admission receipt; publisher receipts are not accepted')
            if body['scope'] == admission_scope(folder, bundle, binary, body['scope']['foundation_files']):
                return {'status': 'reused', 'kernel_replays': 0, 'bundle_id': bundle['bundle_id'],
                        'receipt': str(receipt_path), 'checker_report': body['checker_report']}
        before = inventory(folder, [f['path'] for f in bundle['core']['files']])
        certs = certificates_in(bundle)
        names = sorted({c['core']['interface']['declaration'] for c in certs})
        allowed = sorted({a for c in certs for a in c['core']['allowed_axioms']})
        report, elapsed = checker(folder, list(bundle['core']['modules']), names, allowed, state, binary)
        own, base = actual_closure(folder, report, binary)
        if own != set(bundle['core']['modules']): raise NotaryError('Actual import closure differs from bundle')
        check_realization_coverage(bundle, report, own)
        verify_bundle(folder, locked)
        if before != inventory(folder, [f['path'] for f in bundle['core']['files']]):
            raise NotaryError('Proof bytes changed during checking')
        body = {'scope': admission_scope(folder, bundle, binary, base), 'checker_report': report}
        write(receipt_path, {'body': body, 'signature': hmac.new(key, canonical(body), hashlib.sha256).hexdigest()})
        return {'status': 'created', 'kernel_replays': 1, 'kernel_ms': elapsed,
                'bundle_id': bundle['bundle_id'], 'receipt': str(receipt_path), 'checker_report': report}
    finally:
        lease.unlink()


def export(config_path: Path, folder: Path, state: Path, provider: str, key_path: Path) -> dict:
    cfg = load(config_path)
    source = (config_path.parent / cfg['source_root']).resolve()
    folder, state = folder.resolve(), state.resolve()
    if folder.exists() and any(folder.iterdir()): raise NotaryError('Export destination must be empty')
    objects = folder / 'objects'
    objects.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    dependencies = []
    inherited = {}
    for dependency in cfg.get('dependencies', []):
        dep = (config_path.parent / dependency['bundle']).resolve()
        lock = load((config_path.parent / dependency['lock']).resolve())
        admit(dep, lock, state / 'dependency-admission')
        b = verify_bundle(dep, lock)
        dependencies.append(b)
        for f in b['core']['files']:
            target = safe_path(folder, f['path'])
            if target.exists() and sha256(target) != f['sha256']:
                raise NotaryError('Dependency module collision')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(dep, f['path']), target)
        inherited.update(b['core']['modules'])
    binary = lean_binary()
    env = dict(os.environ, LEAN_PATH=str(objects))
    roots, declarations = [], []
    start = time.monotonic()
    for spec in cfg['modules']:
        module = spec['module']
        if module in inherited: raise NotaryError('Publisher module shadows an imported module')
        rel = module.replace('.', '/')
        original = safe_path(source, rel + '.lean')
        copied = safe_path(folder, 'src/' + rel + '.lean')
        artifact = safe_path(objects, rel + '.olean')
        copied.parent.mkdir(parents=True, exist_ok=True)
        artifact.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, copied)
        result = subprocess.run([str(binary), '--trust=0', '--root=' + str(folder / 'src'),
                                 '-o', str(artifact), str(copied)], env=env, cwd=ROOT,
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode: raise NotaryError('Publisher build failed: ' + result.stdout + result.stderr)
        roots.append(module)
        declarations.extend(spec['declarations'])
    build_ms = round((time.monotonic() - start) * 1000)
    # Sign only after independent replay of the actual compiled environment.
    inherited_certs = [c for b in dependencies for c in certificates_in(b)]
    checked_names = sorted(set(declarations) | {c['core']['interface']['declaration'] for c in inherited_certs})
    allowed = sorted(set(cfg['allowed_axioms']) | {a for c in inherited_certs for a in c['core']['allowed_axioms']})
    report, kernel_ms = checker(folder, sorted(set(roots) | set(inherited)), checked_names, allowed, state, binary)
    observed = {r['interface']['declaration']: r for r in report['declarations']}
    for name in declarations:
        if not set(observed[name]['axioms']) <= set(cfg['allowed_axioms']):
            raise NotaryError('Selected theorem exceeds its declared logical foundation')
    own, _ = actual_closure(folder, report, binary)
    if own != set(roots) | set(inherited): raise NotaryError('Unlisted/missing transitive module')
    for dependency in dependencies:
        check_realization_coverage(dependency, report, own)
    modules, paths = {}, []
    for module in sorted(own):
        rel = module.replace('.', '/')
        parts = ['objects/' + rel + ext for ext in ('.olean', '.olean.server', '.olean.private')
                 if safe_path(folder, 'objects/' + rel + ext).is_file()]
        modules[module] = parts
        paths.extend(['src/' + rel + '.lean', *parts])
    core = {'schema': 'theorem-notary/bundle/v1', 'profile': PROFILE, 'toolchain': TOOLCHAIN,
            'modules': modules, 'files': inventory(folder, paths),
            'dependencies': sorted((dependency_binding(d) for d in dependencies), key=lambda d: d['bundle_id'])}
    bid = digest(core, 'bundle')
    key = protected_key(key_path, provider=True)
    certs = [sign_declaration({'schema': 'theorem-notary/component/v1', 'kind': 'declaration-export',
              'bundle_id': bid, 'interface': row['interface'], 'allowed_axioms': cfg['allowed_axioms']},
              key, provider) for row in report['declarations'] if row['interface']['declaration'] in declarations]
    bundle = {'bundle_id': bid, 'core': core, 'certificates': certs, 'dependencies': dependencies}
    check_realization_coverage(bundle, report, own)
    write(folder / 'bundle.json', bundle)
    verify_bundle(folder)
    _, base = actual_closure(folder, report, binary)
    acceptance = state / 'acceptance'
    acceptance.mkdir(parents=True, exist_ok=True)
    host_key = protected_key(acceptance / 'host.key')
    body = {'scope': admission_scope(folder, bundle, binary, base), 'checker_report': report}
    write(acceptance / (bid.split(':')[1] + '.receipt.json'), {
        'body': body, 'signature': hmac.new(host_key, canonical(body), hashlib.sha256).hexdigest()})
    return {'bundle_id': bid, 'certificates': len(certs), 'build_ms': build_ms,
            'kernel_ms': kernel_ms, 'kernel_replays': 1}


def build_project(config_path: Path, store: Path, state: Path, provider: str, key_path: Path) -> dict:
    cfg = load(config_path)
    source = (config_path.parent / cfg['source_root']).resolve()
    own = [{'module': row['module'], 'sha256': sha256(safe_path(source, row['module'].replace('.', '/') + '.lean'))}
           for row in cfg['modules']]
    locks = [load((config_path.parent / row['lock']).resolve()) for row in cfg.get('dependencies', [])]
    request_id = digest({'config': cfg, 'sources': own, 'locks': locks,
                         'checker': sha256(VERIFIER), 'runner': sha256(Path(__file__))}, 'publisher-build')
    folder = store / request_id.split(':')[1]
    if (folder / 'bundle.json').exists():
        bundle = verify_bundle(folder)
        for row in own:
            if sha256(safe_path(folder, 'src/' + row['module'].replace('.', '/') + '.lean')) != row['sha256']:
                raise NotaryError('Cached publication source differs from requested build')
        selected = {d for row in cfg['modules'] for d in row['declarations']}
        if selected != {c['core']['interface']['declaration'] for c in bundle['certificates']}:
            raise NotaryError('Cached publication selects different declarations')
        # Refresh dependency verification even when the publisher's own source is unchanged.
        for dependency in cfg.get('dependencies', []):
            dep = (config_path.parent / dependency['bundle']).resolve()
            dep_lock = load((config_path.parent / dependency['lock']).resolve())
            admit(dep, dep_lock, state / 'dependency-admission')
            if dependency_binding(verify_bundle(dep, dep_lock)) not in bundle['core']['dependencies']:
                raise NotaryError('Cached publication binds a different dependency')
        lock = make_lock(folder, [c['core']['interface']['declaration'] for c in bundle['certificates']])
        result = admit(folder, lock, state / 'acceptance')
        result.pop('checker_report', None)
    else:
        result = export(config_path, folder, state, provider, key_path)
        result['status'] = 'built'
    return {**result, 'bundle': str(folder.resolve()), 'publisher_build_id': request_id}
