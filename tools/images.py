"""English replacements for text drawn into the game's textures.

Each replacement is generated at build time from your own disc: the tool
decodes the original tile, draws the English in the same style and palette
indices, re-compresses it and checks it fits the original's space. No game
graphics are stored in this repository.
"""
import os
import struct

import numpy as np
from PIL import Image, ImageDraw

import fonts
import memcard
import notices
import smallfont
import souther
import staffroll
import texh
import ui

BOLD = fonts.SANS_BOLD       # its Latin matches the game's gothic

HISTORY = 0x5EC9000      # HISTORY mode screen resource (FARC offset in HK_B.BIN)

# HISTORY chapter labels: entry -> English. Original Japanese for reference.
CHAPTERS = {
    164: 'PAST',            # 過去編
    165: 'ZEED',            # ジード編
    166: 'JUDA',            # ユダ編
    167: 'SOUTHER',         # サウザー編
    168: 'FATED DUEL',      # 宿命の戦い編 (Toki vs Raoh)
    169: 'STAR OF MERCY',   # 南斗慈母星編
    170: 'FINAL BATTLE',    # 世紀末決戦編
    171: 'KING',            # KING編
    172: 'GOLAN',           # GOLAN編
    173: 'JACKAL',          # ジャッカル編
    174: 'FANG CLAN',       # 牙一族編
    175: 'JAGI',            # ジャギ編
    176: 'AMIBA',           # アミバ編
    177: 'CASSANDRA',       # カサンドラ編
    178: 'RAOH',            # ラオウ編
}

# Chapter label style (4bpp): 0 transparent, 12 outline, a vertical gradient
# of fill indices by row, darker indices for anti-aliased edges.
LABEL_FILL = {7: 7, 8: 7, 9: 8, 10: 9, 11: 10, 12: 11, 13: 13, 14: 14, 15: 15,
              16: 15, 17: 15, 18: 14, 19: 13, 20: 11, 21: 10, 22: 9, 23: 8, 24: 7}
LABEL_OUTLINE = 12
LABEL_EDGE = ((0.55, 6), (0.35, 4), (0.15, 2))
LABEL_TOP, LABEL_CAP = 9, 14      # cap height 14 px starting on row 9
MIN_LABEL_WIDTH = 100             # labels may use at least this many columns


