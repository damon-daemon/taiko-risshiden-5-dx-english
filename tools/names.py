"""Person names: Japanese from the scenario files, English from tl/names_persons.json.

Runtime names live in data/CMENU/SNR/SNR0-8_JP.TR5 (ILNK, subfile 16): 1304 x 24 bytes =
family[9] | given[9] | u16 flag | u16 id | u16 id2 (same layout as the PS2 ILNK). Subfile 15
= 1244 x 44 bytes of half-width kana readings (family[10] | given[10] | data).
A person object (stride 64) holds +8 = name record, +0x10 = reading record.

tl/names_persons.json is keyed by person id with optional per-scenario overrides
(sN = SNR file N, 0-8):

  {"id": 517, "en": ["Hashiba", "Hideyoshi"], "s0": ["Kinoshita", "Tokichiro"], ...}

The records keep their Japanese (names typed by the player still work); the exe's name
readers look the record's (family, given) pair up by hash and show the English (see
apply()).

  names.py export   -> script/names_persons.json (jp + reading per scenario, en)
  names.py check    -> pairs with no English / conflicting English
"""
import json, os, re, struct, sys, unicodedata

sys.path.insert(0, os.path.dirname(__file__))
import setup

TL = os.path.join(setup.TL, 'names_persons.json')
SCRIPT = os.path.join(setup.ROOT, 'script', 'names_persons.json')
SNR = 'data/CMENU/SNR/SNR%d_JP.TR5'
SCENARIOS = range(9)
SUB, REC = 16, 24
READ_SUB, READ_REC = 15, 44

def field(b):
    return b.split(b'\0')[0].decode('cp932', 'replace')

def ilnk_sub(entry, k):
    n = struct.unpack_from('<I', entry, 4)[0]
    offs = [struct.unpack_from('<I', entry, 8 + 4 * i)[0] for i in range(n)] + [len(entry)]
    return offs[k], offs[k + 1]

def snr(n, game=None):
    return open(os.path.join(game or setup.CLEAN, SNR % n), 'rb').read()

