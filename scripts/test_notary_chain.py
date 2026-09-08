"""Hostile byte/graph tests with real cryptographic signatures, no Lean replay."""
import copy
from pathlib import Path
import tempfile
import unittest

from notary_chain import verify_graph
from notary_fetch import sha256
from theorem_notary import NotaryError, identity
from test_theorem_notary import credited

FOUNDATION = {'toolchain': 'fixed-test-foundation', 'allowed_axioms': []}


def node(folder, module, deps=(), foundation=None):
    for ext in ('.lean', '.olean'):
        (folder / (module + ext)).write_bytes((module + ext).encode())
    core = {'schema': 'theorem-notary/component/v1', 'kind': 'checked-module-reference',
            'module': module, 'endpoint': module + '.result', 'statement': '∀ n : Nat, n = n',
            'foundation': foundation or FOUNDATION, 'dependencies': list(deps),
            'files': {role: {'path': module + ext, 'sha256': sha256(folder / (module + ext))}
                      for role, ext in [('source', '.lean'), ('olean', '.olean')]}}
    return resign(core)


def resign(core):
    return {'component_id': identity(core), 'core': core, 'credits': [credited(core)]}


class ChainAttacks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Path(self.tmp.name)
        self.graph = {}
        dep = []
        self.ids = []
        for i in range(8):
            d = node(self.store, f'Layer{i}', dep)
            cid = d['component_id']
            self.graph[cid] = d
            self.ids.append(cid)
            dep = [cid]
        self.root = self.ids[-1]

    def verify(self, graph=None):
        return verify_graph(self.root, graph or self.graph, self.store, FOUNDATION)

    def test_eight_layers_pass_identity_but_do_not_claim_kernel_verification(self):
        r = self.verify()
        self.assertEqual((r['nodes'], r['depth']), (8, 8))
        self.assertEqual(r['mathematical_admission'], 'requires-host-kernel-receipt')

    def test_tamper_every_layer_source_and_proof(self):
        for i in range(8):
            for ext in ('.lean', '.olean'):
                path = self.store / (f'Layer{i}' + ext)
                original = path.read_bytes()
                with self.subTest(layer=i, ext=ext):
                    path.write_bytes(original + b'altered')
                    with self.assertRaises(NotaryError):
                        self.verify()
                    path.write_bytes(original)

    def test_missing_middle_component_rejected(self):
        del self.graph[self.ids[3]]
        with self.assertRaises(NotaryError): self.verify()

    def test_valid_resignature_cannot_replace_consumer_root(self):
        # Attacker consistently rehashes and re-signs the WHOLE altered chain.
        new_graph = {}
        dep = []
        for cid in self.ids:
            core = copy.deepcopy(self.graph[cid]['core'])
            core['statement'] = 'False'
            core['dependencies'] = dep
            d = resign(core)
            new_graph[d['component_id']] = d
            dep = [d['component_id']]
        with self.assertRaisesRegex(NotaryError, 'locked root'):
            self.verify(new_graph)

    def test_swapped_same_name_interface_under_old_identity_rejected(self):
        self.graph[self.ids[2]]['core']['statement'] = 'False'
        with self.assertRaises(NotaryError): self.verify()

    def test_self_declared_kernel_status_rejected_even_when_signed(self):
        core = copy.deepcopy(self.graph[self.root]['core'])
        core['kernel_verified'] = True
        d = resign(core)
        self.graph[d['component_id']] = d
        with self.assertRaisesRegex(NotaryError, 'self-declared assurance'):
            verify_graph(d['component_id'], self.graph, self.store, FOUNDATION)

    def test_lookup_alias_cannot_substitute_another_component(self):
        self.graph[self.ids[3]] = self.graph[self.ids[1]]
        with self.assertRaises(NotaryError): self.verify()

    def test_wrong_foundation_is_rejected_with_valid_signature(self):
        d = node(self.store, 'WrongFoundation', foundation={'allowed_axioms': ['False']})
        self.graph[d['component_id']] = d
        with self.assertRaisesRegex(NotaryError, 'foundation'):
            verify_graph(d['component_id'], self.graph, self.store, FOUNDATION)

    def test_provider_impersonation_rejected_at_inner_layer(self):
        self.graph[self.ids[1]]['credits'][0]['body']['display_name'] = 'Alex Chengyu Li'
        with self.assertRaises(NotaryError): self.verify()

    def test_diamond_reuses_same_exact_dependency(self):
        left = node(self.store, 'Left', [self.root])
        right = node(self.store, 'Right', [self.root])
        top = node(self.store, 'Diamond', [left['component_id'], right['component_id']])
        for d in (left, right, top): self.graph[d['component_id']] = d
        r = verify_graph(top['component_id'], self.graph, self.store, FOUNDATION)
        self.assertEqual((r['nodes'], r['depth']), (11, 10))

    def test_conflicting_same_module_versions_rejected(self):
        different = copy.deepcopy(self.graph[self.ids[0]]['core'])
        different['files']['olean']['sha256'] = '00' * 32
        conflict = resign(different)
        top = node(self.store, 'Conflict', [self.root, conflict['component_id']])
        for d in (conflict, top): self.graph[d['component_id']] = d
        with self.assertRaisesRegex(NotaryError, 'same Lean module'):
            verify_graph(top['component_id'], self.graph, self.store, FOUNDATION)

    def test_two_conclusions_share_one_module_without_identity_collision(self):
        second = copy.deepcopy(self.graph[self.ids[0]]['core'])
        second['endpoint'] = 'Layer0.otherConclusion'
        second['statement'] = '∀ n : Nat, n + 1 = n + 1'
        cert = resign(second)
        top = node(self.store, 'TwoConclusions', [self.ids[0], cert['component_id']])
        for d in (cert, top): self.graph[d['component_id']] = d
        r = verify_graph(top['component_id'], self.graph, self.store, FOUNDATION)
        self.assertEqual(r['nodes'], 3)
        self.assertNotEqual(cert['component_id'], self.ids[0])

    def test_credit_cannot_be_transplanted_to_other_conclusion_in_same_module(self):
        original = self.graph[self.ids[0]]
        core = copy.deepcopy(original['core'])
        core['endpoint'] = 'Layer0.otherConclusion'
        changed = {'core': core, 'component_id': identity(core), 'credits': original['credits']}
        self.graph[changed['component_id']] = changed
        with self.assertRaises(NotaryError):
            verify_graph(changed['component_id'], self.graph, self.store, FOUNDATION)


if __name__ == '__main__':
    unittest.main()
