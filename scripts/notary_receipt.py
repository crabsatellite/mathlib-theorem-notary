#!/usr/bin/env python3
"""Run or reuse the exact external-consumer contract through Paper Infrastructure.

The host HMAC receipt is local execution evidence, not a public provider credit.
Verification-only never invokes the configured Lean consumer command.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

import cryptography
from notary_fetch import sha256
from theorem_notary import ROOT, STORE, TOOLCHAIN, canonical, write

POLICY = 'Notary/external-import.policy.json'


def snapshot_runtime(infrastructure: Path) -> None:
    if (ROOT / 'lean-toolchain').read_text().strip() != TOOLCHAIN:
        raise ValueError('Consumer toolchain differs from the locked component')
    binaries = []
    for name in ('lean', 'lake'):
        result = subprocess.run(['elan', 'which', name], cwd=ROOT, check=True,
                                stdout=subprocess.PIPE, text=True, encoding='utf-8')
        binaries.append(Path(result.stdout.strip()).resolve())
    prefix = binaries[0].parent.parent
    files = {Path(sys.executable).resolve(), *binaries}
    # Outside-project inputs are independently hashed before every reuse decision.
    for directory in (prefix / 'bin', prefix / 'lib/lean'):
        files.update(p.resolve() for p in directory.rglob('*') if p.is_file()
                     and (p.suffix in ('.olean', '.dll', '.so', '.dylib', '.exe')
                          or '.so.' in p.name))
    files.update(p.resolve() for p in (infrastructure / 'paper_infrastructure').glob('*.py'))
    crypto_root = Path(cryptography.__file__).parent
    files.update(p.resolve() for p in crypto_root.rglob('*')
                 if p.is_file() and p.suffix in ('.py', '.pyd', '.so'))
    obj = {'schema': 'theorem-notary/host-runtime/v1', 'toolchain': TOOLCHAIN,
           'python': sys.version, 'cryptography': cryptography.__version__,
           'files': [{'path': str(p), 'sha256': sha256(p)} for p in sorted(files)]}
    path = STORE / 'host-runtime.json'
    data = canonical(obj) + b'\n'
    if not path.exists() or path.read_bytes() != data:
        write(path, obj)


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['verify', 'run-or-reuse'])
    parser.add_argument('--policy', default=POLICY)
    parser.add_argument('--infrastructure', type=Path, required=True,
                        help='Paper Infrastructure src directory')
    parser.add_argument('--agent-id', default='local-user')
    parser.add_argument('--agent-runtime', default='interactive-shell')
    parser.add_argument('--thread-id', default='local-user-session')
    args = parser.parse_args()
    try:
        infrastructure = args.infrastructure.resolve()
        if not (infrastructure / 'paper_infrastructure/verification_receipt.py').is_file():
            raise ValueError('Paper Infrastructure receipt implementation is missing')
        sys.path.insert(0, str(infrastructure))
        receipt = importlib.import_module('paper_infrastructure.verification_receipt')
        # Avoid hashing external runtime files for a known absent receipt in read-only mode.
        policy_obj = json.loads((ROOT / args.policy).read_text())
        if args.mode == 'verify' and not (ROOT / policy_obj['receipt_path']).exists():
            receipt.verify_verification_receipt(ROOT, args.policy)
        print('Checking host runtime identity; no theorem command has started.', flush=True)
        snapshot_runtime(infrastructure)
        if args.mode == 'verify':
            result = receipt.verify_verification_receipt(ROOT, args.policy)
        else:
            result = receipt.run_or_reuse_verification(
                ROOT, args.policy, agent_id=args.agent_id, agent_runtime=args.agent_runtime,
                thread_id=args.thread_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        print(f'notary receipt: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
