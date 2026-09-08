#!/usr/bin/env python3
"""Reproducible cold/warm, three-project, default-Lake-build reference experiment."""
from __future__ import annotations

import copy
import json
import os
import secrets
from pathlib import Path
import shutil
import subprocess
import sys
import time
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import notary_protocol as p
from theorem_notary import ROOT, STORE, TOOLCHAIN, NotaryError, load, write


def timed(fn):
    start = time.monotonic()
    value = fn()
    return value, round((time.monotonic() - start) * 1000)


def run(argv, cwd=ROOT):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise NotaryError('Command failed: ' + ' '.join(map(str, argv)) + '\n' + result.stdout + result.stderr)
    return result.stdout


def lake_project(folder: Path, config: Path, store: Path, state: Path):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'lean-toolchain').write_text(TOOLCHAIN + '\n')
    args = [str(ROOT / 'scripts/notary_cli.py'), 'build', '--config', str(config),
            '--store', str(store), '--state', str(state), '--provider', 'Reference consumer provider',
            '--key', str(state / 'provider.pem'), '--result', str(folder / 'build-result.json')]
    quoted = lambda s: json.dumps(str(s).replace('\\', '/'), ensure_ascii=False)
    source = ('import Lake\nopen Lake DSL\npackage notaryConsumer\n\n'
              '@[default_target]\ntarget checkedConsumer pkg : System.FilePath := do\n'
              '  (Job.pure ()).mapM fun _ => do\n'
              '    let result ← IO.Process.output {\n'
              '      cmd := ' + quoted(sys.executable) + '\n'
              '      args := #[' + ', '.join(quoted(a) for a in args) + ']\n'
              '    }\n'
              '    IO.print result.stdout\n'
              '    unless result.exitCode == 0 do error result.stderr\n'
              '    return pkg.dir / "build-result.json"\n')
    (folder / 'lakefile.lean').write_text(source, encoding='utf-8')


