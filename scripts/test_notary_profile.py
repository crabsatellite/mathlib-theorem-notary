import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import notary_protocol as p
from theorem_notary import verify_descriptor, load


class WireProfile(unittest.TestCase):
    def test_rejects_noncanonical_numbers_and_surrogates(self):
        for value in [0.5, float('nan'), float('inf'), 9007199254740992, '\ud800']:
            with self.subTest(value=repr(value)), self.assertRaises((ValueError, UnicodeError)):
                p.canonical(value)

    def test_duplicate_keys_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'x.json'
            path.write_text('{"x":1,"x":2}')
            with self.assertRaises(ValueError): load(path)

    def test_no_unicode_normalization(self):
        self.assertNotEqual(p.digest({'name': 'é'}), p.digest({'name': 'e\u0301'}))

    def test_domain_separation(self):
        self.assertNotEqual(p.digest({'x': 1}), p.digest({'x': 1}, 'bundle'))

    def test_new_provider_does_not_change_component(self):
        core = {'schema': 'theorem-notary/component/v1', 'interface': 'a'}
        first = p.sign_declaration(core, Ed25519PrivateKey.generate(), 'A')
        second = p.sign_declaration(core, Ed25519PrivateKey.generate(), 'B')
        self.assertEqual(first['component_id'], second['component_id'])
        first['credits'].extend(second['credits'])
        verify_descriptor(first)

    def test_old_signature_cannot_move_to_new_type(self):
        core = {'schema': 'theorem-notary/component/v1', 'interface': 'a'}
        record = p.sign_declaration(core, Ed25519PrivateKey.generate(), 'A')
        record['core']['interface'] = 'False'
        record['component_id'] = p.digest(record['core'])
        with self.assertRaises(ValueError): verify_descriptor(record)

    def test_independent_javascript_encoding_and_ed25519(self):
        values = [{'z': 2, 'a': ['α', True, None, 9007199254740991]},
                  {'\U00010000': 'non-BMP', '\ue000': 'BMP', 'quote': '"\\\n'},
                  {'nested': {'b': False, 'a': -7}, 'type_expr': 'Lean.Expr.const `Nat []'}]
        key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))  # public test vector, never a real key
        vectors = []
        for value in values:
            core = {'schema': 'theorem-notary/component/v1', 'vector': value}
            vectors.append({'object': core, 'canonical_hex': p.canonical(core).hex(),
                            'id': p.digest(core), 'certificate': p.sign_declaration(core, key, 'TEST VECTOR ONLY')})
        published = load(p.ROOT / 'Notary/wire-vectors.json')['vectors']
        self.assertEqual(vectors, published, 'Published conformance vectors drifted')
        js = r'''
const fs = require('fs'), crypto = require('crypto');
const vectors = JSON.parse(fs.readFileSync(0, 'utf8'));
function canonical(v) {
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  const keys = Object.keys(v).sort((a,b) => Buffer.compare(Buffer.from(a), Buffer.from(b)));
  return '{' + keys.map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}';
}
for (const v of vectors) {
  const bytes = Buffer.from(canonical(v.object));
  if (bytes.toString('hex') !== v.canonical_hex) throw Error('encoding disagreement');
  const id = 'sha256:' + crypto.createHash('sha256').update(Buffer.concat([
    Buffer.from('theorem-notary/component/v1\0'), bytes])).digest('hex');
  if (id !== v.id) throw Error('identity disagreement');
  const c = v.certificate.credits[0], pub = Buffer.from(c.body.public_key, 'base64');
  const key = crypto.createPublicKey({key: Buffer.concat([
    Buffer.from('302a300506032b6570032100','hex'), pub]), format:'der', type:'spki'});
  if (!crypto.verify(null, Buffer.concat([Buffer.from('theorem-notary/provider-credit/v1\0'),
      Buffer.from(canonical(c.body))]), key, Buffer.from(c.signature,'base64'))) throw Error('signature disagreement');
}
process.stdout.write('wire_vectors=passed');
'''
        result = subprocess.run(['node', '-e', js], input=json.dumps(published), text=True,
                                encoding='utf-8', capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'wire_vectors=passed')
        self.vectors = vectors


