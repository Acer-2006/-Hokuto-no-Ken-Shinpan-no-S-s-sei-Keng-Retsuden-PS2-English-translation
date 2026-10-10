"""Insert the English translation into the PS2 program (SLPM_666.60).

- Timeline lines are written in place (fixed 48-byte fields).
- Gallery captions, episode titles and save messages are repacked into the
  space their Japanese strings used, and every pointer to them is updated.

Text drawn by the game's Shift-JIS renderer (timeline, gallery captions,
episode titles) is stored as letter-pair codes (see pairfont.py), so it
needs the matching font tiles, which build_iso.py writes into HK_B.BIN.
Save messages are never drawn and stay plain ASCII.

usage: insert_text.py SLPM_666.60 translation_dir out_elf out_pnach_section
"""
import csv, os, struct, sys
from pairfont import PairEncoder

VA_BASE, FILE_BASE = 0x100000, 0x80          # single PT_LOAD segment
DATA_START = 0x1C0000                         # pointer tables live after .text
TL_START, TL_STRIDE, TL_FIELD = 0x1E73E4, 0x64, 0x30
ALIGN = 4


def va(fo):
    return fo - FILE_BASE + VA_BASE


def read_tsv(path):
    with open(path, encoding='utf-8') as f:
        rows = list(csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE))
    hdr = rows[0]
    return [dict(zip(hdr, r + [''] * (len(hdr) - len(r)))) for r in rows[1:] if r]


PAIR_IDS = ('GA', 'EP', 'UI')     # gallery_save.tsv rows drawn by the renderer
IN_PLACE_IDS = ('UI',)            # addressed directly by code: keep their address


def check(text, allow_newline):
    bad = [c for c in text if c in '@%' or ord(c) > 126
           or (ord(c) < 32 and not (allow_newline and c == '\n'))]
    if bad:
        raise ValueError(f'unsupported characters {bad!r} in {text!r}')


def encode(text, pairs=None):
    """ASCII bytes, or letter-pair codes when a PairEncoder is given."""
    text = text.replace('\\n', '\n')
    check(text, allow_newline=pairs is None)
    return pairs.encode(text) if pairs else text.encode('ascii')


def trailing_controls(raw):
    """Control bytes (e.g. a tab) at the end of an original Japanese field."""
    s = raw.split(b'\0')[0]
    tail = b''
    while s and s[-1] < 0x20 and s[-1] != 0x0A:
        tail = bytes([s[-1]]) + tail
        s = s[:-1]
    return tail


def insert_timeline(d, rows, pairs=None):
    for r in rows:
        n = int(r['id'][2:])
        base = TL_START + n * TL_STRIDE
        for k, key in enumerate(('line1', 'line2')):
            fo = base + k * TL_FIELD
            orig = bytes(d[fo:fo + TL_FIELD])
            new = encode(r[key], pairs)
            if r[key] and not pairs:
                new += trailing_controls(orig)
            if len(new) > TL_FIELD - 1:
                raise ValueError(f"{r['id']} {key} is {len(new)} bytes (max {TL_FIELD - 1})")
            d[fo:fo + TL_FIELD] = new.ljust(TL_FIELD, b'\0')


def slots_for(orig, offsets):
    """Space each original string may be replaced into: up to the next string,
    or to the end of its 16-byte padding at the end of a run."""
    starts = set(offsets)
    slots = []
    for o in sorted(offsets):
        term = orig.index(b'\0', o)
        k = term
        while orig[k] == 0:
            k += 1
        end = k if k in starts else min(k, (term + 1 + 15) // 16 * 16)
        slots.append([o, end])
    return slots


def insert_in_place(d, orig, rows, pairs=None):
    for r in rows:
        o = int(r['offset'], 16)
        old_len = orig.index(b'\0', o) - o
        new = encode(r['text'], pairs if r['id'][:2] in PAIR_IDS else None)
        if len(new) > old_len:
            raise ValueError(f"{r['id']} is {len(new)} bytes (max {old_len})")
        d[o:o + old_len] = new.ljust(old_len, b'\0')


def insert_strings(d, orig, rows, pairs=None):
    insert_in_place(d, orig, [r for r in rows if r['id'][:2] in IN_PLACE_IDS], pairs)
    rows = [r for r in rows if r['id'][:2] not in IN_PLACE_IDS]
    offsets = [int(r['offset'], 16) for r in rows]
    slots = slots_for(orig, offsets)
    # where each original string is pointed to from (data area only)
    refs = {}
    for o in offsets:
        target = va(o)
        refs[o] = [i for i in range(DATA_START, len(orig) - 3, 4)
                   if struct.unpack_from('<I', orig, i)[0] == target]
        if not refs[o]:
            raise ValueError(f'no pointer found for string at {o:#x}')
    for s, e in slots:
        d[s:e] = b'\0' * (e - s)
    # merge neighbouring slots into continuous runs
    free = []
    for s, e in slots:
        if free and free[-1][1] == s:
            free[-1][1] = e
        else:
            free.append([s, e])
    # first-fit decreasing packing
    def enc(r):
        return encode(r['text'], pairs if r['id'][:2] in PAIR_IDS else None)
    items = sorted(((enc(r) + b'\0', int(r['offset'], 16), r['id']) for r in rows),
                   key=lambda x: -len(x[0]))
    placed = {}
    for blob, old, sid in items:
        for slot in free:
            start = (slot[0] + ALIGN - 1) // ALIGN * ALIGN
            if start + len(blob) <= slot[1]:
                d[start:start + len(blob)] = blob
                slot[0] = start + len(blob)
                placed[old] = start
                break
        else:
            raise ValueError(f'out of space placing {sid}')
    for old, new in placed.items():
        for p in refs[old]:
            struct.pack_into('<I', d, p, va(new))
    used = sum(len(b) for b, _, _ in items)
    total = sum(e - s for s, e in slots)
    return used, total


def pnach_section(orig, d, title, description):
    lines = [f'[{title}]', 'author=Acer-2006', f'description={description}']
    for i in range(0, len(orig) - 3, 4):
        if orig[i:i + 4] != d[i:i + 4]:
            word = struct.unpack_from('<I', d, i)[0]
            lines.append(f'patch=1,EE,{va(i):08x},word,{word:08x}')
    return '\n'.join(lines) + '\n', len(lines) - 3


def patch_program(orig, tdir, use_pairs=True):
    """Returns (patched program, PairEncoder or None, (used, total) string bytes)."""
    d = bytearray(orig)
    pairs = PairEncoder() if use_pairs else None
    insert_timeline(d, read_tsv(os.path.join(tdir, 'timeline.tsv')), pairs)
    stats = insert_strings(d, orig, read_tsv(os.path.join(tdir, 'gallery_save.tsv')), pairs)
    return d, pairs, stats


def main():
    elf, tdir, out_elf, out_pnach = sys.argv[1:5]
    orig = open(elf, 'rb').read()
    d, pairs, (used, total) = patch_program(orig, tdir)
    open(out_elf, 'wb').write(d)
    text, n = pnach_section(orig, d, 'English text (needs the patched font)',
                            'Timeline, gallery and save message translations. The text is stored '
                            'as letter pairs, so it only shows up correctly on a disc built '
                            'with tools/build_iso.py.')
    open(out_pnach, 'w', encoding='ascii').write(text)
    print(f'strings: {used}/{total} bytes used; letter pairs: {len(pairs.codes)}; '
          f'pnach writes: {n}')


if __name__ == '__main__':
    main()
