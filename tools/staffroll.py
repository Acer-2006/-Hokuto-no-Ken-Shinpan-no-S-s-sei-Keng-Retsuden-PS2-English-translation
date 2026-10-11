"""The staff roll in English.

The staff roll (TEXH at 0x6212000) is 65 pictures of 640x256: white text
with a black outline (bank palette 7), English headings over names written
in Japanese. Each picture is cut into its lines of text (rows of ink, split
where there is a wide gap, so two columns give two lines); the lines listed
in translation/staffroll.tsv are erased and drawn again in English, centred
where the Japanese was:

- names in a serif like the English already on the pages (DANGUN PICTURES,
  All Sammy Staff), at the same cap height
- headings ("head") in the condensed capitals of the other headings, between
  the heading's own rules
- the game's title ("title", "subtitle") larger, like the original
- the copyright notice ("notice") in the headings' capitals, left-aligned

Only the tiles that hold text exist, so they are laid out again over the
new text (texh.cover) and the bank is packed again. The English is wider
than the Japanese, so where a page's 64x64 tiles can't cover it, the page
gets the same number of bigger tiles (128x64 or 128x128, sizes the bank
already uses for other pictures).
"""
import os

import numpy as np
from PIL import Image, ImageDraw

import fonts
import texh

BANK = 0x6212000             # staff roll pictures (TEXH)
PAGES = 65
GAP = 28                     # a wider gap between ink splits a row into two lines
TALL = 40                    # a taller row is two lines whose outlines touch
RULE_GAP = 8                 # gaps between a heading's rules and its words are wider

OUTLINE = 6                  # palette 7: 6 black, 1-5 and 7-15 greys up to white
RAMP = np.array([OUTLINE, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15])
LEVELS = np.array([0, 3, 6, 9, 12, 14])   # the steps of RAMP used (fewer greys pack smaller)
DISC = [(dy, dx) for dy in range(-2, 3) for dx in range(-2, 3) if abs(dy) + abs(dx) < 4]

STYLES = {   # font, cap height, horizontal scale, letter spacing, extra word spacing, gamma
    'name': (fonts.SERIF_TEXT, 15, 1.0, 1, 0, 1.8),
    'head': (fonts.SERIF_TEXT, 19, 0.65, 1, 6, 1.3),
    'title': (fonts.SERIF_TEXT, 22, 1.0, 1, 0, 1.4),
    'subtitle': (fonts.SERIF_TEXT, 17, 1.0, 1, 0, 1.6),
    'notice': (fonts.SERIF_TEXT, 17, 0.68, 1, 4, 1.3),     # left-aligned
}
MARGIN = 16                  # space kept between a new line and the other text in its row
TILE_SIZES = [(64, 64), (128, 64), (128, 128)]


def load(path=None):
    """{(page, line): (English, style, shift)} from staffroll.tsv. The Line
    column may end in +N/-N to move that line N pixels right/left."""
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'translation', 'staffroll.tsv')
    out = {}
    with open(path, encoding='utf-8') as f:
        next(f)
        for row in f:
            row = row.rstrip('\n')
            if not row or row.startswith('#'):
                continue
            page, line, style, text = row.split('\t')[:4]
            shift = 0
            for sign in '+-':
                if sign in line:
                    line, n = line.split(sign)
                    shift = int(n) * (1 if sign == '+' else -1)
            out[int(page), int(line)] = (text, style or 'name', shift)
    return out


def _runs(mask, gap):
    """[start, end] of the runs of True in a 1-D mask, joined over gaps of
    fewer than `gap` False values."""
    idx = np.nonzero(mask)[0]
    runs = [[idx[0], idx[0]]]
    for i in idx[1:]:
        if i > runs[-1][1] + gap:
            runs.append([i, i])
        runs[-1][1] = i
    return [(int(a), int(b)) for a, b in runs]


