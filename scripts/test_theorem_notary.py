"""Protocol regression tests: attribution is not mathematical authority."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import theorem_notary as n
from notary_fetch import safe_path


def credited(core, name='provider A'):
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    cid = n.identity(core)
    body = {'component_id': cid, 'role': 'component-provider', 'display_name': name,
            'public_key': base64.b64encode(pub).decode(),
            'key_fingerprint': hashlib.sha256(pub).hexdigest(), 'mathematical_endorsement': False}
    return {'schema': 'theorem-notary/provider-credit/v1', 'body': body,
            'signature': base64.b64encode(key.sign(n.DOMAIN + n.canonical(body))).decode()}


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.core = {'schema': 'theorem-notary/component/v1', 'endpoint': 'P',
                     'definition_environment': 'E'}

    def test_any_provider_can_credit_same_component(self):
        records = [credited(self.core, name) for name in ('A', 'B')]
        descriptor = {'core': self.core, 'component_id': n.identity(self.core), 'credits': records}
        n.verify_descriptor(descriptor)
        self.assertNotEqual(records[0]['body']['public_key'], records[1]['body']['public_key'])
        self.assertEqual(records[0]['body']['component_id'], records[1]['body']['component_id'])

    def test_core_identity_does_not_depend_on_credit_count(self):
        cid = n.identity(self.core)
        for credits in ([], [credited(self.core)], [credited(self.core), credited(self.core)]):
            n.verify_descriptor({'component_id': cid, 'core': self.core, 'credits': credits})

    def test_statement_cannot_be_changed_under_old_signature(self):
        credit = credited(self.core)
        changed = dict(self.core, endpoint='False')
        with self.assertRaises(n.NotaryError):
            n.verify_descriptor({'core': changed, 'component_id': n.identity(changed), 'credits': [credit]})

    def test_same_formula_different_environment_is_different_component(self):
        changed = dict(self.core, definition_environment='E2')
        self.assertNotEqual(n.identity(changed), n.identity(self.core))

    def test_signature_cannot_be_moved_to_another_provider(self):
        credit = credited(self.core)
        credit['body']['display_name'] = 'another person'
        with self.assertRaises(n.NotaryError):
            n.verify_credit(credit, n.identity(self.core))

    def test_corrupt_signature_rejected(self):
        credit = credited(self.core)
        credit['signature'] = base64.b64encode(bytes(64)).decode()
        with self.assertRaises(n.NotaryError):
            n.verify_credit(credit, n.identity(self.core))

    def test_fingerprint_cannot_disagree_with_public_key(self):
        credit = credited(self.core)
        credit['body']['key_fingerprint'] = '00' * 32
        with self.assertRaises(n.NotaryError):
            n.verify_credit(credit, n.identity(self.core))

    def test_credit_does_not_authorize_archive_import(self):
        with self.assertRaisesRegex(n.NotaryError, 'signatures alone'):
            n.materialize(False)

    def test_valid_signature_on_arbitrary_statement_is_not_accepted_archive(self):
        core = {'schema': 'theorem-notary/component/v1',
                'proof_artifacts': {'manifest_sha256': '00' * 32}}
        d = {'component_id': n.identity(core), 'core': core, 'credits': [credited(core)]}
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'component.json'
            n.write(file, d)
            with patch.object(n, 'REGISTRY', file):
                with self.assertRaises(n.NotaryError):
                    n.materialize(True)

    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / 'object.json'
            file.write_text('{"core":1,"core":2}')
            with self.assertRaises(n.NotaryError):
                n.load(file)

    def test_signed_serialization_is_order_independent(self):
        self.assertEqual(n.canonical({'a': 1, 'b': 2}), n.canonical({'b': 2, 'a': 1}))

    def test_archive_paths_cannot_escape_component_store(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ('../x', '/x', 'C:/x', 'a\\b', 'x/../y', './x'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    safe_path(Path(temp), name)

    def test_modified_locked_archive_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / 'ERDOS848_OLEAN_CACHE_MANIFEST.json').write_text('{}')
            with patch.object(n, 'STORE', folder):
                with self.assertRaisesRegex(n.NotaryError, 'modified'):
                    n.read_archive_manifest()

    def test_resigned_false_assurance_fields_are_rejected(self):
        original = n.load(n.REGISTRY)
        for section, field in [('endpoint', 'source_sha256'),
                               ('source', 'publication_manifest_sha256'),
                               ('source', 'license_url'),
                               ('kernel_basis', 'record_sha256'),
                               ('kernel_basis', 'build_input_signature'),
                               ('kernel_basis', 'recorded_completed_at'),
                               ('proof_artifacts', 'platform')]:
            with self.subTest(field=field):
                core = copy.deepcopy(original['core'])
                core[section][field] = 'fabricated'
                d = {'core': core, 'component_id': n.identity(core), 'credits': [credited(core)]}
                with patch.object(n, 'archive_core', return_value=(original['core'], {}, {})):
                    with self.assertRaisesRegex(n.NotaryError, 'not covered'):
                        n.validate_archive_descriptor(d)

    def test_caller_search_path_cannot_shadow_theorem(self):
        with patch.dict(n.os.environ, {'LEAN_PATH': 'untrusted-library'}):
            self.assertNotIn('untrusted-library', n.lean_env()['LEAN_PATH'])

    def test_failed_build_removes_stale_success_without_running_lean(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Path(temp)
            marker = store / 'external-import-result.json'
            marker.write_text('{"success":true}')
            with patch.object(n, 'STORE', store), patch.object(n, '_check_import') as check:
                with self.assertRaises(n.NotaryError):
                    n.build(False)
                self.assertFalse(marker.exists())
                check.assert_not_called()


if __name__ == '__main__':
    unittest.main()
