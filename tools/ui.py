"""Small fixes to English UI graphics that are already in the game.

- The gallery viewer's SELECT button (HISTORY resource, entry 9) is a button
  with big SELECT lettering under it, larger than the help text around it.
  It is redrawn as a box in the style of the L1/R1 buttons next to it
  (entry 6), with its colours mapped to the SELECT icon's palette, and
  small SELECT lettering inside.
- PRIVATE VOICE in SOUND SETTINGS is drawn 20 pixels further right than the
  other labels; its tiles are moved left to line it up.
- The copyright notice on the title screen, in English, drawn like the
  original (white anti-aliased text, 1-pixel black outline).
"""
import numpy as np
from PIL import Image, ImageDraw

import fonts
import texh

HISTORY = 0x5EC9000          # HISTORY mode resource (FARC)
SELECT_ICON, L1_ICON = 9, 6
SELECT_PALETTE, L1_PALETTE = 15, 5    # bank palettes the game draws them with
OPTIONS = 0x5E3E000          # OPTION screens (TEXH)
PRIVATE_VOICE = 92
PRIVATE_VOICE_SHIFT = -20

TITLE = 0x5CA3800            # title screen (TEXH)
COPYRIGHT = 5
COPYRIGHT_LINES = [            # the Japanese notice's three lines, in English
    '\u00a9 Buronson & Tetsuo Hara/NSP 1983, Approved No. GA-307',
    '\u00a9 SEGA',
    'Original recording provided by Pony Canyon',
]
COPYRIGHT_SIZE, COPYRIGHT_PITCH = 17, 21    # three lines in one row of tiles
COPYRIGHT_OUTLINE, COPYRIGHT_TOP = 1, 15    # palette: 1 black ... 15 white
SCREEN_WIDTH = 640

# 2-pixel strokes, 9 rows; drawn like the L1/R1 letters: fill 6, outline 4,
# shadow 5, on the box's interior 2
GLYPHS = {
    'S': ['.####.', '##..##', '##....', '##....', '.####.', '....##', '....##', '##..##', '.####.'],
    'E': ['######', '##....', '##....', '##....', '#####.', '##....', '##....', '##....', '######'],
    'L': ['##....', '##....', '##....', '##....', '##....', '##....', '##....', '##....', '######'],
    'C': ['.####.', '##..##', '##....', '##....', '##....', '##....', '##....', '##..##', '.####.'],
    'T': ['######', '..##..', '..##..', '..##..', '..##..', '..##..', '..##..', '..##..', '..##..'],
}
FILL, OUTLINE, SHADOW = 6, 4, 5
BOX_LEFT, BOX_MIDDLE, BOX_RIGHT = slice(0, 9), 8, slice(29, 37)   # columns of the L1 box
BOX_TOP = 24                 # first row of the L1 box in its entry (same in all icons)


def _tile_pixels(buf, entry):
    t = entry['tiles'][0]
    px, _ = texh.pixels(bytes(buf[t['data']:t['data'] + t['size']]))
    return px


def _lettering(text):
    parts = []
    for ch in text:
        parts.append(np.array([[c == '#' for c in row] for row in GLYPHS[ch]]))
        parts.append(np.zeros((9, 1), bool))
    fill = np.hstack(parts[:-1])
    h, w = fill.shape
    out = np.zeros((h + 3, w + 3), np.uint8)
    f = np.zeros(out.shape, bool)
    f[1:h + 1, 1:w + 1] = fill
    o = np.zeros_like(f)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            o |= np.roll(np.roll(f, dy, 0), dx, 1)
    s = np.roll(np.roll(o, 1, 0), 1, 1) & ~o
    out[s], out[o], out[f] = SHADOW, OUTLINE, FILL
    return out


