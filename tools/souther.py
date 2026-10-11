"""SOUTHER instead of THOUTHER.

The arcade's English graphics spell サウザー "THOUTHER". The translation uses
"Souther" everywhere else, so each THOUTHER picture is rebuilt as SOUTHER from
the game's own lettering: the S comes from SHIN in the same style, the rest
is OUTHER from THOUTHER.

Most styles are sized to the name, so the two are joined at the gaps between
letters (cut along the lettering's slant): SHIN up to the S|H gap, then
THOUTHER from the H|O gap on. The entry's width is set to the new width.

Two styles are names centred on a fixed-size bar. There the bar background
(rows that repeat every 2 pixels) is rebuilt under the old lettering, and S +
OUTHER (the pixels that differ from each bar's background) are drawn centred
where the old name was.

The VS screen's big names are spelled letter by letter (TEXH 0x4DFA800
entry 40 holds K E N S H I R O D M Y G J U T A) from a table of 10-byte
names in the program; patch() changes that one.
"""
import struct

import numpy as np

import texh

# (TEXH, entry) of THOUTHER, (TEXH, entry) of SHIN, slant (pixels per row,
# top to the right), H|O gap column in THOUTHER, S|H gap column in SHIN; the
# columns are where the cut crosses the middle row of the lettering
SPLICES = [
    ((0x4C16800, 13), (0x4C16800, 12), 0.10, 41, 35),    # player select
    ((0x4C16800, 88), (0x4C16800, 87), 0.30, 50, 39),    # player select
    ((0x4D86800, 33), (0x4D86800, 32), 0.00, 45, 22),    # results
    ((0x4DFA800, 37), (0x4DFA800, 36), 0.30, 38, 15),    # VS screen
    ((0x4FA0000, 0), (0x4F27000, 0), 0.25, 127, 93),     # character profile
    ((0x579A000, 15), (0x53DE000, 23), 0.05, 56, 32),    # opening, voice actor card
    ((0x5D30800, 16), (0x5D30800, 15), 0.20, 26, 16),    # ranking
    ((0x5D30800, 22), (0x5D30800, 21), 0.15, 25, 14),    # ranking
    ((0x754D000, 54), (0x754D000, 51), 0.00, 38, 17),    # training
]
# names centred on a bar: THOUTHER, SHIN, slant, H|O gap, S|H gap, middle row
BARS = [
    ((0x4D86800, 43), (0x4D86800, 42), 0.5, 60, 80, 21),     # results
    ((0x50AB800, 51), (0x50AB800, 47), 0.4, 104, 116, 27),   # continue
]
EDGE = 4             # pixels of a bar's slanted left end before its background

VA_BASE, FILE_BASE = 0x100000, 0x80
VS_NAME = 0x2CBE36   # THOUTHER in the VS screen's name table (10 bytes each)


def patch(prog):
    """SOUTHER in the VS screen's name table of the program image `prog`."""
    o = VS_NAME - VA_BASE + FILE_BASE
    assert bytes(prog[o:o + 10]) == b'THOUTHER\0\0', 'VS name table not found'
    prog[o:o + 10] = b'SOUTHER'.ljust(10, b'\0')


