"""Insert the English translation into the PS2 program (SLPM_666.60).

- Timeline lines are written in place (fixed 48-byte fields).
- Gallery captions, episode titles and save messages are repacked into the
  space their Japanese strings used, and every pointer to them is updated.

Outputs a patched copy of the program plus a PCSX2 .pnach section with the
changes, so the result can be previewed without rebuilding the ISO.

usage: insert_text.py SLPM_666.60 translation_dir out_elf out_pnach_section
"""
import csv, os, struct, sys

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


def encode(text):
    text = text.replace('\\n', '\n')
    bad = [c for c in text if c in '@%' or ord(c) > 126 or (ord(c) < 32 and c != '\n')]
    if bad:
        raise ValueError(f'unsupported characters {bad!r} in {text!r}')
    return text.encode('ascii')


def trailing_controls(raw):
    """Control bytes (e.g. a tab) at the end of an original Japanese field."""
    s = raw.split(b'\0')[0]
    tail = b''
    while s and s[-1] < 0x20 and s[-1] != 0x0A:
        tail = bytes([s[-1]]) + tail
        s = s[:-1]
    return tail


def insert_timeline(d, rows):
    for r in rows:
        n = int(r['id'][2:])
        base = TL_START + n * TL_STRIDE
        for k, key in enumerate(('line1', 'line2')):
            fo = base + k * TL_FIELD
            orig = bytes(d[fo:fo + TL_FIELD])
            new = encode(r[key]) + (trailing_controls(orig) if r[key] else b'')
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


def insert_strings(d, orig, rows):
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
    items = sorted(((encode(r['text']) + b'\0', int(r['offset'], 16), r['id']) for r in rows),
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


def main():
    elf, tdir, out_elf, out_pnach = sys.argv[1:5]
    orig = open(elf, 'rb').read()
    d = bytearray(orig)
    insert_timeline(d, read_tsv(os.path.join(tdir, 'timeline.tsv')))
    used, total = insert_strings(d, orig, read_tsv(os.path.join(tdir, 'gallery_save.tsv')))
    open(out_elf, 'wb').write(d)
    text, n = pnach_section(orig, d, 'English text preview',
                            'Timeline, gallery and save message translations (work in progress).')
    open(out_pnach, 'w', encoding='ascii').write(text)
    print(f'strings: {used}/{total} bytes used; pnach writes: {n}')


if __name__ == '__main__':
    main()