def main():
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    output = STORE / 'reference-v1'
    # Fresh transfer/state on every genuine experiment; publisher compilation is cached by inputs.
    active = output / 'active-run.json'
    resumed = active.exists()
    work = output / (load(active)['directory'] if resumed else 'run-' + secrets.token_hex(6))
    if work.resolve().parent != output.resolve(): raise NotaryError('Invalid local experiment checkpoint')
    work.mkdir(parents=True, exist_ok=True)
    write(active, {'directory': work.name})
    results, attacks = {}, []
    results['resumed_after_fixture_failure'] = resumed
    receiver = work / ('receiver-' + secrets.token_hex(6))
    binary = p.lean_binary()
    print('reference_stage=initializer-isolation', flush=True)
    # Initializers run in ordinary trusted compilation, never during data-only admission.
    init_src = work / 'initializer-source'
    init_src.mkdir(exist_ok=True)
    (init_src / 'WithInitializer.lean').write_text(
        'import Init\ninitialize do\n'
        '  if let some path ← IO.getEnv "NOTARY_INIT_MARKER" then\n'
        '    IO.FS.writeFile path "publisher initializer executed"\n'
        'theorem initializer_safe_math : True := True.intro\n', encoding='utf-8')
    write(work / 'initializer.json', {'source_root': str(init_src), 'modules': [
        {'module': 'WithInitializer', 'declarations': ['initializer_safe_math']}], 'allowed_axioms': []})
    init_build = p.build_project(work / 'initializer.json', work / 'initializer-packages', work / 'initializer-publisher',
             'Initializer fixture', work / 'initializer-publisher/key.pem')
    init_bundle = Path(init_build['bundle'])
    marker = work / 'initializer-marker.txt'
    importer = work / 'InitializerImport.lean'
    importer.write_text('import WithInitializer\n#check initializer_safe_math\n')
    result = subprocess.run([str(binary), str(importer)], cwd=ROOT,
        env=dict(os.environ, LEAN_PATH=str(init_bundle / 'objects'), NOTARY_INIT_MARKER=str(marker)), capture_output=True)
    if result.returncode or not marker.exists(): raise AssertionError('Initializer positive control failed')
    marker.unlink()
    with patch.dict(os.environ, {'NOTARY_INIT_MARKER': str(marker)}):
        p.admit(init_bundle, p.make_lock(init_bundle, ['initializer_safe_math']), work / ('initializer-receiver-' + secrets.token_hex(6)))
    if marker.exists(): raise AssertionError('Publisher initializer executed during admission')
    attacks.append('publisher-initializer-not-executed-positive-control-confirmed')
    print('reference_stage=composition', flush=True)
    composition = run([str(binary), '--trust=0', str(ROOT / 'Notary/Composition.lean')])
    if composition.count('does not depend on any axioms') != 3:
        raise NotaryError('Composition model has an unexpected axiom surface: ' + composition)
    (work / 'composition.log').write_text(composition, encoding='utf-8')
    print('reference_stage=publisher', flush=True)
    provider, results['publisher_wall_ms'] = timed(lambda: p.build_project(
        ROOT / 'Notary/Examples/provider.json', output / 'packages', output / 'publisher',
        'Reference tree component provider', output / 'publisher/provider.pem'))
    provider_path = Path(provider['bundle'])
    results['publisher'] = {k: v for k, v in provider.items() if k != 'checker_report'}
    declarations = ['NotaryExample.Tree.mirror_twice', 'NotaryExample.Tree.leaves_mirror']
    lock = p.make_lock(provider_path, declarations)
    write(work / 'provider.lock.json', lock)
    cold = work / 'cold-transfer'
    if not cold.exists(): shutil.copytree(provider_path, cold)
    print('reference_stage=independent-consumer-state', flush=True)
    cold_result, results['cold_consumer_wall_ms'] = timed(lambda: p.admit(cold, lock, receiver))
    warm, results['warm_consumer_wall_ms'] = timed(lambda: p.admit(cold, lock, receiver))
    if cold_result['kernel_replays'] != 1: raise NotaryError('Cold receiver was not fresh')
    if warm['status'] != 'reused' or warm['kernel_replays'] != 0:
        raise NotaryError('Unchanged consumer did not reuse its verified proof')
    results['cold_kernel_replays'] = cold_result['kernel_replays']
    results['warm_kernel_replays'] = warm['kernel_replays']
    results['separate_local_keys'] = (p.sha256(output / 'publisher/acceptance/host.key') !=
                                      p.sha256(receiver / 'host.key'))
    if not results['separate_local_keys']: raise NotaryError('Cold consumer reused the publisher trust root')
    # Credit changes are checked but cannot invalidate unchanged mathematical admission.
    publication = load(cold / 'bundle.json')
    original = copy.deepcopy(publication)
    new_key = Ed25519PrivateKey.generate()
    for cert in publication['certificates']:
        cert['credits'].extend(p.sign_declaration(cert['core'], new_key, 'Second test provider')['credits'])
    write(cold / 'bundle.json', publication)
    changed_credit = p.admit(cold, lock, receiver)
    if changed_credit['kernel_replays'] != 0: raise NotaryError('Credit change forced a mathematical replay')
    write(cold / 'bundle.json', original)
    results['credit_change_kernel_replays'] = 0
    print('reference_stage=ordinary-lake-consumer', flush=True)
    consumer_config = work / 'consumer.json'
    write(consumer_config, {'source_root': str(ROOT / 'Notary/Examples/Consumer'),
          'modules': [{'module': 'NotaryConsumer.RoundTrip', 'declarations': [
              'NotaryConsumer.roundTrip_correct', 'NotaryConsumer.roundTrip_leaves']}],
          'allowed_axioms': [], 'dependencies': [{'bundle': str(cold), 'lock': str(work / 'provider.lock.json')}]})
    lake_dir = work / 'lake-consumer'
    lake_project(lake_dir, consumer_config, work / 'consumer-packages', work / 'consumer-state')
    lake_output, results['lake_consumer_wall_ms'] = timed(lambda: run(['lake', 'build'], lake_dir))
    (work / 'lake-build.log').write_text(lake_output, encoding='utf-8')
    consumer = load(lake_dir / 'build-result.json')
    results['lake_consumer_status'] = consumer['status']
    _, results['lake_consumer_warm_wall_ms'] = timed(lambda: run(['lake', 'build'], lake_dir))
    consumer_path = Path(consumer['bundle'])
    consumer_lock = p.make_lock(consumer_path, ['NotaryConsumer.roundTrip_correct', 'NotaryConsumer.roundTrip_leaves'])
    write(work / 'consumer.lock.json', consumer_lock)
    application_config = work / 'application.json'
    write(application_config, {'source_root': str(ROOT / 'Notary/Examples/Applications'),
          'modules': [{'module': 'NotaryApplication.Payload', 'declarations': [
              'NotaryApplication.mirroredPayload_correct', 'NotaryApplication.frameSize_correct']}],
          'allowed_axioms': [], 'dependencies': [{'bundle': str(consumer_path), 'lock': str(work / 'consumer.lock.json')}]})
    print('reference_stage=third-project', flush=True)
    application, results['application_wall_ms'] = timed(lambda: p.build_project(
        application_config, work / 'application-packages', work / 'application-state',
        'Reference application provider', work / 'application-state/provider.pem'))
    application_path = Path(application['bundle'])
    results['application_status'] = application['status']
    app_lock = p.make_lock(application_path, ['NotaryApplication.mirroredPayload_correct', 'NotaryApplication.frameSize_correct'])
    app = p.admit(application_path, app_lock, work / 'application-state/acceptance')
    referenced = {n for row in app['checker_report']['declarations'] for n in row['referenced_theorems']}
    if not {'NotaryConsumer.roundTrip_correct', 'NotaryConsumer.roundTrip_leaves'} <= referenced:
        raise NotaryError('Application did not actually use both certified consumer conclusions')
    results['actual_cross_project_theorem_use'] = True
    results['signed_theorems'] = sum(len(p.verify_bundle(path)['certificates'])
                                   for path in (provider_path, consumer_path, application_path))
    print('reference_stage=baselines-and-update', flush=True)
    # Same process boundary and artifacts as the notary consumer, but no protocol admission.
    plain = work / ('plain-baseline-' + secrets.token_hex(6))
    plain.mkdir(exist_ok=True)
    (plain / 'lean-toolchain').write_text(TOOLCHAIN + '\n')
    shutil.copytree(ROOT / 'Notary/Examples/Provider/NotaryExample', plain / 'NotaryExample', dirs_exist_ok=True)
    (plain / 'lakefile.lean').write_text('import Lake\nopen Lake DSL\npackage plain\n@[default_target]\nlean_lib NotaryExample\n')
    (plain / 'NotaryExample.lean').write_text('import NotaryExample.Trees\n')
    _, results['plain_lake_cold_wall_ms'] = timed(lambda: run(['lake', 'build'], plain))
    results['plain_initial_state'] = 'fresh project; OS cache not reset'
    _, results['plain_lake_warm_wall_ms'] = timed(lambda: run(['lake', 'build'], plain))
    _, results['hash_and_credit_only_wall_ms'] = timed(lambda: p.verify_bundle(cold, lock))
    update_src = work / 'updated-source'
    shutil.copytree(ROOT / 'Notary/Examples/Provider', update_src, dirs_exist_ok=True)
    with (update_src / 'NotaryExample/Trees.lean').open('a', encoding='utf-8') as stream:
        stream.write('\n-- Deliberate source revision with unchanged mathematical statements.\n')
    update_cfg = load(ROOT / 'Notary/Examples/provider.json')
    update_cfg['source_root'] = str(update_src)
    write(work / 'updated.json', update_cfg)
    updated, results['dependency_update_build_wall_ms'] = timed(lambda: p.build_project(
        work / 'updated.json', work / 'updated-packages', work / 'updated-state',
        'Updated provider', work / 'updated-state/provider.pem'))
    updated_path = Path(updated['bundle'])
    if updated['bundle_id'] == provider['bundle_id']: raise AssertionError('Source revision lost its identity')
    results['dependency_update_build_status'] = updated['status']
    try: p.admit(updated_path, lock, receiver)
    except NotaryError: attacks.append('dependency-update-requires-explicit-new-lock')
    else: raise AssertionError('Old lock accepted new source')
    new_update_lock = p.make_lock(updated_path, declarations)
    update_admit, results['dependency_update_admission_wall_ms'] = timed(lambda: p.admit(updated_path, new_update_lock, receiver))
    if update_admit['kernel_replays'] != 1: raise NotaryError('New dependency did not get fresh admission')
    results['dependency_update_kernel_replays'] = update_admit['kernel_replays']
    print('reference_stage=hostile-tests', flush=True)
    proof = cold / 'objects/NotaryExample/Trees.olean'
    original_bytes = proof.read_bytes()
    try:
        proof.write_bytes(original_bytes[:-1] + bytes([original_bytes[-1] ^ 1]))
        with patch.object(p, 'checker', side_effect=AssertionError('Tamper must fail before replay')):
            try: p.admit(cold, lock, receiver)
            except NotaryError: attacks.append('inner-proof-byte-change-rejected-before-replay')
            else: raise AssertionError('Tampered proof accepted')
        result = subprocess.run(['lake', 'build'], cwd=lake_dir, capture_output=True)
        if result.returncode == 0: raise AssertionError('Ordinary Lake build bypassed dependency admission')
        if load(lake_dir / 'build-result.json')['status'] != 'failed':
            raise AssertionError('Failed build left a stale successful result')
        attacks.append('ordinary-lake-build-rejects-modified-dependency')
    finally: proof.write_bytes(original_bytes)
    extra = cold / 'objects/Undeclared.olean'
    try:
        extra.write_bytes(original_bytes)
        try: p.admit(cold, lock, receiver)
        except NotaryError: attacks.append('undeclared-module-rejected')
        else: raise AssertionError('Unlisted module accepted')
    finally: extra.unlink(missing_ok=True)
    # A valid fresh signature and a deliberately updated lock still cannot lie about the type.
    forged = copy.deepcopy(original)
    core = forged['certificates'][0]['core']
    core['interface']['type_expr'] = 'Lean.Expr.const `False []'
    forged['certificates'][0] = p.sign_declaration(core, new_key, 'Hostile test provider')
    try:
        write(cold / 'bundle.json', forged)
        try: p.admit(cold, lock, receiver)
        except NotaryError: attacks.append('old-consumer-lock-rejects-resigned-conclusion')
        else: raise AssertionError('Old certificate lock accepted changed conclusion')
        new_lock = p.make_lock(cold, declarations)
        try: p.admit(cold, new_lock, work / 'hostile-new-lock')
        except NotaryError as error:
            if 'Actual declaration' not in str(error): raise
            attacks.append('new-lock-and-valid-signature-cannot-fake-kernel-type')
        else: raise AssertionError('Signed false type accepted')
    finally: write(cold / 'bundle.json', original)
    # Re-sign the entire outer package: an inner false interface must still fail kernel admission.
    consumer_original = load(consumer_path / 'bundle.json')
    nested = copy.deepcopy(consumer_original)
    nested['dependencies'][0] = forged
    nested['core']['dependencies'] = [p.dependency_binding(forged)]
    nested['bundle_id'] = p.digest(nested['core'], 'bundle')
    for i, cert in enumerate(nested['certificates']):
        cert['core']['bundle_id'] = nested['bundle_id']
        nested['certificates'][i] = p.sign_declaration(cert['core'], new_key, 'Hostile outer provider')
    try:
        write(consumer_path / 'bundle.json', nested)
        nested_lock = p.make_lock(consumer_path, ['NotaryConsumer.roundTrip_correct'])
        try: p.admit(consumer_path, nested_lock, work / 'hostile-nested')
        except NotaryError as error:
            if 'Actual declaration' not in str(error): raise
            attacks.append('resigned-outer-and-inner-false-interface-rejected')
        else: raise AssertionError('Nested false certificate was laundered')
    finally: write(consumer_path / 'bundle.json', consumer_original)
    for module in ('Lean/Replay', 'Init'):
        shadow = cold / ('objects/' + module + '.olean')
        shadow.parent.mkdir(parents=True, exist_ok=True)
        try:
            shadow.write_bytes(original_bytes)
            with patch.object(p.subprocess, 'run', side_effect=AssertionError('Shadow must fail before launching checker')):
                try: p.checker(cold, ['NotaryExample.Trees'], declarations, [], work / 'shadow-state', binary)
                except NotaryError as error:
                    if 'shadows the trusted toolchain' not in str(error): raise
                    attacks.append('trusted-module-shadow-rejected:' + module)
                else: raise AssertionError('Trusted module was shadowed')
        finally: shadow.unlink(missing_ok=True)
    receipt_file = Path(warm['receipt'])
    raw_receipt = receipt_file.read_bytes()
    try:
        forged_receipt = load(receipt_file)
        forged_receipt['body']['checker_report']['kernel_replayed'] = False
        write(receipt_file, forged_receipt)
        try: p.admit(cold, lock, receiver)
        except NotaryError: attacks.append('forged-host-receipt-rejected')
        else: raise AssertionError('Forged host receipt accepted')
    finally: receipt_file.write_bytes(raw_receipt)
    # Independent checker never accepts a publisher's success text or sorry-based proof.
    hostile_src = work / 'hostile-source'
    hostile_src.mkdir(exist_ok=True)
    (hostile_src / 'Forged.lean').write_text(
        'import Init\n#eval IO.println "notary_kernel_verified=true"\n'
        'theorem forged : False := by sorry\n', encoding='utf-8')
    hostile_cfg = work / 'hostile.json'
    write(hostile_cfg, {'source_root': str(hostile_src), 'modules': [
          {'module': 'Forged', 'declarations': ['forged']}], 'allowed_axioms': []})
    try:
        rejected = work / 'rejected-publication'
        if (rejected / 'objects/Forged.olean').exists():
            if p.sha256(rejected / 'src/Forged.lean') != p.sha256(hostile_src / 'Forged.lean'):
                raise AssertionError('Rejected fixture source changed')
            p.checker(rejected, ['Forged'], ['forged'], [], work / 'hostile-publisher', binary)
        else:
            p.export(hostile_cfg, rejected, work / 'hostile-publisher',
                     'Hostile provider', work / 'hostile-publisher/key.pem')
    except NotaryError as error:
        if 'Disallowed axiom' not in str(error): raise
        attacks.append('spoofed-success-and-sorry-rejected-by-independent-checker')
    else: raise AssertionError('Sorry proof got a provider certificate')
    if (work / 'rejected-publication/bundle.json').exists(): raise AssertionError('Rejected publication persisted')
    results['attacks_rejected'] = attacks
    results['profile'] = p.PROFILE
    results['independent_physical_host'] = False
    results['cold_start_scope'] = 'separate process, transferred public bundle, fresh host key and acceptance state'
    results['source_correspondence'] = 'publisher compilation recorded; consumer checked proof data, not source rebuild equality'
    results['status'] = 'passed'
    write(work / 'result.json', results)
    results['evidence_directory'] = str(work)
    write(output / 'result.json', results)
    active.unlink()
    print(json.dumps(results, indent=2))
    print('notary_reference_v1=passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