def text_coverage(text, cap, max_width, height, top, ss=4):
    """Anti-aliased coverage (0..1) of `text` with cap height `cap`,
    squeezed horizontally to at most `max_width` pixels."""
    size = cap
    font = fonts.load(BOLD, size * ss)
    while font.getbbox('H')[3] - font.getbbox('H')[1] < cap * ss:
        size += 1
        font = fonts.load(BOLD, size * ss)
    bb = font.getbbox(text)
    w = bb[2] - bb[0]
    im = Image.new('L', (w + 2 * ss, height * ss), 0)
    hb = font.getbbox('H')
    ImageDraw.Draw(im).text((ss - bb[0], top * ss - hb[1]), text, font=font, fill=255)
    width = min(max_width, (im.width + ss - 1) // ss)
    im = im.resize((width, height), Image.LANCZOS if width * ss < im.width else Image.BOX)
    return np.asarray(im, dtype=float) / 255


def label_pixels(text, orig, max_width=None):
    """128x32 index image for a chapter label, centred like the originals."""
    h, w = orig.shape
    used = np.where((orig != 0).any(axis=0))[0]
    orig_width = int(used[-1] - used[0] + 1) if len(used) else w
    limit = max(orig_width, MIN_LABEL_WIDTH) - 4
    cov = text_coverage(text, LABEL_CAP, min(limit, max_width or limit), h, LABEL_TOP)
    mask = np.zeros((h, w), dtype=bool)
    fill = np.zeros((h, w), dtype=float)
    x0 = (w - cov.shape[1]) // 2
    fill[:, x0:x0 + cov.shape[1]] = cov
    mask = fill >= 0.15
    out = np.zeros((h, w), dtype=np.uint8)
    ring = np.zeros_like(mask)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if abs(dy) + abs(dx) <= 3:
                ring |= np.roll(np.roll(mask, dy, 0), dx, 1)
    out[ring] = LABEL_OUTLINE
    for y in range(h):
        for x in range(w):
            c = fill[y, x]
            if c >= 0.75:
                out[y, x] = LABEL_FILL.get(y, 7)
            else:
                for t, idx in LABEL_EDGE:
                    if c >= t:
                        out[y, x] = idx
                        break
    return out


def fit(make, old_size, widths):
    """Compress make(width) for each candidate width until it fits."""
    for wdt in widths:
        new = make(wdt)
        if len(new) <= old_size:
            return new
    raise ValueError('replacement does not fit in the original space')


def replacements(buf):
    """Yields (offset in HK_B.BIN, bytes, description) for every image edit."""
    res = texh.resource(buf, HISTORY)
    entries = list(texh.entries(buf, res['GIRT'][0]))
    for idx, text in CHAPTERS.items():
        tile = entries[idx]['tiles'][0]
        old = bytes(buf[tile['data']:tile['data'] + tile['size']])
        px, _ = texh.pixels(old)
        bpp = struct.unpack_from('<H', old, 4)[0]
        new = fit(lambda wdt: texh.compress(label_pixels(text, px, wdt), bpp),
                  len(old), [None] + list(range(120, 40, -6)))
        yield tile['data'], new.ljust(len(old), b'\0'), f'HISTORY chapter label {idx}: {text}'
    names = movelist(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  '..', 'translation', 'movelist.tsv'))
    yield from command_list_replacements(buf, names)
    yield from notices.replacements(buf)
    yield from memcard.replacements(buf)
    yield from ui.replacements(buf)
    yield from staffroll.replacements(buf)
    banks, edits = souther.changes(buf)
    yield from edits
    for bank, new in banks.items():
        yield from texh.rebuild(buf, bank, new, f'SOUTHER bank {bank:#x}')


# --- training mode command lists ---------------------------------------------
#
# Each character's command list is one 640-wide image (GICH resources, a TEXH
# of its own) made of 128x128 tiles in the 32-colour "mode 3" format. Rows
# are 32 px apart starting at y=8: the move name on the left (white, index
# 28), then a separator line, with the button inputs on the right. Follow-up
# moves start with an arrow icon, finishers with a FATAL/DEADLY badge; those
# are kept and only the name after them is redrawn.

COMMAND_LISTS = [            # (TEXH offset in HK_B.BIN, character in movelist.tsv)
    (0x042B000, 'KENSHIRO'), (0x0AD4000, 'RAOH'), (0x10E7800, 'TOKI'),
    (0x1681000, 'JAGI'), (0x1BF3000, 'SHIN'), (0x2107000, 'REI'),
    (0x25EE800, 'JUDA'), (0x261D800, 'JUDA'), (0x2BB8000, 'SOUTHER'),
    (0x3237000, 'HEART'), (0x3693800, 'MAMIYA'),
]
SERIF = fonts.SERIF_BOLD
CL_ROW0, CL_PITCH, CL_BAND = 8, 32, 26
CL_TEXT, CL_BG, CL_AA = 28, 31, ((0.5, 28),)       # crisp white, like the originals
CL_RIGHT = 372                   # names stay left of the separator's step
CL_CAP, CL_BASELINE = 14, 20
CL_KEEP = {28, 31, 2, 5, 19, 25}  # colours that are not part of a badge
# the follow-up arrow, as drawn in the original lists (1 = white pixel)
CL_ARROW = np.array([[int(c) for c in row] for row in (
    '111111100000000000000000', '111111100000000000000000', '000000000000000000000000',
    '111111100000000000000000', '100000100000000000000000', '100000100000000010000000',
    '100000100000000011000000', '100000100000000011100000', '100000011000000010110000',
    '100000000111111110011000', '100000000000000000001100', '010000000000000000000110',
    '010000000000000000000011', '001000000000000000000110', '000110000000000000001100',
    '000001111111111110011000', '000000000000000010110000', '000000000000000011100000',
    '000000000000000011000000', '000000000000000010000000')], dtype=bool)


