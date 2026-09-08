#!/usr/bin/env python3
"""Restore immutable theorem artifacts; hashes establish identity, not truth.

The release manifest digest must come from the locked component descriptor.
Each ZIP and every extracted member is checked before an atomic install.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import time
from urllib.parse import quote
from urllib.request import urlopen
import zipfile


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            h.update(block)
    return h.hexdigest()


def safe_path(root: Path, name: str) -> Path:
    p = PurePosixPath(name)
    if not name or p.is_absolute() or any(x in ('..', '.') for x in name.split('/')):
        raise ValueError(f'Unsafe artifact path: {name}')
    if '\\' in name or ':' in name or '\x00' in name:
        raise ValueError(f'Unsafe artifact path: {name}')
    result = root.joinpath(*p.parts).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f'Artifact escapes store: {name}')
    return result


def fetch_file(url: str, target: Path, digest: str, size: int | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and (size is None or target.stat().st_size == size):
        if sha256(target) == digest:
            return
    partial = target.with_name(target.name + '.partial')
    for attempt in range(3):
        try:
            with urlopen(url, timeout=90) as response, partial.open('wb') as out:
                shutil.copyfileobj(response, out, 4 << 20)
            if size is not None and partial.stat().st_size != size:
                raise ValueError(f'Artifact size mismatch: {target.name}')
            if sha256(partial) != digest:
                raise ValueError(f'Artifact digest mismatch: {target.name}')
            os.replace(partial, target)
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def restore_archive(archive: dict, files: list[dict], base_url: str,
                    download_dir: Path, library_dir: Path) -> tuple[str, int]:
    name = archive['archive']
    target = safe_path(download_dir, name)
    fetch_file(base_url.rstrip('/') + '/' + quote(name), target,
               archive['archive_sha256'], archive['archive_bytes'])
    expected = {f['cache_path']: f for f in files}
    prefix = 'lean4/.lake/build/lib/lean/'
    with zipfile.ZipFile(target) as zf:
        members = [m for m in zf.infolist() if not m.is_dir()]
        if len(members) != len(expected) or {m.filename for m in members} != set(expected):
            raise ValueError(f'Archive member inventory mismatch: {name}')
        for member in members:
            f = expected[member.filename]
            if not member.filename.startswith(prefix) or member.file_size != f['cache_bytes']:
                raise ValueError(f'Invalid theorem artifact member: {member.filename}')
            dest = safe_path(library_dir, member.filename[len(prefix):])
            if dest.is_file() and dest.stat().st_size == f['cache_bytes']:
                if sha256(dest) == f['cache_sha256']:
                    continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            part = dest.with_name(dest.name + '.partial')
            h = hashlib.sha256()
            with zf.open(member) as stream, part.open('wb') as out:
                for block in iter(lambda: stream.read(4 << 20), b''):
                    h.update(block)
                    out.write(block)
            if h.hexdigest() != f['cache_sha256']:
                raise ValueError(f'Proof artifact digest mismatch: {member.filename}')
            os.replace(part, dest)
    return name, len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--download-dir', type=Path, required=True)
    parser.add_argument('--library-dir', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=3, choices=range(1, 5))
    args = parser.parse_args()
    if sha256(args.manifest) != args.manifest_sha256.lower():
        raise ValueError('Release manifest digest mismatch')
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    groups: dict[str, list[dict]] = {}
    seen = set()
    for f in manifest['files']:
        if f['cache_path'] in seen:
            raise ValueError('Duplicate proof artifact path')
        seen.add(f['cache_path'])
        groups.setdefault(f['archive'], []).append(f)
    archives = manifest['archives']
    if len({a['archive'] for a in archives}) != len(archives):
        raise ValueError('Duplicate archive')
    if set(groups) != {a['archive'] for a in archives}:
        raise ValueError('Incomplete archive inventory')
    start = time.monotonic()
    args.library_dir.mkdir(parents=True, exist_ok=True)
    lock = args.library_dir / '.notary-restore.lock'
    with lock.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps({'pid': os.getpid(), 'manifest': args.manifest_sha256}))
    try:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            pending = [pool.submit(restore_archive, a, groups[a['archive']], args.base_url,
                                   args.download_dir, args.library_dir) for a in archives]
            for n, job in enumerate(as_completed(pending), 1):
                name, count = job.result()
                print(json.dumps({'completed': n, 'total': len(archives), 'archive': name,
                                  'modules': count, 'elapsed_s': round(time.monotonic()-start)}), flush=True)
        print(json.dumps({'artifact_identity': 'verified', 'modules': len(seen),
                          'kernel_verification': 'not_performed_by_downloader'}), flush=True)
    finally:
        lock.unlink()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
