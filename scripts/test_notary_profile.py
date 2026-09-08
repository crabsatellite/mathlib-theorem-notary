import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
