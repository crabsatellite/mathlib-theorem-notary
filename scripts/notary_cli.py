#!/usr/bin/env python3
"""Declaration export, consumer locking, and fresh/run-or-reuse admission."""
import argparse
import json
from pathlib import Path
import sys

from notary_protocol import admit, build_project, export, load, make_lock, verify_bundle, write


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    e = sub.add_parser('export')
    e.add_argument('--config', type=Path, required=True)
    e.add_argument('--out', type=Path, required=True)
    e.add_argument('--state', type=Path, required=True)
    e.add_argument('--provider', required=True)
    e.add_argument('--key', type=Path, required=True)
    b = sub.add_parser('build')
    b.add_argument('--config', type=Path, required=True)
    b.add_argument('--store', type=Path, required=True)
    b.add_argument('--state', type=Path, required=True)
    b.add_argument('--provider', required=True)
    b.add_argument('--key', type=Path, required=True)
    b.add_argument('--result', type=Path)
    a = sub.add_parser('admit')
    a.add_argument('--bundle', type=Path, required=True)
    a.add_argument('--lock', type=Path, required=True)
    a.add_argument('--state', type=Path, required=True)
    l = sub.add_parser('lock')
    l.add_argument('--bundle', type=Path, required=True)
    l.add_argument('--declaration', action='append', required=True)
    l.add_argument('--out', type=Path, required=True)
    i = sub.add_parser('inspect')
    i.add_argument('--bundle', type=Path, required=True)
    args = p.parse_args()
    try:
        if args.command == 'export':
            result = export(args.config, args.out, args.state, args.provider, args.key)
        elif args.command == 'build':
            result = build_project(args.config, args.store, args.state, args.provider, args.key)
            if args.result: write(args.result, result)
        elif args.command == 'admit':
            r = admit(args.bundle, load(args.lock), args.state)
            result = {k: v for k, v in r.items() if k != 'checker_report'}
        elif args.command == 'lock':
            result = make_lock(args.bundle, args.declaration)
            write(args.out, result)
        else:
            b = verify_bundle(args.bundle)
            result = {'bundle_id': b['bundle_id'], 'certificates': b['certificates'],
                      'assurance': 'content-and-credit-only; run admit for kernel acceptance'}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        if args.command == 'build' and args.result:
            write(args.result, {'status': 'failed', 'error': str(error)})
        print(f'notary rejected: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
