"""Adversarial control for theorem-body replacement during Lean import merging."""
from pathlib import Path
import argparse
import json
import os
import subprocess

import notary_protocol as p


def run(expect_merged_acceptance=False):
    folder = p.ROOT / '.notary/reference-v1/overlap-probe'
    objects = folder / 'objects'
    objects.mkdir(parents=True, exist_ok=True)
    binary = p.lean_binary()
    for module, proof in [('Bad', 'by sorry'), ('Good', 'True.intro')]:
        source = folder / (module + '.lean')
        content = 'import Init\ntheorem OverlapProbe.shared : True := ' + proof + '\n'
        target = objects / (module + '.olean')
        unchanged = source.exists() and source.read_text(encoding='utf-8') == content
        source.write_text(content, encoding='utf-8')
        if not (unchanged and target.exists()):
            result = subprocess.run([str(binary), '--trust=0', '--root=' + str(folder),
                '-o', str(target), str(source)], cwd=p.ROOT, env=dict(os.environ, LEAN_PATH=''),
                capture_output=True, text=True, encoding='utf-8')
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
    state = p.ROOT / '.notary/reference-v1'
    try:
        report, _ = p.checker(folder, ['Bad', 'Good'], ['OverlapProbe.shared'], [], state, binary)
        observed = {'merged': 'accepted', 'axioms': report['declarations'][0]['axioms']}
    except p.NotaryError as error:
        observed = {'merged': 'rejected', 'reason': str(error)}
    if expect_merged_acceptance:
        assert observed['merged'] == 'accepted', observed
        assert observed['axioms'] == [], observed
    else:
        assert observed['merged'] == 'rejected', observed
        assert 'Conflicting original declaration' in observed['reason'], observed
    # The original component on its own must fail; the merged result cannot stand in for it.
    try:
        p.checker(folder, ['Bad'], ['OverlapProbe.shared'], [], state, binary)
    except p.NotaryError as error:
        assert 'Disallowed axiom' in str(error), error
        observed['inner_only'] = 'rejected-sorry'
    else:
        raise AssertionError('Unproved inner component was accepted on its own')
    observed['scope'] = 'True remains true; the attack concerns original component proof coverage'
    output = p.ROOT / 'Notary/output' / ('overlap-before.json' if expect_merged_acceptance else 'overlap-after.json')
    p.write(output, observed)
    print(json.dumps(observed, ensure_ascii=False), flush=True)
    print('notary_overlap_probe=passed', flush=True)
    return observed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-merged-acceptance', action='store_true')
    args = parser.parse_args()
    run(args.expect_merged_acceptance)