def select_icon(l1, orig, tile, remap):
    """Index image for the SELECT tile: an L1-style box, centred where the
    old icon was, at the same height as the L1/R1 boxes. `remap` turns the
    L1 icon's palette indices into the SELECT icon's."""
    ys, xs = np.nonzero(l1)
    box = l1[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    letters = _lettering('SELECT')
    middle = letters.shape[1] + 6 - (BOX_LEFT.stop + (BOX_RIGHT.stop - BOX_RIGHT.start))
    box = np.hstack([box[:, BOX_LEFT], np.repeat(box[:, BOX_MIDDLE:BOX_MIDDLE + 1], middle, axis=1),
                     box[:, BOX_RIGHT]])
    y0, x0 = (box.shape[0] - letters.shape[0]) // 2, (box.shape[1] - letters.shape[1]) // 2
    area = box[y0:y0 + letters.shape[0], x0:x0 + letters.shape[1]]
    area[letters > 0] = letters[letters > 0]
    oy, ox = np.nonzero(orig)
    centre = (ox.min() + ox.max() + 1) // 2 + tile['x']
    left, top = centre - box.shape[1] // 2 - tile['x'], BOX_TOP - tile['y']
    px = np.zeros(orig.shape, np.uint8)
    px[top:top + box.shape[0], left:left + box.shape[1]] = remap[box]
    return px


def _remap(src, dst):
    """For each colour of palette src, the index of the closest in dst
    (index 0, see-through, stays 0)."""
    out = np.zeros(len(src), np.uint8)
    for i in range(1, len(src)):
        d = np.abs(dst[1:, :3].astype(int) - src[i, :3].astype(int)).sum(axis=1)
        out[i] = int(np.argmin(d)) + 1
    return out


def replacements(buf):
    res = texh.resource(buf, HISTORY)
    entries = list(texh.entries(buf, res['GIRT'][0]))
    pals = texh.palettes(buf, res['GIRP'][0])
    tile = entries[SELECT_ICON]['tiles'][0]
    px = select_icon(_tile_pixels(buf, entries[L1_ICON]), _tile_pixels(buf, entries[SELECT_ICON]), tile,
                     _remap(pals[L1_PALETTE], pals[SELECT_PALETTE]))
    new = texh.compress(px, 4)
    assert len(new) <= tile['size']
    yield tile['data'], new.ljust(tile['size'], b'\0'), 'gallery SELECT button'

    entry = list(texh.entries(buf, OPTIONS))[PRIVATE_VOICE]
    for t in entry['tiles']:
        x = t['x'] + PRIVATE_VOICE_SHIFT
        yield t['record'] + 0x18, np.array([x, t['y'], x + t['w'], t['y'] + t['h']], '<i2').tobytes(), \
            'PRIVATE VOICE position'

    yield from copyright_replacements(buf)


def copyright_pixels(orig_shape, left, top):
    """Index image of the English notice, lines starting at (left, top)."""
    ss = 4
    font = fonts.load(fonts.SANS_REGULAR, COPYRIGHT_SIZE * ss)
    h, w = orig_shape
    im = Image.new('L', (w * ss, h * ss), 0)
    d = ImageDraw.Draw(im)
    asc = font.getbbox('H')[1]
    for k, line in enumerate(COPYRIGHT_LINES):
        d.text((left * ss, (top + COPYRIGHT_PITCH * k) * ss - asc), line, font=font, fill=255)
    cov = np.asarray(im.resize((w, h), Image.BOX), float) / 255
    fill = cov > 0.02
    ring = np.zeros_like(fill)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ring |= np.roll(np.roll(fill, dy, 0), dx, 1)
    px = np.where(ring, COPYRIGHT_OUTLINE, 0).astype(np.uint8)
    levels = COPYRIGHT_OUTLINE + np.round(cov * (COPYRIGHT_TOP - COPYRIGHT_OUTLINE)).astype(int)
    px[fill] = np.maximum(levels[fill], COPYRIGHT_OUTLINE + 1)
    return px


def copyright_replacements(buf):
    entry = list(texh.entries(buf, TITLE))[COPYRIGHT]
    tiles = entry['tiles']
    tw, th = tiles[0]['w'], tiles[0]['h']
    W, H = SCREEN_WIDTH, max(t['y'] + t['h'] for t in tiles) + th
    orig = np.zeros((H, W), np.uint8)
    for t in tiles:
        px, _ = texh.pixels(bytes(buf[t['data']:t['data'] + t['size']]))
        orig[t['y']:t['y'] + th, t['x']:t['x'] + tw] = px
    ys, xs = np.nonzero(orig)
    # the first line's capitals start where the Japanese line's ink starts
    px = copyright_pixels(orig.shape, int(xs.min()) + 1, int(ys.min()) + 2)
    assert not px[:, -8:].any() and not px[-th:].any(), 'copyright notice too long'
    cells = texh.cover(px > 0, tw, th, len(tiles))
    assert cells, 'copyright notice needs more tiles'
    rects = [(x, y, x + tw, y + th) for x, y in cells]
    budget = sum(t['size'] for t in tiles)
    # fewer grey levels if the full anti-aliasing doesn't fit the space
    for levels in (None, (4, 8, 12, 15), (5, 10, 15), (8, 15)):
        q = px.copy()
        if levels:
            lv = np.array(levels)
            m = q > COPYRIGHT_OUTLINE
            q[m] = lv[np.argmin(np.abs(q[m][:, None].astype(int) - lv[None, :]), axis=1)]
        datas = [texh.compress(q[y:y + th, x:x + tw], 4) for x, y in cells]
        if sum(map(len, datas)) <= budget:
            break
    yield from texh.repack(TITLE, tiles, datas, rects, what='title copyright')
