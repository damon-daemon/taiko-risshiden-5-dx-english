import sys, io, contextlib
sys.path.insert(0, 'tools')
import tl
hits = []
orig_layout, orig_build = tl.layout, tl.build_entry
cur = {}
def build_entry(jp, units_en, box, tag, log):
    cur['tag'] = tag
    return orig_build(jp, units_en, box, tag, log)
def layout(et, lim):
    lines, e, w = orig_layout(et, lim)
    if lim.page and len(lines) > lim.page:
        last = lines[(len(lines) - 1) // lim.page * lim.page:]
        if len(last) == 1:
            px, nc = tl.measure(last[0])
            if px < 200:
                txt = b''.join(t for k, t in last[0]).decode('cp932', 'replace')
                hits.append((cur['tag'], len(lines), px, txt))
    return lines, e, w
tl.layout, tl.build_entry = layout, build_entry
for n in range(33):
    with contextlib.redirect_stdout(io.StringIO()):
        try: tl.apply(n)
        except SystemExit: pass
for h in hits: print('%s\t%d lines\t%dpx\t%s' % h)
print(len(hits), file=sys.stderr)
