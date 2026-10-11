"""English versions of the HISTORY unlock notices.

When the HISTORY timeline reaches 50% (arcade staff credits) and 100% (Ken-Oh
playable), the game shows a gold banner (entries 140 and 143 of the HISTORY
resource) and then a framed notice (139 and 141).

The notices are 576x448 pictures in 64x64 tiles, 8 bits per pixel, each tile
with its own 256-colour palette. Both share the same frame and stone
background, so the Japanese text of one is erased with the clean background
of the other where possible; where both have text the background is
rebuilt from nearby blocks of the same stone. The English is then drawn in
the original style (white with a soft glow; the title gold with a dark
shadow), the changed tiles get new palettes, and the tiles are packed back
into the original space. Nothing from the game is stored here: everything
is computed from the disc at build time.
"""
import struct

import numpy as np
from PIL import Image, ImageDraw

import fonts
import texh

HISTORY = 0x5EC9000      # HISTORY mode screen resource (FARC offset in HK_B.BIN)

NOTICES = {
    139: {   # アーケード版スタッフロール鑑賞可能！
        'title': 'ARCADE STAFF CREDITS UNLOCKED!',
        'lines': [
            'Congratulations!',
            'You have completed 50% of the HISTORY mode timeline.',
            "You can now view the arcade version's staff credits.",
            'How to View',
            '1. Select “HISTORY” from the main menu.',
            '2. Move the cursor to the very bottom of the timeline.',
            '3. Select “Arcade Version Staff Credits” on the timeline.',
            "4. The arcade version's staff credits will play.",
        ],
    },
    141: {   # 『拳王』利用可能！！
        'title': 'KEN-OH UNLOCKED!!',
        'lines': [
            'Congratulations!!',
            'You have completed 100% of the HISTORY mode timeline.',
            'Ken-Oh is now available as a playable character.',
            'How to Play as Ken-Oh',
            '1. On the character select screen, move the cursor to “Raoh”.',
            '2. Press the START button.',
            '3. You will play as Ken-Oh.',
        ],
    },
}
HEADING_LINE = 3             # the larger "How to ..." line
OTHER = {139: 141, 141: 139}

BANNERS = {140: '50% COMPLETE', 143: 'KEN-OH DESCENDS'}   # 50%達成, 拳王降臨

TITLE_CAP, BODY_CAP, HEADING_CAP = 16, 10, 14
TITLE_CENTRE, TITLE_TOP = 282, 31
MAX_WIDTH = {'title': 430, 'line': 440}
TITLE_ROWS, BODY_ROWS = (20, 59), (72, 351)     # stone areas above/below the divider
BODY_X, TITLE_X = (48, 526), (62, 522)
DARK_STEPS = (8, 10, 12, 14, 16)             # see _pack_notice

# 8bpp palettes are stored in the GS's CSM1 order: entries 8-15 and 16-23 of
# every 32 are swapped. The permutation is its own inverse.
_I = np.arange(256)
CSM1 = (_I & ~0x18) | ((_I & 0x08) << 1) | ((_I & 0x10) >> 1)


# --- reading -----------------------------------------------------------------