def lines(canvas):
    """Boxes (x0, y0, x1, y1), inclusive, of the lines of text on a page,
    row by row from the top, left to right."""
    ink = canvas > 0
    rows = []
    for y0, y1 in _runs(ink.any(axis=1), 1):
        if y1 - y0 + 1 > TALL:           # split at the emptiest row
            counts = ink[y0 + 8:y1 - 7].sum(axis=1)
            cut = y0 + 8 + int(np.argmin(counts))
            rows += [(y0, cut - 1), (cut, y1)]
        else:
            rows.append((y0, y1))
    out = []
    for y0, y1 in rows:
        for x0, x1 in _runs(ink[y0:y1 + 1].any(axis=0), GAP):
            ys = np.nonzero(ink[y0:y1 + 1, x0:x1 + 1].any(axis=1))[0]
            out.append((x0, y0 + int(ys[0]), x1, y0 + int(ys[-1])))
    return out


def _coverage(text, style):
    """Anti-aliased coverage of `text` and the row of its capitals' top,
    trimmed to the ink horizontally."""
    path, cap, scale, tracking, word, _ = STYLES[style]
    ss = 4
    font = fonts.cap_sized(path, cap, ss)
    top = font.getbbox('H')[1]
    l = min(0, font.getbbox(text)[0])
    w = int(font.getlength(text)) + (tracking * len(text) + word * text.count(' ')) * ss + 8 * ss - l
    h = font.getbbox(text)[3] + 8 * ss
    im = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(im)
    x = 4 * ss - l
    for ch in text:              # letter by letter, for the extra spacing
        d.text((x, 4 * ss), ch, font=font, fill=255)
        x += font.getlength(ch) + (tracking + (word if ch == ' ' else 0)) * ss
    W = int(np.ceil(w * scale / ss))
    H = int(np.ceil(h / ss))
    im = im.resize((W * ss, H * ss), Image.LANCZOS).resize((W, H), Image.BOX)
    cov = np.asarray(im, float) / 255
    cols = np.nonzero(cov.max(axis=0) > 0.02)[0]
    return cov[:, cols[0]:cols[-1] + 1], 4 + top / ss


def _outlined(cov, gamma=1.0):
    """Palette indices for coverage: the grey ramp (darkened by `gamma` to
    thin the strokes), with a black outline two pixels wide around it."""
    h, w = cov.shape
    fill = np.zeros((h + 4, w + 4), bool)
    fill[2:-2, 2:-2] = cov > 0.02
    ring = np.zeros_like(fill)
    for dy, dx in DISC:
        ring |= np.roll(np.roll(fill, dy, 0), dx, 1)
    out = np.where(ring, OUTLINE, 0).astype(np.uint8)
    level = np.round(cov ** gamma * (len(RAMP) - 1)).astype(int)
    level = LEVELS[np.argmin(np.abs(level[..., None] - LEVELS), axis=-1)]
    inner = out[2:-2, 2:-2]
    inner[cov > 0.02] = RAMP[np.maximum(level[cov > 0.02], 1)]
    return out


def _heading_rules(canvas, box):
    """The rules either side of a heading, as (pixels, gap to the words)."""
    x0, y0, x1, y1 = box
    parts = _runs((canvas[y0:y1 + 1, x0:x1 + 1] > 0).any(axis=0), RULE_GAP)
    (la, lb), (ra, rb) = parts[0], parts[-1]
    left = canvas[y0:y1 + 1, x0 + la:x0 + lb + 1]
    right = canvas[y0:y1 + 1, x0 + ra:x0 + rb + 1]
    return left, parts[1][0] - lb, right, ra - parts[-2][1]