def scenario_names(entry):
    """[(family, given)] x 1304 of one scenario file."""
    a, b = ilnk_sub(entry, SUB)
    sub = entry[a:b]
    return [(field(sub[i * REC:i * REC + 9]), field(sub[i * REC + 9:i * REC + 18]))
            for i in range(len(sub) // REC)]

def scenario_readings(entry):
    a, b = ilnk_sub(entry, READ_SUB)
    sub = entry[a:b]
    return [(field(sub[i * READ_REC:i * READ_REC + 10]), field(sub[i * READ_REC + 10:i * READ_REC + 20]))
            for i in range(len(sub) // READ_REC)]

def all_names(game=None):
    """{scenario: [(family, given)]}, {scenario: [(family reading, given reading)]}"""
    names, reads = {}, {}
    for n in SCENARIOS:
        e = snr(n, game)
        names[n], reads[n] = scenario_names(e), scenario_readings(e)
    return names, reads

# ---------------------------------------------------------------- romanization

KANA = {
    'きゃ': 'kya', 'きゅ': 'kyu', 'きょ': 'kyo', 'しゃ': 'sha', 'しゅ': 'shu', 'しょ': 'sho',
    'ちゃ': 'cha', 'ちゅ': 'chu', 'ちょ': 'cho', 'にゃ': 'nya', 'にゅ': 'nyu', 'にょ': 'nyo',
    'ひゃ': 'hya', 'ひゅ': 'hyu', 'ひょ': 'hyo', 'みゃ': 'mya', 'みゅ': 'myu', 'みょ': 'myo',
    'りゃ': 'rya', 'りゅ': 'ryu', 'りょ': 'ryo', 'ぎゃ': 'gya', 'ぎゅ': 'gyu', 'ぎょ': 'gyo',
    'じゃ': 'ja', 'じゅ': 'ju', 'じょ': 'jo', 'ぢゃ': 'ja', 'ぢゅ': 'ju', 'ぢょ': 'jo',
    'びゃ': 'bya', 'びゅ': 'byu', 'びょ': 'byo', 'ぴゃ': 'pya', 'ぴゅ': 'pyu', 'ぴょ': 'pyo',
    'あ': 'a', 'い': 'i', 'う': 'u', 'え': 'e', 'お': 'o',
    'か': 'ka', 'き': 'ki', 'く': 'ku', 'け': 'ke', 'こ': 'ko',
    'さ': 'sa', 'し': 'shi', 'す': 'su', 'せ': 'se', 'そ': 'so',
    'た': 'ta', 'ち': 'chi', 'つ': 'tsu', 'て': 'te', 'と': 'to',
    'な': 'na', 'に': 'ni', 'ぬ': 'nu', 'ね': 'ne', 'の': 'no',
    'は': 'ha', 'ひ': 'hi', 'ふ': 'fu', 'へ': 'he', 'ほ': 'ho',
    'ま': 'ma', 'み': 'mi', 'む': 'mu', 'め': 'me', 'も': 'mo',
    'や': 'ya', 'ゆ': 'yu', 'よ': 'yo', 'ら': 'ra', 'り': 'ri', 'る': 'ru', 'れ': 're', 'ろ': 'ro',
    'わ': 'wa', 'ゐ': 'i', 'ゑ': 'e', 'を': 'o', 'ん': 'n',
    'が': 'ga', 'ぎ': 'gi', 'ぐ': 'gu', 'げ': 'ge', 'ご': 'go',
    'ざ': 'za', 'じ': 'ji', 'ず': 'zu', 'ぜ': 'ze', 'ぞ': 'zo',
    'だ': 'da', 'ぢ': 'ji', 'づ': 'zu', 'で': 'de', 'ど': 'do',
    'ば': 'ba', 'び': 'bi', 'ぶ': 'bu', 'べ': 'be', 'ぼ': 'bo',
    'ぱ': 'pa', 'ぴ': 'pi', 'ぷ': 'pu', 'ぺ': 'pe', 'ぽ': 'po',
    'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o', 'ー': '',
}

def hiragana(s):
    """Half-width / full-width katakana -> hiragana."""
    s = unicodedata.normalize('NFKC', s)
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)

def romaji(kana):
    """Hepburn, long vowels written short (ou/oo -> o, uu -> u), as in the PS2 English."""
    kana = hiragana(kana)
    out, i = '', 0
    while i < len(kana):
        if kana[i] == 'っ' and i + 1 < len(kana):
            nxt = KANA.get(kana[i + 1:i + 3]) or KANA.get(kana[i + 1], '')
            out += 't' if nxt.startswith('ch') else nxt[:1]
            i += 1
            continue
        two = KANA.get(kana[i:i + 2])
        if two:
            out += two
            i += 2
            continue
        out += KANA.get(kana[i], kana[i])
        i += 1
    out = re.sub('ou(?![aiueo])|oo', 'o', out)
    out = re.sub('uu', 'u', out)
    return out.capitalize()

# ---------------------------------------------------------------- tl/

def load_tl():
    return {r['id']: r for r in json.load(open(TL, encoding='utf-8'))}

def save_tl(tab):
    rows = [tab[k] for k in sorted(tab)]
    with open(TL, 'w', encoding='utf-8') as f:
        f.write('[\n' + ',\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n]\n')

def english(r, n):
    """English (family, given) of tl record r in scenario n."""
    return tuple(r.get('s%d' % n, r['en']))

def pairs(names, tab):
    """{(jp family, jp given): (en family, en given)} over all scenarios, plus conflicts."""
    out, bad = {}, []
    for n in SCENARIOS:
        for pid, jp in enumerate(names[n]):
            if not any(jp) or pid not in tab:
                continue
            en = english(tab[pid], n)
            if out.setdefault(jp, en) != en:
                bad.append((jp, out[jp], en, pid, n))
    return out, bad

def export():
    names, reads = all_names()
    tab = load_tl() if os.path.exists(TL) else {}
    rows = []
    for pid in range(len(names[0])):
        jp = {n: names[n][pid] for n in SCENARIOS}
        if not any(any(v) for v in jp.values()):
            continue
        r = {'id': pid, 'jp': {}, 'reading': {}}
        for n in SCENARIOS:
            r['jp']['s%d' % n] = jp[n]
            if pid < len(reads[n]):
                r['reading']['s%d' % n] = reads[n][pid]
        if pid in tab:
            r['en'] = {('s%d' % n): english(tab[pid], n) for n in SCENARIOS}
        rows.append(r)
    os.makedirs(os.path.dirname(SCRIPT), exist_ok=True)
    json.dump(rows, open(SCRIPT, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('%d persons -> %s' % (len(rows), SCRIPT))

def check():
    names, _ = all_names()
    tab = load_tl()
    _, bad = pairs(names, tab)
    for b in bad:
        print('conflict', b)
    miss = sorted({(pid, n) for n in SCENARIOS for pid, jp in enumerate(names[n])
                   if any(jp) and pid not in tab})
    for pid, n in miss[:50]:
        print('missing', pid, n, names[n][pid])
    print('%d conflicts, %d missing (person, scenario)' % (len(bad), len(miss)))
    return not bad and not miss

# ---------------------------------------------------------------- exe
#
# Lookup table in the .tl section: FNV-1a 32 hashes, sorted, of
#   pair:  family bytes (<= 9, to NUL), 0xFF, given bytes  -> (English family, English given)
#   part:  0xFE, part bytes                                -> English part
# (parts = every Japanese part whose English is the same wherever it occurs; they cover
# generated people and pairs the table does not know). Readers given a record (family[9]
# | given[9]) call en_family / en_given (rcx = record -> rax = string; all other
# registers kept), which fall back to the record's own field.

FNV_BASIS, FNV_PRIME = 0x811C9DC5, 0x01000193
PAIR_MARK, PART_MARK = 0xFF, 0xFE

def fnv(data, h=FNV_BASIS):
    for c in data:
        h = ((h ^ c) * FNV_PRIME) & 0xFFFFFFFF
    return h

def cp(s):
    return s.encode('cp932')

def pair_hash(f, g):
    return fnv(cp(g), fnv([PAIR_MARK], fnv(cp(f))))

def part_hash(p):
    return fnv(cp(p), fnv([PART_MARK]))

# parts read two ways: the reading used where only the part is known (e.g. the clan
# name 北条 in the Powers list; Kitajo people still get theirs from their pair)
PART_PREFER = {'北条': 'Hojo'}

EVENT_NAMES = os.path.join(setup.TL, 'ev', 'names.txt')

def event_pairs(path=EVENT_NAMES):
    """{(jp family, jp given): (en family, en given)} of event speakers (5A) and renames
    (3C) that are not persons of the scenario tables (tl/ev/names.txt, keyed by the first
    occurrence; the Japanese pair is read from the clean event file)."""
    import evtl
    out = {}
    if not os.path.exists(path):
        return out
    for raw in open(path, encoding='utf-8'):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        m = re.fullmatch(r'(\S+) @(\d+)\.(\d+) = (.*)', line)
        if not m:
            raise SystemExit('names.txt: bad line %r' % line)
        name, k, n, en = m[1], int(m[2]), int(m[3]), m[4]
        ins = next((i for kk, nn, i, j in evtl.units_ro(name) if (kk, nn) == (k, n)), None)
        if ins is None or ins.op not in (0x5A, 0x3C):
            raise SystemExit('names.txt: %s is not a 5A/3C name' % line)
        jf, jg = ins.strs[0].decode('cp932'), ins.strs[1].decode('cp932')
        ef, _, eg = en.partition('|')
        en = (ef.strip(), eg.strip())
        out[(jf, jg)] = en
        # the event engine stores the parts with half-width katakana as hiragana
        # (the nameplate shows 道場の門弟 for 道場ﾉ|門弟): that form too
        out.setdefault((half_to_hiragana(jf), half_to_hiragana(jg)), en)
    return out

def half_to_hiragana(s):
    """Half-width katakana (with their voicing marks) -> hiragana; the rest unchanged."""
    out, i = '', 0
    while i < len(s):
        c = s[i]
        if '\uff61' <= c <= '\uff9f':
            j = i + 1
            while j < len(s) and s[j] in '\uff9e\uff9f':
                j += 1
            k = unicodedata.normalize('NFKC', s[i:j])
            out += ''.join(chr(ord(x) - 0x60) if 'ァ' <= x <= 'ヶ' else x for x in k)
            i = j
        else:
            out += c
            i += 1
    return out

def lookup_entries(names, tab):
    """{hash: (english a, english b)} for pairs and parts (event pairs: pairs only)."""
    pr, bad = pairs(names, tab)
    assert not bad, bad[:3]
    out = {}
    def put(h, v, what):
        if out.setdefault(h, v) != v:
            raise SystemExit('names: hash collision %08X (%s)' % (h, what))
    for (f, g), (ef, eg) in pr.items():
        put(pair_hash(f, g), (ef, eg), f + g)
    for (f, g), en in event_pairs().items():
        if (f, g) not in pr:
            put(pair_hash(f, g), en, f + g)
    part = {}
    for (f, g), (ef, eg) in pr.items():
        for jp, en in ((f, ef), (g, eg)):
            if jp and en:
                part.setdefault(jp, set()).add(en)
    for jp, ens in part.items():
        if jp in PART_PREFER:
            put(part_hash(jp), (PART_PREFER[jp], ''), jp)
        elif len(ens) == 1:
            put(part_hash(jp), (ens.pop(), ''), jp)
    return out

# officer table (canonical names, shown e.g. by the id -> name dispatcher 0x14036BD30 with
# its flag set): 960 x 194 bytes, name[17] | reading[17] | ... | 7 x name[17] at +0x28
OFFICERS, OFF_REC, OFF_COUNT, OFF_SLOTS = 0x140BC0220, 194, 960, 7

FULL_NAME_TAIL = (0x140439155, '488bd8c60000')         # full-name getter 0x140439130, after ring alloc
FULL_NAME_NULL, FULL_NAME_RET = 0x1404391E4, 0x1404391E1
SITES = [
    # (va, original bytes, stub body, return va)
    (0x140418E2E, '488b4308eb08', 'mov rcx, [rbx + 8]\ncall en_family', 0x140418E3C),   # msg 'e'
    (0x140418E53, '488b53084883c209', 'mov rcx, [rbx + 8]\ncall en_given\nmov rdx, rax', 0x140418E5B),  # 'e' fallback
    (0x140418E72, '488b53084883c209', 'mov rcx, [rbx + 8]\ncall en_given\nmov rdx, rax', 0x140418E7A),  # msg 'f'
    (0x1402D76DA, '488b5008488bce', 'mov rcx, [rax + 8]\ncall en_family\nmov rdx, rax\nmov rcx, rsi', 0x1402D76E1),  # event \# family
    (0x1402D7701, '488b5008488bce4883c209', 'mov rcx, [rax + 8]\ncall en_given\nmov rdx, rax\nmov rcx, rsi', 0x1402D770C),  # event \# given
    # msg power variables ({02}{0B..14}e: daimyo house / merchant / ninja / pirate name, e.g.
    # 島津) in the power field handler 0x1404172D0: name = [vtbl+0x38](power), then strcpy
    (0x1404175AA, '498bc8ff5038488bd0', 'mov rcx, r8\ncall qword ptr [rax + 0x38]\nmov rcx, rax\ncall en_str\nmov rdx, rax', 0x1404175B3),
]
# Text-object set-text core 0x140694510 (obj, flags, text, r9b; ~200 callers, display
# only), hooked at entry (set_text):
#  - text = one known name part (SJIS, 4-8 bytes) -> its English; "A B" (half- or
#    full-width space) with A and B known parts -> "English-A English-B" (ring buffer);
#    A known and B ASCII ("%s Diplomacy" with a clan name) -> "English-A B".
#    Catches names read straight from a record (clan names, hero-select cards, ...).
#  - hiragana-only text (>= 2 characters) -> "" (kana readings above names).
#  - fit: an ASCII text of 1-24 bytes wider than its box (word [obj+0x24], sized for the
#    Japanese; 0 = no limit) gets the box widened to its width (advance() per byte with
#    the object's sizes [obj+0x2C]/[obj+0x2D]): the layout wraps per character otherwise.
# The message window draws one character per object, so it is never matched.
SET_TEXT = (0x140694510, '40535541544157', 0x140694517)
RING, RING_ALLOC = 0x14259DCA0, 0x1400121C0     # name ring buffer (128 x 256 bytes) and its allocator
ADVANCE = 0x140025356                           # advance(code, full, half) thunk (exepatch rewrites it)

# Debug (env TL_DEBUG_CALLERS=1, never for a release): a widened text is replaced by the
# code addresses (minus 0x140000000) found on the stack above the set-text core entry,
# to find which code draws a label.
DEBUG_CALLERS = bool(os.environ.get('TL_DEBUG_CALLERS'))
DBG_BODY = """
dbg_callers:
    mov word ptr [rdi + 0x24], 0x7fff
    push rdi
    lea rsi, [rsp + 0x4e8]
    lea rcx, [rip + hook_base]
    add rcx, {ring_off}
    call {ring_alloc}
    mov r8, rax
    mov r9, rax
    mov byte ptr [r9], 0x58
    inc r9
    mov r10d, 120
    mov r11d, 3
    lea rdi, [rip + hook_base]
    mov rdx, {hb_off}
    sub rdi, rdx
dc_loop:
    mov rax, qword ptr [rsi]
    add rsi, 8
    sub rax, rdi
    cmp rax, 0x1000
    jb dc_next
    cmp rax, 0xb01000
    jae dc_next
    lea rdx, [rdi + rax]
    cmp byte ptr [rdx - 5], 0xe8
    jne dc_next
    cmp rax, 0x6944cc
    je dc_next
    mov ecx, 24
dc_hex:
    sub ecx, 4
    mov edx, eax
    shr edx, cl
    and edx, 15
    cmp edx, 10
    jb dc_dig
    add edx, 0x27
dc_dig:
    add edx, 0x30
    mov byte ptr [r9], dl
    inc r9
    test ecx, ecx
    jnz dc_hex
    mov byte ptr [r9], 0x20
    inc r9
    dec r11d
    jz dc_end
dc_next:
    dec r10d
    jnz dc_loop
dc_end:
    mov byte ptr [r9], 0
    pop rdi
    ret
"""

LIB = """
fnv_add:                    ; rsi = bytes, ecx = max length, eax = hash; clobbers rsi ecx edx
    test ecx, ecx
    jz fa_end
fa_loop:
    movzx edx, byte ptr [rsi]
    test edx, edx
    jz fa_end
    xor eax, edx
    imul eax, eax, 0x01000193
    inc rsi
    dec ecx
    jnz fa_loop
fa_end:
    ret

find:                       ; eax = hash -> eax = index or -1; clobbers ecx edx r8 r9
    lea r8, [rip + tab_h]
    xor ecx, ecx
    mov edx, {count}
fi_loop:
    cmp ecx, edx
    jae fi_none
    lea r9d, [rcx + rdx]
    shr r9d, 1
    cmp eax, dword ptr [r8 + r9 * 4]
    je fi_found
    jb fi_less
    lea ecx, [r9 + 1]
    jmp fi_loop
fi_less:
    mov edx, r9d
    jmp fi_loop
fi_found:
    mov eax, r9d
    ret
fi_none:
    mov eax, -1
    ret

en_pair:                    ; rcx = record -> eax = index or -1; keeps other registers
    push rcx
    push rdx
    push rsi
    push r8
    push r9
    mov r9, rcx
    mov rsi, rcx
    mov ecx, 9
    mov eax, 0x811c9dc5
    call fnv_add
    xor eax, 0xff
    imul eax, eax, 0x01000193
    lea rsi, [r9 + 9]
    mov ecx, 9
    call fnv_add
    call find
    pop r9
    pop r8
    pop rsi
    pop rdx
    pop rcx
    ret

en_part:                    ; rcx = part -> eax = index or -1; keeps other registers
    push rcx
    push rdx
    push rsi
    push r8
    push r9
    mov rsi, rcx
    mov eax, 0x811c9dc5
    xor eax, 0xfe
    imul eax, eax, 0x01000193
    mov ecx, 9
    call fnv_add
    call find
    pop r9
    pop r8
    pop rsi
    pop rdx
    pop rcx
    ret

str_of:                     ; eax = index, rdx = offset table -> rax = string
    mov eax, dword ptr [rdx + rax * 4]
    lea rdx, [rip + tab_h + {off_s}]
    add rax, rdx
    ret

en_family:                  ; rcx = record -> rax = family (English if known)
    push rdx
    call en_pair
    cmp eax, -1
    je ef_part
    lea rdx, [rip + tab_h + {off_a}]
    call str_of
    pop rdx
    ret
ef_part:
    call en_part
    cmp eax, -1
    je ef_orig
    lea rdx, [rip + tab_h + {off_a}]
    call str_of
    pop rdx
    ret
ef_orig:
    mov rax, rcx
    pop rdx
    ret

en_given:                   ; rcx = record -> rax = given name (English if known)
    push rdx
    call en_pair
    cmp eax, -1
    je eg_part
    lea rdx, [rip + tab_h + {off_b}]
    call str_of
    pop rdx
    ret
eg_part:
    push rcx
    add rcx, 9
    call en_part
    cmp eax, -1
    je eg_orig
    lea rdx, [rip + tab_h + {off_a}]
    call str_of
    pop rcx
    pop rdx
    ret
eg_orig:
    mov rax, rcx
    pop rcx
    pop rdx
    ret

en_str:                     ; rcx = string (a whole name part) -> rax = English if known, else rcx
    call en_part
    cmp eax, -1
    je es_orig
    push rdx
    lea rdx, [rip + tab_h + {off_a}]
    call str_of
    pop rdx
    ret
es_orig:
    mov rax, rcx
    ret

en_part_n:                  ; rcx = part, edx = length -> eax = index or -1; keeps other registers
    push rcx
    push rdx
    push rsi
    push r8
    push r9
    mov rsi, rcx
    mov ecx, edx
    mov eax, 0x811c9dc5
    xor eax, 0xfe
    imul eax, eax, 0x01000193
    call fnv_add
    call find
    pop r9
    pop r8
    pop rsi
    pop rdx
    pop rcx
    ret

st_empty:
    .byte 0
    .align 4

set_text:                   ; entry of the set-text core: rcx = object, r8 = text
    test r8, r8
    jz st_go
    push rax
    push rcx
    push rdx
    push r9
    push r10
    push r11
    push rsi
    push rdi
    sub rsp, 0x38
    cmp byte ptr [r8], 0x81
    jb st_fit
    xor eax, eax
st_len:
    cmp byte ptr [r8 + rax], 0
    je st_lend
    inc eax
    cmp eax, 40
    jb st_len
    jmp st_fit
st_lend:
    cmp eax, 4
    jb st_fit
    mov esi, eax
    xor ecx, ecx
st_hira:
    cmp ecx, esi
    jae st_blank
    cmp byte ptr [r8 + rcx], 0x82
    jne st_nothira
    movzx edx, byte ptr [r8 + rcx + 1]
    cmp edx, 0x9f
    jb st_nothira
    cmp edx, 0xf1
    ja st_nothira
    add ecx, 2
    jmp st_hira
st_blank:
    lea r8, [rip + st_empty]
    jmp st_pop
st_nothira:
    cmp esi, 8
    ja st_split
    mov rcx, r8
    mov edx, esi
    call en_part_n
    cmp eax, -1
    je st_split
    lea rdx, [rip + tab_h + {off_a}]
    call str_of
    mov r8, rax
    jmp st_widen
st_split:
    xor ecx, ecx
st_sp:
    cmp ecx, esi
    jae st_pop
    movzx edx, byte ptr [r8 + rcx]
    cmp edx, 0x20
    je st_sp1
    cmp edx, 0x81
    jne st_spn
    cmp byte ptr [r8 + rcx + 1], 0x40
    je st_sp2
st_spn:
    cmp edx, 0x81
    jb st_spa
    cmp edx, 0xa0
    jb st_spb
    cmp edx, 0xe0
    jb st_spa
st_spb:
    add ecx, 2
    jmp st_sp
st_spa:
    inc ecx
    jmp st_sp
st_sp1:
    mov edi, 1
    jmp st_found
st_sp2:
    mov edi, 2
st_found:
    test ecx, ecx
    jz st_pop
    cmp ecx, 8
    ja st_pop
    mov r10d, ecx
    mov rcx, r8
    mov edx, r10d
    call en_part_n
    cmp eax, -1
    je st_fit
    mov r11d, eax
    mov ecx, r10d
    add ecx, edi
    mov edx, esi
    sub edx, ecx
    jle st_pop
    add rcx, r8
    cmp byte ptr [rcx], 0x80
    jb st_rawb
    cmp edx, 8
    ja st_pop
    call en_part_n
    cmp eax, -1
    je st_pop
    mov edi, eax
    push r11
    sub rsp, 8
    lea rcx, [rip + hook_base]
    add rcx, {ring_off}
    call {ring_alloc}
    add rsp, 8
    pop r11
    mov r8, rax
    mov eax, r11d
    lea rdx, [rip + tab_h + {off_a}]
    call str_of
    mov rdx, r8
st_ca:
    mov cl, byte ptr [rax]
    test cl, cl
    jz st_cae
    mov byte ptr [rdx], cl
    inc rax
    inc rdx
    jmp st_ca
st_cae:
    mov byte ptr [rdx], 0x20
    inc rdx
    mov r9, rdx
    mov eax, edi
    lea rdx, [rip + tab_h + {off_a}]
    call str_of
    mov rdx, r9
st_cb:
    mov cl, byte ptr [rax]
    mov byte ptr [rdx], cl
    test cl, cl
    jz st_widen
    inc rax
    inc rdx
    jmp st_cb
st_rawb:
    mov rdi, rcx
    push r11
    sub rsp, 8
    lea rcx, [rip + hook_base]
    add rcx, {ring_off}
    call {ring_alloc}
    add rsp, 8
    pop r11
    mov r8, rax
    mov eax, r11d
    lea rdx, [rip + tab_h + {off_a}]
    call str_of
    mov rdx, r8
st_ra:
    mov cl, byte ptr [rax]
    test cl, cl
    jz st_rae
    mov byte ptr [rdx], cl
    inc rax
    inc rdx
    jmp st_ra
st_rae:
    mov byte ptr [rdx], 0x20
    inc rdx
    mov rax, rdi
    jmp st_cb
st_widen:
st_fit:
    mov rdi, qword ptr [rsp + 0x68]
    movzx eax, word ptr [rdi + 0x24]
    test eax, eax
    jz st_pop
    xor ecx, ecx
st_fa:
    movzx edx, byte ptr [r8 + rcx]
    test edx, edx
    jz st_fb
    cmp edx, 0x20
    jb st_pop
    cmp edx, 0x7f
    jae st_pop
    inc ecx
    cmp ecx, 24
    jbe st_fa
    jmp st_pop
st_fb:
    test ecx, ecx
    jz st_pop
    mov qword ptr [rsp + 0x28], r8
    mov rsi, r8
    mov dword ptr [rsp + 0x20], 0
st_fc:
    movzx ecx, byte ptr [rsi]
    test ecx, ecx
    jz st_fd
    movzx edx, byte ptr [rdi + 0x2c]
    movzx r8d, byte ptr [rdi + 0x2d]
    call {advance}
    add dword ptr [rsp + 0x20], eax
    inc rsi
    jmp st_fc
st_fd:
    mov r8, qword ptr [rsp + 0x28]
    mov eax, dword ptr [rsp + 0x20]
    movzx ecx, word ptr [rdi + 0x24]
    cmp eax, ecx
    jle st_pop
    add eax, 2
    cmp eax, 0x7fff
    jbe st_w
    mov eax, 0x7fff
st_w:
    mov word ptr [rdi + 0x24], ax
{dbg_call}
st_pop:
    add rsp, 0x38
    pop rdi
    pop rsi
    pop r11
    pop r10
    pop r9
    pop rdx
    pop rcx
    pop rax
st_go:
    push rbx
    push rbp
    push r12
    push r15
    jmp {set_ret}

{dbg_body}
full_tail:                  ; in the full-name getter: rax = rbx-to-be = ring buffer, rdi = person
    mov rbx, rax
    mov byte ptr [rax], 0
    mov rcx, qword ptr [rdi + 8]
    test rcx, rcx
    jz ft_null
    call en_family
    mov rdx, rbx
ft_f:
    mov r8b, byte ptr [rax]
    mov byte ptr [rdx], r8b
    test r8b, r8b
    jz ft_fe
    inc rax
    inc rdx
    jmp ft_f
ft_fe:
    call en_given
    cmp byte ptr [rax], 0
    je ft_ret
    cmp rdx, rbx                ; family empty: no space
    je ft_g
    cmp byte ptr [rbx], 0x80    ; Japanese family (SJIS lead byte): no space
    jae ft_g
    mov byte ptr [rdx], 0x20
    inc rdx
ft_g:
    mov r8b, byte ptr [rax]
    mov byte ptr [rdx], r8b
    test r8b, r8b
    jz ft_ret
    inc rax
    inc rdx
    jmp ft_g
ft_ret:
    jmp {ret}
ft_null:
    mov rax, rbx
    jmp {null}
"""

def officer_names(exe, tab, names):
    """Write English into the officer table (in place): canonical name and the 7 slots."""
    from pesect import IMAGE_BASE
    import pefile
    pe = pefile.PE(data=bytes(exe), fast_load=True)
    base = pe.get_offset_from_rva(OFFICERS - IMAGE_BASE)
    n = 0
    for pid in range(OFF_COUNT):
        r = tab.get(pid)
        if not r:
            continue
        full = {}
        for s in SCENARIOS:
            f, g = names[s][pid]
            full.setdefault(f + g, english(r, s))
        o = base + pid * OFF_REC
        for k in [0] + [0x28 + 17 * i for i in range(OFF_SLOTS)]:
            jp = field(exe[o + k:o + k + 17])
            if not jp:
                continue
            en = full.get(jp, tuple(r['en']))
            s = ' '.join(p for p in en if p)
            if len(s) > 16 and en[0] and en[1]:
                s = en[0][0] + '. ' + en[1]
            b = s.encode('ascii')[:16]
            exe[o + k:o + k + 17] = b + b'\0' * (17 - len(b))
            n += 1
    return n

# Speaker nameplate 0x1406DDF50 (window, name, reading): the name is cut into 2-byte text
# objects (max 8 = 16 bytes) at fixed full-width steps, centered. Rewritten in place
# (0x1406DE0F3-0x1406DE1D6): the whole name in object 0 ([window+0x480]), centered by its
# width (advance() per byte, full width for SJIS pairs). Readings (kana above the name)
# are not passed for persons (0x1406DDB50 call reading getter -> xor eax, eax).
NAMEPLATE_VA, NAMEPLATE_END = 0x1406DE0F3, 0x1406DE1D6
NAMEPLATE_HEAD = '498bcee8f95793ff8bd8b808000000d1'
NO_READING = (0x1406DDB50, 'e875aa93ff', '31c0909090')
# the 8 nameplate objects are created 34 px wide (one full-width character) at 0x1406DD76C:
# 384 px so object 0 holds a whole English name
NAMEPLATE_WIDTH = (0x1406DD75D, '41b922000000', '41b980010000')
NAMEPLATE_ASM = """
    mov r12, qword ptr [rsp + 0x88]
    mov rcx, r14
    call 0x1400138f4
    test eax, eax
    jz np_end
    mov ecx, 5
    call 0x1400123a5
    movzx esi, byte ptr [rax]
    xor ebx, ebx
    mov r15, r14
np_w:
    movzx ecx, byte ptr [r15]
    test ecx, ecx
    jz np_wend
    inc r15
    cmp ecx, 0x80
    jb np_half
    cmp ecx, 0xa1
    jb np_full
    cmp ecx, 0xe0
    jb np_half
np_full:
    inc r15
    add ebx, esi
    jmp np_w
np_half:
    mov edx, esi
    mov r8d, esi
    shr r8d, 1
    call 0x140025356
    add ebx, eax
    jmp np_w
np_wend:
    sub ebp, ebx
    sar ebp, 1
    add ebp, dword ptr [rsp + 0x34]
    mov rsi, qword ptr [rdi + 0x480]
    mov rcx, rsi
    mov edx, ebp
    mov r8d, r13d
    call 0x140023920
    mov ecx, 5
    call 0x1400242fd
    movzx ebx, byte ptr [rax]
    mov ecx, 5
    call 0x1400123a5
    movzx edx, byte ptr [rax]
    mov r8d, ebx
    mov rcx, rsi
    call 0x140001465
    mov rcx, rsi
    mov r8, r14
    xor edx, edx
    call 0x140008238
    mov rcx, rsi
    mov edx, 7
    call 0x14002c2af
    mov rcx, rsi
    xor edx, edx
    call 0x14002c7c3
np_end:
    jmp 0x1406de1d6
"""

def nameplate_patch(seg, ks):
    b = bytes(ks.asm(NAMEPLATE_ASM, NAMEPLATE_VA)[0])
    n = NAMEPLATE_END - NAMEPLATE_VA
    assert len(b) <= n, len(b)
    _patch(seg, ks, NAMEPLATE_VA, None, NAMEPLATE_HEAD, raw=b + b'\xcc' * (n - len(b)))
    for at, old, new in (NO_READING, NAMEPLATE_WIDTH):
        _patch(seg, ks, at, None, old, raw=bytes.fromhex(new))

def apply(seg):
    """Hook the name readers of seg.exe (pesect.Segment) and add the lookup table."""
    import keystone
    names, _ = all_names()
    tab = load_tl()
    ent = lookup_entries(names, tab)
    n_off = officer_names(seg.exe, tab, names)
    hs = sorted(ent)
    strs, soff = bytearray(), {}
    def so(s):
        if s not in soff:
            soff[s] = len(strs)
            strs.extend(s.encode('ascii') + b'\0')
        return soff[s]
    a = [so(ent[h][0]) for h in hs]
    b = [so(ent[h][1]) for h in hs]
    # entry points first, one per 64-byte slot: slot 0 = full-name tail, slot 1+i = SITES[i]
    # last slot = set-text hook
    slots = (['jmp full_tail'] + ['%s\njmp 0x%x' % (body, ret) for va, old, body, ret in SITES]
             + ['jmp set_text'])
    n = len(hs)
    va = seg.add(b'', align=64, share=False)
    src = ('hook_base:\n' + '\n'.join(s + '\n.align 64' for s in slots) + '\n'
           + LIB.format(count=n, ret='0x%x' % FULL_NAME_RET, null='0x%x' % FULL_NAME_NULL,
                        off_a=4 * n, off_b=8 * n, off_s=12 * n, set_ret='0x%x' % SET_TEXT[2],
                        ring_off='%d' % (RING - va), ring_alloc='0x%x' % RING_ALLOC, advance='0x%x' % ADVANCE,
                        dbg_call='    call dbg_callers' if DEBUG_CALLERS else '',
                        dbg_body=DBG_BODY.replace('{ring_off}', '%d' % (RING - va)).replace(
                            '{ring_alloc}', '0x%x' % RING_ALLOC).replace('{hb_off}', '0x%x' % (va - 0x140000000)) if DEBUG_CALLERS else '')
           + '\n.align 4\ntab_h:\n')
    # tables as raw bytes after the code (keystone is very slow on long data directives)
    data = struct.pack('<%dI' % n, *hs) + struct.pack('<%dI' % n, *a) + struct.pack('<%dI' % n, *b) + bytes(strs)
    ks = keystone.Ks(keystone.KS_ARCH_X86, keystone.KS_MODE_64)
    src = '\n'.join(l.split(';')[0] for l in src.split('\n'))     # keystone hangs on ; comments
    code = bytes(ks.asm(src, va)[0])
    assert seg.add(code + data, share=False) == va
    patch = lambda at, asm_src, old: _patch(seg, ks, at, asm_src, old)
    patch(FULL_NAME_TAIL[0], 'jmp 0x%x' % va, FULL_NAME_TAIL[1])
    for i, (at, old, body, ret) in enumerate(SITES):
        patch(at, 'jmp 0x%x' % (va + 64 * (i + 1)), old)
    patch(SET_TEXT[0], 'jmp 0x%x' % (va + 64 * (len(SITES) + 1)), SET_TEXT[1])
    nameplate_patch(seg, ks)
    return len(hs), n_off

def _patch(seg, ks, at, asm_src, old, raw=None):
    o = seg.va2off(at)
    old = bytes.fromhex(old)
    if bytes(seg.exe[o:o + len(old)]) != old:
        raise SystemExit('names: patch %X: expected %s, found %s' % (at, old.hex(), seg.exe[o:o + len(old)].hex()))
    if raw is not None:
        seg.exe[o:o + len(raw)] = raw
        return
    b = bytes(ks.asm(asm_src, at)[0])
    assert len(b) <= len(old)
    seg.exe[o:o + len(old)] = b + b'\x90' * (len(old) - len(b))

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'export':
        export()
    elif cmd == 'check':
        sys.exit(0 if check() else 1)
    else:
        sys.exit(__doc__)

if __name__ == '__main__':
    main()
