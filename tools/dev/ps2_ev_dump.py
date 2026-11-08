"""Dump the PS2 project's event strings with their English (own tl/ev or memory) to JSON.

Run with the PS2 project's python (its tools/ go on sys.path, not ours):
    ~/Projects/taiko_risshiden_5_translation/.venv/bin/python tools/dev/ps2_ev_dump.py OUT.json

OUT: {"entries": {entry: [[script, n, op, j, jp (cp932 hex), english source or null], ...]},
      "pronouns": {index: English of the msg00 entry \\%NN inserts},
      "persons": {PS2 person id: [[family, given], ...] (all scenario variants)}}
"""
import json, os, sys

PS2 = os.path.expanduser('~/Projects/taiko_risshiden_5_translation')
sys.path.insert(0, os.path.join(PS2, 'tools'))
import evtl

def main(out):
    mem = evtl.memory()
    res = {}
    for entry in evtl.script_entries():
        own = evtl.parse_tl(evtl.tl_path(entry)) if entry in evtl.tl_entries() else {}
        rows = []
        for k, n, ins, j in evtl.units(entry)[1]:
            kd = evtl.kind(ins, j)
            src = own.get((k, n))
            if src is None and kd != 'name':
                src = mem.get((kd, ins.strs[j]))
            rows.append([k, n, ins.op, j, ins.strs[j].hex(), src])
        res[entry] = rows
    msg00 = json.load(open(os.path.join(PS2, 'script', 'msg', 'msg00.json'), encoding='utf-8'))
    pron = {i: msg00[m]['en'] or msg00[m]['jp'] for i, m in evtl.pronouns().items()}
    res = {'entries': res, 'pronouns': pron, 'persons': evtl.person_names()}
    json.dump(res, open(out, 'w', encoding='utf-8'), ensure_ascii=False)
    print(len(res['entries']), 'entries', len(pron), 'pronouns', len(res['persons']), 'persons')

if __name__ == '__main__':
    main(sys.argv[1])
