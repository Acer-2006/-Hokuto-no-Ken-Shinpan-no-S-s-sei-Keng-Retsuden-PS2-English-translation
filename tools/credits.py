"""The arcade staff credits (HISTORY: Arcade Version Staff Credits).

Unlike the PS2's own staff roll (pictures, see staffroll.py), the arcade's is
text in the program: a table of line pointers, English at 0x2E5960 (the
Japanese one is at 0x2E4FD0), each line Shift-JIS full-width text with '＠'
in front of the two columns of a cast line. The English came with the
arcade's overseas release; translation/credits.tsv corrects some of its
lines by number (THOUTHER and other typos, family-name-first and all-caps
names), so the names read the same as in the PS2 staff roll.

The English names' strings sit together and only this table points at them,
so they are written there again, packed, with the corrected ones.
"""
import os
import struct

import numpy as np

VA_BASE, FILE_BASE = 0x100000, 0x80
TABLE, LINES = 0x2E5960, 611
AREA = (0x2F6AA0, 0x2F7D50)       # the English names' strings


def load(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'translation', 'credits.tsv')
    out = {}
    with open(path, encoding='utf-8') as f:
        next(f)
        for row in f:
            if row.strip() and not row.startswith('#'):
                line, text = row.rstrip('\n').split('\t')[:2]
                out[int(line)] = text
    return out


def encode(text):
    """Full-width Shift-JIS, as the credits are written."""
    wide = ''.join('　' if c == ' ' else '・' if c == '·' else '−' if c == '-'
                   else chr(ord(c) + 0xFEE0) if '!' <= c <= '~' else c for c in text)
    return wide.encode('cp932')


def _file(va):
    return va - VA_BASE + FILE_BASE


def patch(prog, lines=None):
    """Rewrite the English credits in the program image `prog` (bytearray)."""
    lines = load() if lines is None else lines
    table = list(struct.unpack_from(f'<{LINES}I', prog, _file(TABLE)))
    lo, hi = AREA
    # nothing but this table may point into the area
    words = np.frombuffer(bytes(prog[:len(prog) // 4 * 4]), '<u4')
    inside = np.nonzero((words >= lo) & (words < hi))[0] * 4
    t0, t1 = _file(TABLE), _file(TABLE) + 4 * LINES
    assert all(t0 <= o < t1 for o in inside), 'credits: unexpected pointer into the names'

    def old(va):
        o = _file(va)
        return bytes(prog[o:prog.index(b'\0', o)])

    texts = {}
    for k, va in enumerate(table):
        if k in lines:
            texts[k] = encode(lines[k])
        elif lo <= va < hi:
            texts[k] = old(va)
    blob, where = bytearray(), {}
    for k, data in texts.items():
        if data not in where:
            where[data] = lo + len(blob)
            blob += data + b'\0'
            blob += bytes(-len(blob) % 4)
        table[k] = where[data]
    assert len(blob) <= hi - lo, f'credits: {len(blob) - (hi - lo)} bytes too long'
    prog[_file(lo):_file(hi)] = bytes(blob).ljust(hi - lo, b'\0')
    struct.pack_into(f'<{LINES}I', prog, _file(TABLE), *table)
    return len(blob), hi - lo