def render(text, style, box, canvas):
    """(pixels, x, y): the new line, placed with its capitals centred on the
    old line's box (headings keep their rules)."""
    x0, y0, x1, y1 = box
    cov, cap_top = _coverage(text, style)
    px = _outlined(cov, STYLES[style][5])
    cap = STYLES[style][1]
    top = int(round((y0 + y1) / 2 - cap / 2 - cap_top - 2))
    if style == 'head':
        left, lgap, right, rgap = _heading_rules(canvas, box)
        # the words' capitals centred on the rules' line
        rule = int(np.argmax(((left > 0) & (left != OUTLINE)).sum(axis=1)))
        ty = int(round(rule - cap / 2 - cap_top - 2))
        t0 = min(0, ty)
        row = np.zeros((max(left.shape[0], ty + px.shape[0]) - t0,
                        left.shape[1] + lgap + px.shape[1] + rgap + right.shape[1]), np.uint8)
        row[-t0:-t0 + left.shape[0], :left.shape[1]] = left
        row[-t0:-t0 + right.shape[0], -right.shape[1]:] = right
        x = left.shape[1] + lgap
        row[ty - t0:ty - t0 + px.shape[0], x:x + px.shape[1]] = px
        px, top = row, y0 + t0
    rows = np.nonzero(px.any(axis=1))[0]
    px, top = px[rows[0]:rows[-1] + 1], top + int(rows[0])
    left = x0 if style == 'notice' else int(round((x0 + x1 + 1) / 2 - px.shape[1] / 2))
    return px, left, top


def page(canvas, boxes, items):
    """The page with the lines in `items` ({line: (text, style, shift)})
    drawn in English."""
    out = canvas.copy()
    for k in items:
        x0, y0, x1, y1 = boxes[k]
        region = out[y0:y1 + 1, x0:x1 + 1]
        region[:] = 0
    drawn = []
    for k, (text, style, shift) in items.items():
        px, x, y = render(text, style, boxes[k], canvas)
        x += shift
        h, w = px.shape
        y = min(y, out.shape[0] - h)     # descenders on the last row
        assert 0 <= x and x + w <= out.shape[1] and 0 <= y and y + h <= out.shape[0], \
            f'line {k} "{text}" is off the page'
        # keep clear of the rest of the row
        for j, (a0, b0, a1, b1) in enumerate(boxes):
            if j != k and j not in items and not (b1 < y or b0 >= y + h):
                assert x + w + MARGIN <= a0 or a1 + MARGIN < x, f'line {k} "{text}" runs into line {j}'
        for j, (a, b, w2, h2) in drawn:
            if not (b + h2 <= y or y + h <= b):
                assert x + w + MARGIN <= a or a + w2 + MARGIN <= x, f'line {k} "{text}" runs into line {j}'
        drawn.append((k, (x, y, w, h)))
        dst = out[y:y + h, x:x + w]
        dst[px > 0] = px[px > 0]
    return out


def pictures(buf, names=None):
    """(entry, original canvas, English canvas) for each page with English."""
    names = load() if names is None else names
    for entry in list(texh.entries(buf, BANK))[:PAGES]:
        items = {line: v for (p, line), v in names.items() if p == entry['index']}
        if not items:
            continue
        canvas = np.zeros((entry['h'], entry['w']), np.uint8)
        for t in entry['tiles']:
            px, _ = texh.pixels(bytes(buf[t['data']:t['data'] + t['size']]))
            canvas[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']] = px[:canvas.shape[0] - t['y'],
                                                                        :canvas.shape[1] - t['x']]
        boxes = lines(canvas)
        assert max(items) < len(boxes), f'staff roll page {entry["index"]} has {len(boxes)} lines'
        yield entry, canvas, page(canvas, boxes, items)


def _layout(canvas, n):
    """Tile size and positions for at most n tiles over the page's ink: the
    game's 64x64 tiles if they are enough, otherwise bigger ones (the same
    bank has 4-bit 128x32 and 128x128 tiles)."""
    for tw, th in TILE_SIZES:
        padded = np.zeros((canvas.shape[0] + th, canvas.shape[1] + tw), np.uint8)
        padded[:canvas.shape[0], :canvas.shape[1]] = canvas
        cells = texh.cover(padded > 0, tw, th, n)
        if cells:
            return tw, th, padded, cells
    return None


def replacements(buf):
    new = {}
    for entry, _, canvas in pictures(buf):
        tiles = entry['tiles']
        layout = _layout(canvas, len(tiles))
        assert layout, f'staff roll page {entry["index"]} needs more than {len(tiles)} tiles'
        tw, th, padded, cells = layout
        new[entry['index']] = [(texh.compress(padded[y:y + th, x:x + tw], 4), (x, y, x + tw, y + th))
                               for x, y in cells]
    yield from texh.rebuild(buf, BANK, new, 'staff roll')