class AdmissionBoundaries(unittest.TestCase):
    """Content-only fixtures; these bytes are never claimed to be kernel proofs."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'bundle'
        paths = ['src/Example.lean', 'objects/Example.olean',
                 'objects/Example.olean.server', 'objects/Example.olean.private']
        for name in paths:
            dest = self.folder / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b'content-validation fixture, never replayed')
        core = {'schema': 'theorem-notary/bundle/v1', 'profile': p.PROFILE,
                'toolchain': p.TOOLCHAIN, 'modules': {'Example': paths[1:]},
                'files': p.inventory(self.folder, paths), 'dependencies': []}
        bid = p.digest(core, 'bundle')
        self.key = Ed25519PrivateKey.generate()
        cert = p.sign_declaration({'schema': 'theorem-notary/component/v1',
            'kind': 'declaration-export', 'bundle_id': bid,
            'interface': {'declaration': 'Example.claim', 'type_expr': 'True', 'level_params': []},
            'allowed_axioms': []}, self.key, 'Content fixture')
        self.bundle = {'bundle_id': bid, 'core': core, 'certificates': [cert], 'dependencies': []}
        p.write(self.folder / 'bundle.json', self.bundle)
        self.lock = p.make_lock(self.folder, ['Example.claim'])

    def test_falsey_supplied_locks_fail_content_validation(self):
        for locked in [{}, [], False, 0, '']:
            with self.subTest(locked=locked), self.assertRaises(p.NotaryError):
                p.verify_bundle(self.folder, locked)

    def test_all_missing_selections_fail_before_state_or_checker(self):
        for locked in [None, {}, [], False, 0, '']:
            with self.subTest(locked=locked), patch.object(p, 'protected_key') as key, \
                    patch.object(p, 'checker') as checker, self.assertRaises(p.NotaryError):
                p.admit(self.folder, locked, self.root / 'state')
            key.assert_not_called()
            checker.assert_not_called()
        self.assertFalse((self.root / 'state').exists())

    def test_explicit_content_inspection_without_lock_remains_available(self):
        self.assertEqual(p.verify_bundle(self.folder)['bundle_id'], self.bundle['bundle_id'])

    def test_lock_requires_typed_unique_identities(self):
        for value in [[], self.lock['certificates'] * 2, 'not-a-list', [True], ['sha256:abc']]:
            locked = {**self.lock, 'certificates': value}
            with self.subTest(value=value), self.assertRaises(p.NotaryError):
                p.verify_bundle(self.folder, locked)
        for field, value in [('schema', 'unknown'), ('profile', 'unknown'), ('bundle_id', 0)]:
            with self.subTest(field=field), self.assertRaises(p.NotaryError):
                p.verify_bundle(self.folder, {**self.lock, field: value})

    def test_unknown_certificate_and_credit_envelope_fields_fail(self):
        for credit in [False, True]:
            changed = copy.deepcopy(self.bundle)
            cert = changed['certificates'][0]
            (cert['credits'][0] if credit else cert)['unsigned_extra'] = 'uninterpreted'
            with self.subTest(credit=credit), self.assertRaises(p.NotaryError):
                p.verify_bundle(self.folder, document=changed)

    def test_valid_signature_cannot_change_attribution_semantics(self):
        for value in ['verified real-world identity', None, False]:
            changed = copy.deepcopy(self.bundle)
            credit = changed['certificates'][0]['credits'][0]
            credit['body']['identity_scope'] = value
            import base64
            credit['signature'] = base64.b64encode(
                self.key.sign(p.DOMAIN + p.canonical(credit['body']))).decode()
            with self.subTest(value=value), self.assertRaises(p.NotaryError):
                p.verify_bundle(self.folder, document=changed)

    def test_additional_signed_credit_metadata_is_preserved(self):
        import base64
        changed = copy.deepcopy(self.bundle)
        credit = changed['certificates'][0]['credits'][0]
        credit['body']['contact_label'] = 'Provider-declared metadata'
        credit['signature'] = base64.b64encode(
            self.key.sign(p.DOMAIN + p.canonical(credit['body']))).decode()
        self.assertEqual(p.verify_bundle(self.folder, self.lock, document=changed), changed)

    def test_parent_cannot_extend_inherited_module_parts(self):
        outer = copy.deepcopy(self.bundle)
        inner = copy.deepcopy(self.bundle)
        removed = inner['core']['modules']['Example'].pop()
        inner['core']['files'] = [f for f in inner['core']['files'] if f['path'] != removed]
        inner['bundle_id'] = p.digest(inner['core'], 'bundle')
        certcore = inner['certificates'][0]['core']
        certcore['bundle_id'] = inner['bundle_id']
        inner['certificates'] = [p.sign_declaration(certcore, self.key, 'Inner fixture')]
        outer['dependencies'] = [inner]
        outer['core']['dependencies'] = [p.dependency_binding(inner)]
        outer['bundle_id'] = p.digest(outer['core'], 'bundle')
        certcore = outer['certificates'][0]['core']
        certcore['bundle_id'] = outer['bundle_id']
        outer['certificates'] = [p.sign_declaration(certcore, self.key, 'Outer fixture')]
        with self.assertRaisesRegex(p.NotaryError, 'Inherited module proof-data parts changed'):
            p.verify_bundle(self.folder, document=outer)

    def test_duplicate_or_reordered_module_parts_fail(self):
        for parts in [['objects/Example.olean'] * 2 + ['objects/Example.olean.server', 'objects/Example.olean.private'],
                      ['objects/Example.olean', 'objects/Example.olean.private', 'objects/Example.olean.server']]:
            changed = copy.deepcopy(self.bundle)
            changed['core']['modules']['Example'] = parts
            changed['bundle_id'] = p.digest(changed['core'], 'bundle')
            certcore = changed['certificates'][0]['core']
            certcore['bundle_id'] = changed['bundle_id']
            changed['certificates'] = [p.sign_declaration(certcore, self.key, 'Content fixture')]
            with self.subTest(parts=parts), self.assertRaises(p.NotaryError):
                p.verify_bundle(self.folder, document=changed)


class RealizationCoverage(unittest.TestCase):
    def setUp(self):
        interface = {'declaration': 'Inner.claim', 'type_expr': 'True', 'level_params': []}
        self.bundle = {'core': {'modules': {'Inner': []}}, 'dependencies': [],
                       'certificates': [{'core': {'interface': interface, 'allowed_axioms': []}}]}
        self.report = {'modules': [{'module': 'Inner', 'imports': ['Init']},
                                  {'module': 'Outer', 'imports': ['Inner']},
                                  {'module': 'Init', 'imports': []}],
                       'declarations': [{'interface': interface, 'axioms': [],
                           'dependency_module_alternatives': [['Inner'], ['Init']]}]}

    def test_original_dependencies_covered_by_owner_and_foundation(self):
        p.check_realization_coverage(self.bundle, self.report, {'Inner', 'Outer'})

    def test_outer_module_cannot_cover_inner_proof_dependency(self):
        self.report['declarations'][0]['dependency_module_alternatives'].append(['Outer'])
        with self.assertRaisesRegex(p.NotaryError, 'original proof dependency'):
            p.check_realization_coverage(self.bundle, self.report, {'Inner', 'Outer'})

    def test_identical_origin_available_in_owner_is_sufficient(self):
        self.report['declarations'][0]['dependency_module_alternatives'].append(['Outer', 'Inner'])
        p.check_realization_coverage(self.bundle, self.report, {'Inner', 'Outer'})

    def test_unused_import_must_also_be_present_in_owner(self):
        self.report['modules'][0]['imports'].append('Outer')
        with self.assertRaisesRegex(p.NotaryError, 'actual module import'):
            p.check_realization_coverage(self.bundle, self.report, {'Inner', 'Outer'})


if __name__ == '__main__':
    unittest.main()
