"""Re-sign an inner dependency omission while retaining the outer proof union."""
import argparse
import copy
from pathlib import Path
import secrets

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import notary_protocol as p


def run(folder: Path):
    original_bytes = (folder / 'bundle.json').read_bytes()
    publication = copy.deepcopy(p.verify_bundle(folder))
    inner = publication['dependencies'][0]
    omitted = set(inner['dependencies'][0]['core']['modules'])
    inner['dependencies'] = []
    inner['core']['dependencies'] = []
    removed_paths = set()
    for module in omitted:
        removed_paths.update(inner['core']['modules'].pop(module))
        removed_paths.add('src/' + module.replace('.', '/') + '.lean')
    inner['core']['files'] = [f for f in inner['core']['files'] if f['path'] not in removed_paths]
    key = Ed25519PrivateKey.generate()  # ephemeral adversarial identity; never stored

    def resign(bundle):
        bundle['bundle_id'] = p.digest(bundle['core'], 'bundle')
        for i, cert in enumerate(bundle['certificates']):
            cert['core']['bundle_id'] = bundle['bundle_id']
            bundle['certificates'][i] = p.sign_declaration(cert['core'], key, 'Dependency omission fixture')

    resign(inner)
    publication['core']['dependencies'] = [p.dependency_binding(inner)]
    resign(publication)
    result = {'omitted_inner_modules': sorted(omitted),
              'parent_modules': sorted(publication['core']['modules']),
              'scope': 'real three-project proof bytes; fresh receiver admission of re-signed publication'}
    try:
        p.write(folder / 'bundle.json', publication)
        lock = p.make_lock(folder, [c['core']['interface']['declaration'] for c in publication['certificates']])
        result['content_validation'] = 'accepted'
        state = p.ROOT / '.notary/reference-v1' / ('dependency-probe-' + secrets.token_hex(6))
        try:
            p.admit(folder, lock, state)
        except p.NotaryError as error:
            if 'Realization omits' not in str(error):
                raise
            result['admission'] = 'rejected'
            result['reason'] = str(error)
        else:
            raise AssertionError('Outer proof union concealed an inner dependency omission')
    finally:
        (folder / 'bundle.json').write_bytes(original_bytes)
    p.write(p.ROOT / 'Notary/output/missing-dependency-after.json', result)
    print('notary_dependency_probe=passed', flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    run(parser.parse_args().bundle.resolve())