def _canvas(buf, entry):
    """Raw RGBA (alpha 0..0x80) of an 8bpp entry, in tile coordinates."""
    tiles = entry['tiles']
    W = max(t['x'] + t['w'] for t in tiles)
    H = max(t['y'] + t['h'] for t in tiles)
    can = np.zeros((H, W, 4), np.uint8)
    for t in tiles:
        tile = bytes(buf[t['data']:t['data'] + t['size']])
        px, _ = texh.pixels(tile)
        pal = np.frombuffer(tile[16:16 + 1024], np.uint8).reshape(256, 4)[CSM1]
        can[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']] = pal[px]
    return can


def _text_boxes(can):
    """[(kind, x0, y0, x1, y1)]: the title, then each line of text, with a
    margin for the glow/shadow."""
    rgb = can[..., :3].astype(int)
    gold = (rgb[..., 0] > 150) & (rgb[..., 2] < 120) & (rgb[..., 0] - rgb[..., 2] > 80)
    xs = np.where(gold[15:62, 55:530].any(axis=0))[0] + 55
    boxes = [('title', int(xs.min()) - 7, 20, int(xs.max()) + 7, 58)]
    bright = rgb.mean(axis=2) > 150
    groups = []
    for r in np.where(bright[75:350, 60:530].any(axis=1))[0] + 75:
        if groups and r - groups[-1][1] <= 2:
            groups[-1][1] = r
        else:
            groups.append([r, r])
    for g0, g1 in groups:
        if g1 - g0 >= 5:       # skip the 1-pixel divider lines
            cols = np.where(bright[g0:g1 + 1, 60:530].any(axis=0))[0] + 60
            boxes.append(('line', int(cols.min()) - 7, int(g0) - 7, int(cols.max()) + 7, int(g1) + 7))
    return boxes


def _mask(shape, boxes):
    m = np.zeros(shape[:2], bool)
    for _, x0, y0, x1, y1 in boxes:
        m[y0:y1 + 1, x0:x1 + 1] = True
    return m


# --- erasing the Japanese ----------------------------------------------------

def _blur1d(a, s, axis):
    r = int(3 * s)
    k = np.exp(-np.arange(-r, r + 1) ** 2 / (2 * s * s))
    k /= k.sum()
    a = np.moveaxis(a, axis, 0)
    out = np.zeros_like(a)
    n = a.shape[0]
    for i, w in enumerate(k):
        d = i - r
        if d >= 0:
            out[:n - d] += w * a[d:]
        else:
            out[-d:] += w * a[:n + d]
    return np.moveaxis(out, 0, axis)


def _blur(a, s):
    return _blur1d(_blur1d(np.asarray(a, float), s, 0), s, 1)


def _lowpass(img, known, sigmas, axes=(0, 1)):
    """Smooth brightness of `img` from the `known` pixels only, reaching
    into the unknown ones with ever wider filters."""
    out = np.zeros(img.shape, float)
    done = np.zeros(known.shape, bool)
    for s in sigmas:
        num, den = img * known[..., None], known.astype(float)
        for ax in axes:
            num, den = _blur1d(num, s, ax), _blur1d(den, s, ax)
        ok = (den > 0.2) & ~done
        out[ok] = num[ok] / den[ok][..., None]
        done |= ok
    return out


def erase_text(can, other, seed=7):
    """Copy of `can` with its text replaced by background. Returns it and
    the text boxes."""
    boxes, oboxes = _text_boxes(can), _text_boxes(other)
    mine, theirs = _mask(can.shape, boxes), _mask(can.shape, oboxes)
    clean = can.copy()
    take = mine & ~theirs
    clean[take] = other[take]           # identical background, no text there
    hole = mine & theirs
    known = ~hole & (clean[..., 3] > 0)
    rgb = clean[..., :3].astype(float)

    # Rebuild the rest from 16x16 blocks of stone taken nearby (same rows for
    # the title band), choosing blocks of similar brightness, with the
    # difference in smooth brightness corrected, overlapping by 4 pixels.
    t0, t1 = TITLE_ROWS
    b0, b1 = BODY_ROWS
    low = np.zeros(rgb.shape)
    kt, kb = known.copy(), known.copy()
    kt[:, :TITLE_X[0]] = kt[:, TITLE_X[1]:] = False
    kb[:, :BODY_X[0]] = kb[:, BODY_X[1]:] = False
    low[t0:t1] = _lowpass(rgb[t0:t1], kt[t0:t1], (30, 60, 120), axes=(1,))
    low[b0:b1] = _lowpass(rgb[b0:b1], kb[b0:b1], (4, 8, 16, 32, 64))
    rng = np.random.default_rng(seed)
    B, S = 16, 12
    ramp = np.minimum(1, np.minimum(np.arange(B) + 1, B - np.arange(B)) / 4.0)
    win = np.outer(ramp, ramp)
    num = np.zeros(rgb.shape)
    den = np.zeros(rgb.shape[:2])
    ys, xs = np.nonzero(hole)
    starts = {((y // S + k) * S, (x // S + j) * S) for y, x in zip(ys, xs)
              for k in (-1, 0) for j in (-1, 0)}
    for by, bx in sorted(starts):
        title = by < t1 - 4
        if title:
            by = min(max(by, t0), t1 - B)
        want = low[by:by + B, bx:bx + B].mean()
        best = None
        for _ in range(4000):
            if title:
                sy, sx = by, bx + int(rng.integers(-300, 301))
                if sx < TITLE_X[0] or sx + B > TITLE_X[1]:
                    continue
            else:
                sy, sx = by + int(rng.integers(-120, 121)), bx + int(rng.integers(-120, 121))
                if sy < b0 or sy + B > b1 or sx < BODY_X[0] or sx + B > BODY_X[1]:
                    continue
            if not known[sy:sy + B, sx:sx + B].all():
                continue
            diff = abs(low[sy:sy + B, sx:sx + B].mean() - want)
            if best is None or diff < best[0]:
                best = (diff, sy, sx)
            if diff < 1.5:
                break
        assert best, (by, bx)
        _, sy, sx = best
        block = rgb[sy:sy + B, sx:sx + B] - low[sy:sy + B, sx:sx + B] + low[by:by + B, bx:bx + B]
        num[by:by + B, bx:bx + B] += win[..., None] * block
        den[by:by + B, bx:bx + B] += win
    assert (den[hole] > 0).all()
    rgb[hole] = num[hole] / den[hole][:, None]
    clean[..., :3] = np.clip(np.round(rgb), 0, 255).astype(np.uint8)
    return clean, boxes


# --- drawing the English ---------------------------------------------------

def _coverage(text, path, cap, max_width, ss=4):
    """Anti-aliased coverage of `text`, cap height `cap`, capitals' top on
    row 4, squeezed to at most max_width columns."""
    font = fonts.cap_sized(path, cap, ss)
    hb, bb = font.getbbox('H'), font.getbbox(text)
    im = Image.new('L', (bb[2] - bb[0] + 4 * ss, (2 * cap + 8) * ss), 0)
    ImageDraw.Draw(im).text((2 * ss - bb[0], 4 * ss - hb[1]), text, font=font, fill=255)
    cov = np.asarray(im.resize(((im.width + ss - 1) // ss, im.height // ss), Image.BOX), float) / 255
    cols = np.where(cov.max(axis=0) > 0.02)[0]
    cov = cov[:, cols.min():cols.max() + 1]
    if cov.shape[1] > max_width:
        im = Image.fromarray(np.round(cov * 255).astype(np.uint8))
        cov = np.asarray(im.resize((max_width, cov.shape[0]), Image.LANCZOS), float) / 255
    return cov


def _place(layer, cov, centre, cap_top):
    h, w = cov.shape
    x0, y0 = int(round(centre - w / 2)), cap_top - 4
    np.maximum(layer[y0:y0 + h, x0:x0 + w], cov, out=layer[y0:y0 + h, x0:x0 + w])


def draw_notice(clean, boxes, texts):
    """The notice with the English drawn over the cleaned background, laid
    out on the original lines (centred like them)."""
    H, W = clean.shape[:2]
    rgb = clean[..., :3].astype(float)
    lines = [b for b in boxes if b[0] == 'line']
    assert len(lines) == len(texts['lines']), (len(lines), len(texts['lines']))

    # title: gold, darker towards the bottom, on a soft dark shadow
    cov = np.zeros((H, W))
    _place(cov, _coverage(texts['title'], fonts.SERIF_BOLD, TITLE_CAP, MAX_WIDTH['title']),
           TITLE_CENTRE, TITLE_TOP)
    shadow = np.minimum(_blur(cov, 1.3) * 3.0, 0.92)[..., None]
    rgb = rgb * (1 - shadow) + np.array([12, 8, 4]) * shadow
    t = np.clip((np.arange(H) - TITLE_TOP) / TITLE_CAP, 0, 1)[:, None, None]
    gold = np.array([248, 222, 118]) * (1 - t) + np.array([214, 180, 96]) * t
    rgb = rgb * (1 - cov[..., None]) + gold * cov[..., None]

    # body: white with a grey glow
    cov = np.zeros((H, W))
    for k, (text, (_, x0, y0, x1, y1)) in enumerate(zip(texts['lines'], lines)):
        top = y0 + 7                     # first row of the original text
        if k == HEADING_LINE:
            c, cap_top = _coverage(text, fonts.SERIF_SEMIBOLD, HEADING_CAP, MAX_WIDTH['line']), top + 3
        else:
            c, cap_top = _coverage(text, fonts.SERIF_SEMIBOLD, BODY_CAP, MAX_WIDTH['line']), top + 1
        _place(cov, c, (x0 + x1) / 2, cap_top)
    glow = np.minimum(_blur(cov, 2.0) * 2.8, 0.5)[..., None]
    rgb = np.maximum(rgb, 255 * glow)
    rgb = rgb * (1 - cov[..., None]) + 247 * cov[..., None]

    out = clean.copy()
    out[..., :3] = np.clip(np.round(rgb), 0, 255).astype(np.uint8)
    return out


# --- writing it back -------------------------------------------------------

def _quantize(tile):
    """(indices, palette rows) for a (64, 64, 4) raw RGBA tile, most used
    colour first (runs of index 0 compress best)."""
    flat = tile.reshape(-1, 4)
    keys = flat.astype(np.uint32) << np.array([0, 8, 16, 24], np.uint32)
    keys = keys.sum(axis=1, dtype=np.uint32)
    uniq, inv = np.unique(keys, return_inverse=True)
    if len(uniq) <= 256:
        pal = np.zeros((256, 4), np.uint8)
        pal[:len(uniq)] = np.stack([(uniq >> s) & 255 for s in (0, 8, 16, 24)], axis=1)
        idx = inv.reshape(-1)
    else:
        opaque = flat[:, 3] > 0
        clear = 0 if opaque.all() else 1
        im = Image.fromarray(np.ascontiguousarray(flat[:, :3]).reshape(tile.shape[0], tile.shape[1], 3))
        q = im.quantize(colors=256 - clear, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        rows = np.array(q.getpalette()[:3 * (256 - clear)], np.uint8).reshape(-1, 3)
        pal = np.zeros((256, 4), np.uint8)
        pal[clear:clear + len(rows), :3] = rows
        pal[clear:, 3] = 0x80
        idx = np.asarray(q).reshape(-1).astype(int) + clear
        if clear:
            pal[0] = flat[~opaque][0]
            idx[~opaque] = 0
    order = np.argsort(-np.bincount(idx, minlength=256), kind='stable')
    rank = np.empty(256, int)
    rank[order] = np.arange(256)
    return rank[idx].reshape(tile.shape[:2]).astype(np.uint8), pal[order]


def _encode(tile):
    idx, pal = _quantize(tile)
    return texh.compress(idx, 8, pal[CSM1].tobytes())


def _pack_notice(buf, entry, orig, new):
    """New data for every tile of the entry. Tiles that didn't change keep
    their bytes. If the result is bigger than the original, the darkest
    colours of the changed tiles (all channels <= n) are made black, which
    can't be told apart on screen and compresses much better."""
    budget = sum(t['size'] for t in entry['tiles'])
    for dark in DARK_STEPS:
        datas = []
        for t in entry['tiles']:
            sl = (slice(t['y'], t['y'] + t['h']), slice(t['x'], t['x'] + t['w']))
            if (new[sl] == orig[sl]).all():
                datas.append(bytes(buf[t['data']:t['data'] + t['size']]))
                continue
            tile = new[sl].copy()
            black = (tile[..., :3].max(axis=2) <= dark) & (tile[..., 3] > 0)
            tile[black, :3] = 0
            datas.append(_encode(tile))
        if sum(map(len, datas)) <= budget:
            return datas
    raise ValueError(f'notice {entry["index"]} does not fit')


# --- banners ---------------------------------------------------------------
#
# 4bpp, three 128x64 tiles sharing one palette: 0 clear, 9 black, f white,
# 8/6/3/1 greys, and the fill e d c b a 7 5 4 2 from yellow to dark red.

BANNER_CAP = 30
# fill colours by height in the letter (0 = top): pairs alternate in a
# checkerboard, like the dithered metal of the originals
BANNER_FILL = [(0.00, (0xE,)), (0.36, (0xE, 0xD)), (0.39, (0xC, 0xB)), (0.42, (0xA, 7)),
               (0.45, (7,)), (0.49, (7, 4)), (0.53, (0xA, 7)), (0.58, (7, 4)), (0.62, (4, 2)),
               (0.66, (2,)), (0.74, (2, 4)), (0.79, (0xA, 0xE)), (0.82, (0xE,)),
               (0.88, (0xA, 7)), (0.93, (7, 5))]
BANNER_TRACK = 3          # extra pixels between letters
BANNER_RING = 7.5         # outline width around the fill


def _banner_mask(text, cap, width, ss=4):
    font = fonts.cap_sized(fonts.SERIF_BLACK, cap, ss)
    hb = font.getbbox('H')
    xs, x = [], 0
    for ch in text:
        xs.append(x)
        x += font.getlength(ch) + BANNER_TRACK * ss
    im = Image.new('L', (int(x) + 8 * ss, (cap + 12) * ss), 0)
    d = ImageDraw.Draw(im)
    for ch, x0 in zip(text, xs):
        d.text((x0 + 2 * ss, 6 * ss - hb[1]), ch, font=font, fill=255)
    a = np.asarray(im) > 127
    cols = np.where(a.any(axis=0))[0]
    a = a[:, cols.min():cols.max() + 1]
    w = min(width, a.shape[1] // ss)
    im = Image.fromarray(a.astype(np.uint8) * 255).resize((w, im.height // ss), Image.BOX)
    return np.asarray(im) >= 128          # capitals' top on row 6


def _distance(fill, reach=8):
    """Distance from each pixel to the fill, and whether the nearest fill
    pixel is below it (that side of the outline is lit)."""
    h, w = fill.shape
    dist = np.full((h, w), 99.0)
    below = np.zeros((h, w), bool)
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            dd = (dy * dy + dx * dx) ** 0.5
            if dd > reach:
                continue
            shifted = np.zeros_like(fill)
            ys0, ys1 = max(0, -dy), min(h, h - dy)
            xs0, xs1 = max(0, -dx), min(w, w - dx)
            shifted[ys0:ys1, xs0:xs1] = fill[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx]
            closer = shifted & (dd < dist)
            dist[closer] = dd
            below[closer] = dy > 0
    return dist, below


def banner_pixels(text, height, width, centre, middle):
    """Index image (height x width) with `text` centred on (centre, middle)."""
    margin = int(np.ceil(BANNER_RING)) + 1
    limit = int(2 * min(centre, width - centre)) - 2 * margin
    m = _banner_mask(text, BANNER_CAP, limit)
    fill = np.zeros((height, width), bool)
    y0 = int(round(middle - BANNER_CAP / 2)) - 6
    x0 = int(round(centre - m.shape[1] / 2))
    fill[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
    dist, below = _distance(fill)
    ring = dist > 0
    checker = np.indices(fill.shape).sum(axis=0) % 2 == 1
    out = np.zeros(fill.shape, np.uint8)
    out[ring & (dist <= BANNER_RING)] = 9                   # black outline
    grey = ring & (dist <= 5.6)
    out[grey & below] = 6                                   # lit side
    out[grey & ~below] = 1
    outer = grey & (dist > 4.4)
    out[outer & below] = 3
    out[outer & ~below & checker] = 3
    out[ring & (dist <= 3.3)] = 0xF                         # white edge
    out[ring & (dist <= 2.2)] = 9                           # black inner line
    rows = np.where(fill.any(axis=1))[0]
    top, bottom = rows.min(), rows.max()
    for y in rows:
        t = (y - top) / max(1, bottom - top)
        pair = [c for s, c in BANNER_FILL if s <= t + 1e-9][-1]
        row = np.array([pair[(x + y) % len(pair)] for x in range(width)], np.uint8)
        out[y, fill[y]] = row[fill[y]]
    return out


def _banner(buf, entry, text):
    """Tile datas for an English banner. The tiles are moved to cover the
    whole width (the originals leave columns free on one side)."""
    tiles = entry['tiles']
    width = entry['w']
    y = tiles[0]['y']
    th, tw = tiles[0]['h'], tiles[0]['w']
    assert all(t['y'] == y and t['h'] == th and t['w'] == tw for t in tiles)
    span = tw * len(tiles)
    left = (width - span) // 2
    img = banner_pixels(text, th, span, width / 2 - left, th / 2 - 1)
    datas, rects = [], []
    for k, t in enumerate(tiles):
        old = bytes(buf[t['data']:t['data'] + t['size']])
        pal = old[16:16 + 64]
        assert struct.unpack_from('<3H', old, 2) == (1, 4, tw)
        datas.append(texh.compress(img[:, k * tw:(k + 1) * tw], 4, pal))
        x0 = left + k * tw
        rects.append((x0, y, x0 + tw, y + th))
    return datas, rects


# --- all of it ---------------------------------------------------------------

def replacements(buf):
    res = texh.resource(buf, HISTORY)
    texh_off = res['GIRT'][0]
    entries = list(texh.entries(buf, texh_off))
    for idx, text in BANNERS.items():
        datas, rects = _banner(buf, entries[idx], text)
        yield from texh.repack(texh_off, entries[idx]['tiles'], datas, rects, f'banner {idx}: {text}')
    canvases = {idx: _canvas(buf, entries[idx]) for idx in NOTICES}
    for idx, texts in NOTICES.items():
        clean, boxes = erase_text(canvases[idx], canvases[OTHER[idx]])
        new = draw_notice(clean, boxes, texts)
        datas = _pack_notice(buf, entries[idx], canvases[idx], new)
        yield from texh.repack(texh_off, entries[idx]['tiles'], datas, None, f'notice {idx}')