def _cl_text_start(band):
    """(erase from, name starts at): after any arrow or badge."""
    white = band == CL_TEXT
    ah, aw = CL_ARROW.shape
    end = 0
    for dy in range(0, CL_BAND - ah + 1):
        for x in range(44, 300):
            win = white[dy:dy + ah, x:x + aw]
            if win.shape == CL_ARROW.shape and (win != CL_ARROW).sum() <= 3:
                end = max(end, x + aw)
    badge = ~np.isin(band, list(CL_KEEP))
    cols = np.where(badge[:, :140].any(axis=0))[0]
    if len(cols):
        end = max(end, int(cols.max()) + 1)
    cols = np.where(white[:, max(end, 44):].any(axis=0))[0]
    start = max(end, 44) + (int(cols.min()) if len(cols) else 3)
    return (start if end else 38), start


def _cl_coverage(text, width, ss=4):
    font = fonts.cap_sized(SERIF, CL_CAP, ss)
    hb, bb = font.getbbox('H'), font.getbbox(text)
    im = Image.new('L', (bb[2] - bb[0] + 2 * ss, CL_BAND * ss), 0)
    ImageDraw.Draw(im).text((ss - bb[0], CL_BASELINE * ss - hb[3]), text, font=font, fill=255)
    w = min(width, (im.width + ss - 1) // ss)
    return np.asarray(im.resize((w, CL_BAND), Image.LANCZOS), dtype=float) / 255


# Small Japanese notes beside the inputs: (first column, last column, line 1,
# line 2, alignment). Right-aligned notes may grow left as far as CL_NOTE_MIN.
CL_NOTE_MIN = 400
_NEAR = ('CLOSE', 'RANGE')
_HOUOU = (420, 469, 'IN HOUOU', 'STANCE', 'r')
CL_NOTES = {
    ('KENSHIRO', 15): [(401, 457, 'HIGH/MID', 'INCOMING', 'r'), (511, 565, 'LOW', 'INCOMING', 'r')],
    ('RAOH', 10): [(435, 476, 'DURING', 'RECOVERY', 'r')],
    ('RAOH', 12): [(399, 455, 'HIGH/MID', 'INCOMING', 'r'), (509, 563, 'LOW', 'INCOMING', 'r')],
    ('TOKI', 4): [(434, 470, *_NEAR, 'r')],
    ('TOKI', 16): [(434, 480, 'VS HIGH', 'ATTACK', 'r')],
    ('TOKI', 18): [(434, 480, 'VS LOW', 'ATTACK', 'r')],
    ('JAGI', 15): [(447, 513, 'DOWNED', 'NEAR GUN', 'r')],
    ('JAGI', 16): [(427, 462, 'NEAR', 'SHIN', 'r')],
    ('JAGI', 17): [(427, 463, *_NEAR, 'r')],
    ('SHIN', 13): [(439, 475, *_NEAR, 'r')],
    ('SHIN', 14): [(427, 462, 'DEATH STAR', 'SHINING', 'r')],
    ('REI', 9): [(463, 499, *_NEAR, 'r')],
    ('REI', 10): [(452, 484, 'NEAR WALL', '', 'r')],
    ('JUDA', 11): [(432, 481, 'WHILE', 'GETTING UP', 'r')],
    ('SOUTHER', 7): [_HOUOU], ('SOUTHER', 9): [_HOUOU], ('SOUTHER', 12): [_HOUOU],
    ('SOUTHER', 15): [_HOUOU], ('SOUTHER', 17): [_HOUOU], ('SOUTHER', 20): [_HOUOU],
    ('HEART', 8): [(506, 556, 'USES 1/4', 'AURA', 'l')],
    ('HEART', 16): [(462, 498, *_NEAR, 'r')],
    ('HEART', 19): [(414, 450, *_NEAR, 'r')],
    ('MAMIYA', 22): [(460, 500, 'BOOST', 'READY', 'r')],
}
# Heart's moves that only work while he's in "It hurts!" mode carry a small
# badge before the name.
CL_BADGES = {('HEART', k): (40, 91, 'OWWW!!', 'ONLY') for k in range(11, 17)}


def _cl_note(canvas, y0, x0, x1, l1, l2, align, left_limit=CL_NOTE_MIN):
    region = canvas[y0 + 6:y0 + CL_PITCH, x0:x1 + 1]
    region[region == CL_TEXT] = CL_BG
    for line, dy in (((l1, 9), (l2, 20)) if l2 else ((l1, 12),)):
        g = smallfont.render(line)
        w = g.shape[1]
        if align == 'r':
            gx = x1 + 1 - w
            assert gx >= min(x0, left_limit), line
        else:
            gx = x0
            assert gx + w <= x1 + 1, line
        area = canvas[y0 + dy:y0 + dy + 7, gx:gx + w]
        assert not np.isin(area[g], [c for c in range(32) if c not in (CL_BG, CL_TEXT)]).any(), line
        area[g] = CL_TEXT


def command_list_rows(canvas, names, who=None):
    """Redraw every row's move name (and notes) on a full command list image."""
    for k, name in enumerate(names):
        y0 = CL_ROW0 + CL_PITCH * k
        band = canvas[y0:y0 + CL_BAND]
        badge = CL_BADGES.get((who, k + 1))
        if badge:
            erase, x0 = badge[0], badge[1] + 1
        else:
            erase, x0 = _cl_text_start(band)
        area = band[:, erase:CL_RIGHT + 20]
        area[area == CL_TEXT] = CL_BG
        if badge:
            bx0, bx1, l1, l2 = badge
            _cl_note(canvas, y0 - 6, bx0 + 2, bx1, l1, l2, 'l')
        for note in CL_NOTES.get((who, k + 1), []):
            _cl_note(canvas, y0, *note)
        cov = _cl_coverage(name, CL_RIGHT - x0)
        area = band[:, x0:x0 + cov.shape[1]]
        for t, idx in CL_AA:
            area[(cov >= t) & (area == CL_BG)] = idx
    return canvas


def movelist(path):
    import csv
    names = {}
    with open(path, encoding='utf-8') as f:
        for row in list(csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE))[1:]:
            if row:
                names.setdefault(row[0], []).append(row[2])
    return names