def _canvas(buf, texh_off, index):
    entry = list(texh.entries(buf, texh_off))[index]
    tiles = entry['tiles']
    W = max(max(t['x'] + t['w'] for t in tiles), entry['w'])
    H = max(max(t['y'] + t['h'] for t in tiles), entry['h'])
    can = np.zeros((H, W), np.uint8)
    for t in tiles:
        px, _ = texh.pixels(bytes(buf[t['data']:t['data'] + t['size']]))
        can[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']] = px
    return entry, can


def _rows(img):
    ys = np.nonzero(img.any(axis=1))[0]
    return int(ys.min()), int(ys.max())


def _cut(x, slant, y, middle):
    return max(0, x + int(round(slant * (middle - y))))


def splice(thouther, shin, slant, x_t, x_s):
    """SHIN left of its S|H cut, then THOUTHER right of its H|O cut, row by
    row along the same slant (so the joined parts keep their shapes)."""
    h = max(thouther.shape[0], shin.shape[0])
    t = np.pad(thouther, ((0, h - thouther.shape[0]), (0, 0)))
    s = np.pad(shin, ((0, h - shin.shape[0]), (0, 0)))
    r0, r1 = _rows(t)
    middle = (r0 + r1) / 2
    out = np.zeros((h, t.shape[1]), np.uint8)
    for y in range(h):
        a, b = _cut(x_t, slant, y, middle), _cut(x_s, slant, y, middle)
        tail = t[y, a:]
        n = min(len(tail), out.shape[1] - b)
        out[y, :b] = s[y, :b]
        out[y, b:b + n] = tail[:n]
    return out


def _bar_background(img):
    """Per row: (first, end, even, odd) - the bar's background columns
    [first, end) and its two alternating values, taken from the first run of
    4 repeating pixels after the left end; end is where the right end starts
    (the trailing pixels that don't fit the pattern)."""
    out = {}
    for y in range(img.shape[0]):
        row = img[y]
        nz = np.nonzero(row)[0]
        if not len(nz):
            continue
        for x in range(nz[0] + EDGE, nz[-1] - 3):
            r = row[x:x + 4]
            if r[0] and r[0] == r[2] and r[1] == r[3]:
                even, odd = (int(r[0]), int(r[1])) if x % 2 == 0 else (int(r[1]), int(r[0]))
                end = nz[-1] + 1
                while end > x and row[end - 1] != (even if (end - 1) % 2 == 0 else odd):
                    end -= 1
                out[y] = (x, end, even, odd)
                break
    return out


def _lettering(img, bg):
    """Mask of the pixels that differ from the bar's background."""
    m = np.zeros(img.shape, bool)
    for y, (first, end, even, odd) in bg.items():
        xs = np.arange(first, end)
        m[y, first:end] = img[y, first:end] != np.where(xs % 2 == 0, even, odd)
    return m


def bar(thouther, shin, slant, x_t, x_s, middle):
    """THOUTHER's bar with S (from SHIN's bar) + OUTHER centred on it."""
    h = max(thouther.shape[0], shin.shape[0])
    t = np.pad(thouther, ((0, h - thouther.shape[0]), (0, 0)))
    s = np.pad(shin, ((0, h - shin.shape[0]), (0, 0)))
    bg_t = _bar_background(t)
    m_t, m_s = _lettering(t, bg_t), _lettering(s, _bar_background(s))
    letters = {}
    for y in range(h):
        a, b = _cut(x_t, slant, y, middle), _cut(x_s, slant, y, middle)
        for x in np.nonzero(m_s[y, :b])[0]:
            letters[(y, x - b + a)] = s[y, x]
        for x in np.nonzero(m_t[y, a:])[0] + a:
            letters[(y, x)] = t[y, x]
    old = np.nonzero(m_t.any(axis=0))[0]
    new = [x for _, x in letters]
    shift = ((old.min() + old.max()) - (min(new) + max(new))) // 2
    shift -= shift % 2                       # keep the dithering in step
    out = t.copy()
    for y, (first, end, even, odd) in bg_t.items():
        xs = np.arange(first, end)
        out[y, first:end] = np.where(xs % 2 == 0, even, odd)
    for (y, x), v in letters.items():
        x += shift
        assert bg_t[y][0] <= x < bg_t[y][1], (y, x)
        out[y, x] = v
    return out


def _tiles_for(entry, img):
    """Tile datas for img (in the entry's coordinates), same tile layout."""
    datas = []
    for t in entry['tiles']:
        px = np.zeros((t['h'], t['w']), np.uint8)
        part = img[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']]
        px[:part.shape[0], :part.shape[1]] = part
        datas.append(px)
    return datas


def _encode(buf, entry, img):
    out = []
    for t, px in zip(entry['tiles'], _tiles_for(entry, img)):
        old = bytes(buf[t['data']:t['data'] + t['size']])
        has_pal, bpp = struct.unpack_from('<2H', old, 2)
        pal = old[16:16 + (4 << bpp)] if has_pal & 1 else b''
        out.append(texh.compress(px, bpp, pal))
    return out


def changes(buf):
    """({TEXH: {entry: [(tile data, rect), ...]}}, [other edits]): the new
    tiles (same layout as before) and the entries' new widths."""
    banks, edits = {}, []
    for (bt, it), (bs, is_), slant, x_t, x_s in SPLICES:
        entry, thouther = _canvas(buf, bt, it)
        _, shin = _canvas(buf, bs, is_)
        img = splice(thouther, shin, slant, x_t, x_s)
        width = int(np.nonzero(img.any(axis=0))[0].max()) + 1
        assert width < entry['w'], (hex(bt), it)
        banks.setdefault(bt, {})[it] = _tiles(entry, _encode(buf, entry, img[:, :width]))
        edits.append((entry['offset'] + 4, struct.pack('<H', width), f'SOUTHER {it} width'))
    for (bt, it), (bs, is_), slant, x_t, x_s, middle in BARS:
        entry, thouther = _canvas(buf, bt, it)
        _, shin = _canvas(buf, bs, is_)
        img = bar(thouther, shin, slant, x_t, x_s, middle)
        banks.setdefault(bt, {})[it] = _tiles(entry, _encode(buf, entry, img))
    return banks, edits


def _tiles(entry, datas):
    return [(d, (t['x'], t['y'], t['x'] + t['w'], t['y'] + t['h'])) for t, d in zip(entry['tiles'], datas)]