def command_list_replacements(buf, names):
    for texh_off, who in COMMAND_LISTS:
        assert bytes(buf[texh_off:texh_off + 4]) == b'TEXH', hex(texh_off)
        entry = next(texh.entries(buf, texh_off))
        tiles = entry['tiles']
        x_min = min(t['x'] for t in tiles)
        y_min = min(t['y'] for t in tiles)
        W = max(t['x'] + t['w'] for t in tiles) - x_min
        H = max(t['y'] + t['h'] for t in tiles) - y_min
        canvas = np.full((H + y_min, W + x_min), CL_BG, dtype=np.uint8)
        olds = []
        for t in tiles:
            old = bytes(buf[t['data']:t['data'] + t['size']])
            px, _ = texh.pixels(old)
            canvas[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']] = px
            olds.append(old)
        rows = names[who]
        last = CL_ROW0 + CL_PITCH * (len(rows) - 1)
        assert (canvas[last:last + CL_BAND, 44:CL_RIGHT] == CL_TEXT).any(), who
        assert not (canvas[last + CL_PITCH:last + CL_PITCH + CL_BAND, 44:CL_RIGHT] == CL_TEXT).any(), who
        command_list_rows(canvas, rows, who)
        # re-encode every tile and pack them back to back where the old ones
        # were (the new total is smaller; the records get the new offsets)
        datas = []
        for t, old in zip(tiles, olds):
            px = canvas[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']]
            bpp, has_pal = struct.unpack_from('<H', old, 4)[0], struct.unpack_from('<H', old, 2)[0]
            mode3 = struct.unpack_from('<H', old, 14)[0] == 3
            pal = old[16:16 + (4 << bpp)] if has_pal & 1 else b''
            datas.append(texh.compress(px, bpp, pal, mode3=mode3))
        yield from texh.repack(texh_off, tiles, datas, what=f'{who} command list')
