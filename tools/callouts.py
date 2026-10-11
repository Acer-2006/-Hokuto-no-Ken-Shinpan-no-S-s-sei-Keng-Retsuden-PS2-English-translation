"""English for the Japanese drawn into fight and ending graphics.

- move names that flash up in a fight (Kenshiro's 北斗百裂拳 banner and the
  five 北斗残悔拳 stamps, Toki's 北斗有情断迅拳 and 北斗有情破顔拳)
- Heart's いてえよ～!! and Jagi's "Say my name!" speech
- the ending: Raoh's last words and the two narration cards

Each picture is redrawn from its own colours, in one of three ways:
- flat lettering with an outline (banners, stamps, Jagi): the fill colour of
  every row of the original lettering (most have a vertical gradient) and
  its outline colour and width are measured (Look) and the English drawn
  with them
- shiny letters in a soft glow (Toki's HAGANKEN, Heart; 8-bit, hundreds of
  colours): the letters' colours by depth and row and the glow's by distance
  are measured in RGB (Glow), and the new picture is mapped back to the
  palette
- black brush ink (the ending): drawn anti-aliased, with see-through steps
  of the ink colour added to the palette
The tiles are laid out again over the new text (texh.cover), with as many
tiles as before (the lettering is narrowed until they hold it); the banks
are packed again in images.py.
"""
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import fonts
import texh

GOTHIC, SERIF, SERIF_BOLD, SERIF_BLACK = fonts.SANS_BOLD, fonts.SERIF_SEMIBOLD, fonts.SERIF_BOLD, fonts.SERIF_BLACK
BRUSH = SERIF_BLACK

# (TEXH, entry): list of blocks, each (lines, box or None, font, max cap
# height, style). box (x0, y0, x1, y1) is where the block is centred; None
# means the original lettering's box, 'wide' the picture's width. style
# 'restyle' copies the original's colours, 'glow' its shiny letters and glow
# (see Glow), 'ink' is anti-aliased black (the ending cards). An optional
# dict can follow: min_scale (squeezing allowed), bold (strokes thickened by
# this much of the cap height) and look (another entry to measure the look
# from).
SPECS = {
    # Kenshiro: DEADLY banner, FATAL stamps (one syllable per kanji stamp)
    (0x3E0800, 2): [(['HOKUTO HYAKURETSUKEN'], None, GOTHIC, 70, 'restyle')],
    (0x3B0000, 6): [(['HOKU'], None, GOTHIC, 64, 'restyle', {'min_scale': 0.42})],
    (0x3B0000, 7): [(['TO'], None, GOTHIC, 64, 'restyle', {'min_scale': 0.42})],
    (0x3B0000, 8): [(['ZAN'], None, GOTHIC, 64, 'restyle', {'min_scale': 0.42})],
    (0x3B0000, 9): [(['KAI'], None, GOTHIC, 64, 'restyle', {'min_scale': 0.42})],
    (0x3B0000, 10): [(['KEN'], None, GOTHIC, 64, 'restyle', {'min_scale': 0.42})],
    # Toki: FATAL and DEADLY names
    (0x1093800, 9): [(['HOKUTO UJOU DANJINKEN'], None, GOTHIC, 70, 'restyle')],
    (0x10B5800, 11): [(['HOKUTO UJOU', 'HAGANKEN'], None, SERIF_BOLD, 40, 'glow')],
    # Heart
    (0x31D8000, 0): [(['IT HUUURTS!!'], None, GOTHIC, 66, 'glow', {'bold': 0.03})],
    # Jagi: "Say my name!", the answers (one right, four garbled) and his replies
    (0x15E6800, 2): [(['JAGI'], None, BRUSH, 22, 'restyle')],
    (0x15E6800, 3): [(['JIAGI'], None, BRUSH, 22, 'restyle')],
    (0x15E6800, 4): [(['SHAGI'], None, BRUSH, 22, 'restyle')],
    (0x15E6800, 5): [(['JAJI'], None, BRUSH, 22, 'restyle')],
    (0x15E6800, 6): [(['ZYAGI'], None, BRUSH, 22, 'restyle')],
    (0x15E6800, 7): [(['Go on...', 'say my name!'], 'wide', BRUSH, 20, 'restyle')],
    (0x15E6800, 8): [(['Fool!'], None, BRUSH, 22, 'restyle')],
    (0x15E6800, 9): [(['You idiot!'], 'wide', BRUSH, 22, 'restyle')],
    (0x15E6800, 10): [(['I see!'], 'wide', BRUSH, 22, 'restyle')],
    (0x15E6800, 11): [(["I'll give you", 'one more chance!'], 'wide', BRUSH, 20, 'restyle',
                       {'look': 12})],    # its own outline is too thin to measure
    (0x15E6800, 12): [(['You see the scars', 'on my chest and still',
                        "don't know who I am?"], 'wide', BRUSH, 20, 'restyle')],
    (0x15E6800, 13): [(['There\'s nothing', 'I hate more', 'than a liar!!'], 'wide', BRUSH, 20, 'restyle')],
    (0x15E6800, 14): [(['Whyyyy...!?'], 'wide', BRUSH, 22, 'restyle')],
    # the ending: Raoh's last words, two columns (read right, then left) on
    # either side of him; the English keeps to the sky around him
    (0x377C800, 5): [(['In my', 'life,'], (350, 28, 630, 206), SERIF_BLACK, 40, 'ink'),
                     (['I have', 'no', 'regrets!'], (4, 300, 162, 474), SERIF_BLACK, 40, 'ink',
                      {'min_scale': 0.92})],
    (0x377C800, 7): [(['Long ago,', 'men fought', '. . . . . .'], (470, 44, 632, 300), SERIF, 17, 'ink')],
    (0x377C800, 8): [(['They left this', 'world a moment', 'of peace, and', 'were scattered', 'to heaven and', 'earth.'],
                      (16, 44, 200, 360), SERIF, 17, 'ink')],
}
LINE_GAP = 0.45            # space between lines, in cap heights
MIN_SCALE = 0.62           # letters may be squeezed to this width
MARGIN = 6                 # 'wide' boxes: the entry's width less this


def _entry(buf, bank, index):
    entry = list(texh.entries(buf, bank))[index]
    tiles = entry['tiles']
    W = max(entry['w'], max(t['x'] + t['w'] for t in tiles))
    H = max(entry['h'], max(t['y'] + t['h'] for t in tiles))
    can = np.zeros((H, W), np.uint8)
    pal = raw_pal = None
    for t in tiles:
        raw = bytes(buf[t['data']:t['data'] + t['size']])
        px, p = texh.pixels(raw)
        can[t['y']:t['y'] + px.shape[0], t['x']:t['x'] + px.shape[1]] = px
        has_pal, bpp = struct.unpack_from('<2H', raw, 2)
        assert has_pal & 1, f'{bank:#x}:{index} has no palette of its own'
        pal, raw_pal, depth = p, raw[16:16 + (4 << bpp)], bpp
    return entry, can, pal, raw_pal, depth


def _shift(m, dy, dx):
    out = np.zeros_like(m)
    h, w = m.shape
    out[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = \
        m[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return out


def _erode(m):
    out = m.copy()
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        out &= _shift(m, dy, dx)
    return out


def _bands(mask):
    rows = np.nonzero(mask.any(axis=1))[0]
    bands, start = [], rows[0]
    for a, b in zip(rows, rows[1:]):
        if b > a + 2:
            bands.append((start, a))
            start = b
    bands.append((start, rows[-1]))
    return bands


def _depth(mask, limit=64):
    """How many 4-neighbour erosions each pixel of mask survives (1 = edge)."""
    depth = np.zeros(mask.shape, np.int32)
    cur = mask.copy()
    k = 0
    while cur.any() and k < limit:
        k += 1
        depth[cur] = k
        cur = _erode(cur)
    return depth


def _grow(mask, n):
    out = mask.copy()
    for _ in range(n):
        out = out | _shift(out, 0, 1) | _shift(out, 0, -1) | _shift(out, 1, 0) | _shift(out, -1, 0)
    return out


def _edt(mask):
    """Euclidean distance from every pixel to the nearest pixel of mask."""
    H, W = mask.shape
    big = H + W
    idx = np.arange(H)[:, None].repeat(W, 1)
    above = np.maximum.accumulate(np.where(mask, idx, -big), axis=0)
    below = np.minimum.accumulate(np.where(mask, idx, 3 * big)[::-1], axis=0)[::-1]
    g2 = np.minimum(np.minimum(idx - above, below - idx), big).astype(float) ** 2
    xs = np.arange(W)
    dx2 = (xs[:, None] - xs[None, :]) ** 2
    out = np.empty((H, W))
    for y in range(H):
        out[y] = np.sqrt((g2[y][None, :] + dx2).min(axis=1))
    return out


ROW_BINS = 24


class Look:
    """The original lettering's look, measured from its pixels.

    edge: how many pixels of outline and glow surround the letters' fill
    height: height of the letters' fill (one line)
    colours[d][r]: the most common colour at depth d (1 = outermost pixel,
        edge + 1 = fill) in row band r of a line
    """

    def __init__(self, can, pal):
        ink = pal[can][..., 3] > 0
        depth = _depth(ink)
        top = int(depth.max())
        # the fill's colours: what most of the deepest pixels are
        deep = can[depth >= max(2, int(top * 0.6))]
        vals, counts = np.unique(deep, return_counts=True)
        order = np.argsort(-counts)
        keep = np.cumsum(counts[order]) <= 0.9 * counts.sum()
        keep[0] = True
        fill = set(vals[order][keep].tolist())
        edge = 0
        for d in range(1, top):
            if np.isin(can[depth == d], list(fill)).mean() >= 0.5:
                break
            edge = d
        self.edge = edge
        y0, y1 = max(_bands(depth > edge), key=lambda b: b[1] - b[0])
        self.height = y1 - y0 + 1
        rel = (np.arange(can.shape[0]) - y0) / max(1, y1 - y0)
        band = np.clip(np.round(rel * (ROW_BINS - 1)), -3, ROW_BINS + 2).astype(int)
        self.colours = {}
        for d in range(1, edge + 2):
            sel = (depth == d) if d <= edge else (depth > edge)
            table = []
            for r in range(-3, ROW_BINS + 3):
                v = can[sel & (band[:, None] == r)]
                table.append(int(np.bincount(v).argmax()) if len(v) else None)
            fallback = int(np.bincount(can[sel]).argmax()) if sel.any() else 0
            for k in range(len(table)):
                if table[k] is None:
                    near = [table[j] for j in sorted(range(len(table)), key=lambda j: abs(j - k))
                            if table[j] is not None]
                    table[k] = near[0] if near else fallback
            self.colours[d] = np.array(table)

    def edge_for(self, cap):
        """Outline and glow width for letters `cap` pixels tall."""
        if not self.edge:
            return 0
        return max(1, int(round(self.edge * min(1.0, cap / self.height))))


GLOW_STEP = 30             # colour step that ends the glow (the letters' edge)
GLOW_MIN = 0.8             # the glow shrinks with the letters, to this much at most


class Glow:
    """Shiny letters in a soft glow (8-bit pictures with hundreds of colours).

    The glow is smooth, the letters' edge a sharp step: what can be reached
    from outside the picture without crossing a step of GLOW_STEP is glow,
    the rest letters. Measured, in RGB:
    inner[d][r]: mean colour d pixels inside the letters, in row band r
    outer[d]: mean colour d pixels outside the letters
    reach: how far outside the letters the picture's opaque blob goes
    """

    def __init__(self, can, pal):
        rgb = pal[can][..., :3].astype(float)
        ink = pal[can][..., 3] > 0
        rgb[~ink] = 0
        dirs = ((0, 1), (0, -1), (1, 0), (-1, 0))
        smooth = {d: np.abs(rgb - np.stack([_shift(rgb[..., c], *d) for c in range(3)], -1)).max(-1) < GLOW_STEP
                  for d in dirs}
        glow = ~ink
        while True:
            nxt = glow.copy()
            for d in dirs:
                nxt |= _shift(glow, *d) & smooth[d]
            if (nxt == glow).all():
                break
            glow = nxt
        letters = ink & ~glow
        y0, y1 = max(_bands(letters), key=lambda b: b[1] - b[0])
        self.height = y1 - y0 + 1
        inside = _edt(~letters)
        outside = _edt(letters)
        self.stroke = float(np.percentile(inside[letters], 90))
        # the opaque blob ends where most pixels that far out are see-through
        self.reach = 1
        while self.reach < outside.max():
            ring = (np.round(outside) == self.reach + 1)
            if ink[ring].mean() < 0.5:
                break
            self.reach += 1
        self.outer = []
        for d in range(self.reach + 1):
            ring = (np.round(outside) == d) & ink & ~letters
            self.outer.append(rgb[ring].mean(0) if ring.any() else (self.outer[-1] if self.outer else np.zeros(3)))
        self.outer = np.array(self.outer)
        rel = (np.arange(can.shape[0]) - y0) / max(1, y1 - y0)
        band = np.clip(np.round(rel * (ROW_BINS - 1)), -3, ROW_BINS + 2).astype(int)
        top = int(np.ceil(self.stroke))
        self.inner = np.zeros((top + 1, ROW_BINS + 6, 3))
        have = np.zeros((top + 1, ROW_BINS + 6), bool)
        depth = np.clip(np.round(inside), 1, top).astype(int)
        for d in range(1, top + 1):
            for r in range(-3, ROW_BINS + 3):
                sel = letters & (depth == d) & (band[:, None] == r)
                if sel.any():
                    self.inner[d, r + 3] = rgb[sel].mean(0)
                    have[d, r + 3] = True
        # empty cells: the nearest measured one
        cells = np.argwhere(have)
        for d, r in np.argwhere(~have):
            if d:
                k = np.argmin(np.abs(cells[:, 0] - d) * 4 + np.abs(cells[:, 1] - r))
                self.inner[d, r] = self.inner[tuple(cells[k])]
        self.colours = np.unique(can[ink])
        self.palette = pal[self.colours][:, :3].astype(float)

    def scale(self, cap):
        """How much smaller the glow is drawn around letters `cap` tall."""
        return min(1.0, max(GLOW_MIN, cap / self.height))

    def margin_for(self, cap):
        return int(np.ceil(self.reach * self.scale(cap)))

    def draw(self, shape, cov, caps, cap):
        """(index image, opaque mask) of the placed coverage `cov`."""
        s = self.scale(cap)
        glyph = cov > 0.5
        inside = _edt(~glyph)
        outside = _edt(glyph)
        stroke = float(np.percentile(inside[glyph], 90)) if glyph.any() else 1.0
        si = max(stroke / self.stroke, 1e-3)
        H = shape[0]
        band = _row_bands(H, caps)
        top = self.inner.shape[0] - 1
        d_in = np.clip(np.round(inside / si), 1, top).astype(int)
        rows = np.broadcast_to((band + 3)[:, None], shape)
        inner = self.inner[d_in, rows]
        d_out = np.clip(np.round(outside / s), 0, self.reach).astype(int)
        outer = self.outer[d_out]
        # anti-aliased edge: the outline colour under partly covered pixels
        a = np.clip(cov, 0, 1)[..., None]
        edge = self.inner[1][rows]
        rgb = np.where(glyph[..., None], inner, a * edge + (1 - a) * outer)
        opaque = glyph | (outside / s <= self.reach)
        # nearest colour of the original's
        flat = rgb[opaque]
        best = np.empty(len(flat), int)
        for k in range(0, len(flat), 20000):
            part = flat[k:k + 20000]
            best[k:k + 20000] = ((part[:, None, :] - self.palette[None]) ** 2).sum(-1).argmin(1)
        out = np.zeros(shape, np.uint8)
        out[opaque] = self.colours[best]
        return out, opaque


def _row_bands(H, caps):
    """Each row's band (-3 .. ROW_BINS + 2) in the nearest line's body."""
    y = np.arange(H)[:, None]
    a = np.array([c[0] for c in caps])[None, :]
    b = np.array([c[1] for c in caps])[None, :]
    nearest = np.abs(y - (a + b) / 2).argmin(axis=1)
    a, b = a[0, nearest], b[0, nearest]
    rel = (np.arange(H) - a) / np.maximum(1.0, b - a)
    return np.clip(np.round(rel * (ROW_BINS - 1)), -3, ROW_BINS + 2).astype(int)


def _render(lines, font_path, cap, scale, tracking=0, bold=0, ss=4):
    """Coverage (0..1) of the lines, centred, and each line's body rows
    (cap height, or x-height for lines with small letters);
    bold thickens the strokes by that much of the cap height on each side."""
    font = fonts.cap_sized(font_path, cap, ss)
    grow = int(round(bold * cap * ss))
    tracking += 2 * grow / ss
    top = font.getbbox('H')[1]
    widths = [sum(font.getlength(c) for c in l) + tracking * ss * (len(l) - 1) for l in lines]
    pitch = cap * ss * (1 + LINE_GAP)
    W = int(max(widths) + 8 * ss)
    H = int(pitch * (len(lines) - 1) + cap * ss * 1.6 + 8 * ss)
    im = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(im)
    caps = []
    for k, (line, w) in enumerate(zip(lines, widths)):
        y = 4 * ss + k * pitch
        x = (W - w) / 2
        for c in line:
            d.text((x, y - top), c, font=font, fill=255)
            x += font.getlength(c) + tracking * ss
        # the letters' body: from the x-height down when there are small letters
        body = cap * ss - (font.getbbox('x')[3] - font.getbbox('x')[1]) if any(c.islower() for c in line) else 0
        caps.append(((y + body) / ss, (y + cap * ss) / ss))
    if grow:
        im = im.filter(ImageFilter.MaxFilter(2 * grow + 1))
    w2, h2 = int(np.ceil(W * scale / ss)), int(np.ceil(H / ss))
    im = im.resize((w2 * ss, h2 * ss), Image.LANCZOS).resize((w2, h2), Image.BOX)
    return np.asarray(im, float) / 255, caps


def _fit(lines, font_path, max_cap, box_w, box_h, edge_for=lambda cap: 0, min_scale=MIN_SCALE,
         tracking_for=None, bold=0):
    """The biggest rendering of the lines (squeezed if need be) that fits
    the box with its outline; returns (coverage, cap rows, cap, edge).
    Letters are spaced by the outline's width unless tracking_for says."""
    cap = max_cap
    while True:
        e = edge_for(cap)
        tracking = e if tracking_for is None else tracking_for(cap)
        for scale in np.arange(1.0, min_scale - 0.001, -0.04):
            cov, caps = _render(lines, font_path, cap, scale, tracking=tracking, bold=bold)
            ys, xs = np.nonzero(cov > 0.02)
            if xs.max() - xs.min() + 1 + 2 * (e + 1) <= box_w and ys.max() - ys.min() + 1 + 2 * (e + 1) <= box_h:
                return cov, caps, cap, e
        cap -= 1
        assert cap >= 8, f'"{" / ".join(lines)}" does not fit'


def _place(shape, cov, caps, box):
    """The block centred in box, at full size; and its cap rows there."""
    ys, xs = np.nonzero(cov > 0.02)
    cov = cov[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    caps = [(a - ys.min(), b - ys.min()) for a, b in caps]
    x0, y0, x1, y1 = box
    h, w = cov.shape
    left = int(round((x0 + x1 - w) / 2))
    top = int(round((y0 + y1 - h) / 2))
    full = np.zeros(shape, float)
    full[top:top + h, left:left + w] = cov
    return full, [(a + top, b + top) for a, b in caps]


def draw(can, pal, blocks, look=None, narrow=0):
    """Index image with the blocks drawn in the original's look (or `look`,
    measured from another picture with the same palette); narrow takes that
    much off both sides of every box."""
    H, W = can.shape
    ink = pal[can][..., 3] > 0
    ys, xs = np.nonzero(ink)
    orig_box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    out = np.zeros_like(can)
    for lines, box, font_path, max_cap, kind, *opt in blocks:
        opt = opt[0] if opt else {}
        min_scale, bold = opt.get('min_scale', MIN_SCALE), opt.get('bold', 0)
        if box is None:
            box = orig_box
        elif box == 'wide':
            cx = (orig_box[0] + orig_box[2]) / 2
            half = min(cx, W - cx) - MARGIN
            box = (int(cx - half), MARGIN, int(cx + half), H - MARGIN)
        box = (box[0] + narrow, box[1], box[2] - narrow, box[3])
        box_w, box_h = box[2] - box[0], box[3] - box[1]
        if kind == 'ink':
            cov, caps, _, _ = _fit(lines, font_path, max_cap, box_w, box_h, min_scale=min_scale, bold=bold)
            full, _ = _place(can.shape, cov, caps, box)
            level = np.clip(np.round(full * 15), 0, 15).astype(np.uint8)
            level[full < 0.04] = 0
            out = np.maximum(out, level)
            continue
        if kind == 'glow':
            glow = Glow(can, pal)
            cov, caps, cap, _ = _fit(lines, font_path, max_cap, box_w, box_h, glow.margin_for, min_scale,
                                     tracking_for=lambda cap: max(1, round(cap * 0.04)), bold=bold)
            full, caps = _place(can.shape, cov, caps, box)
            px, opaque = glow.draw(can.shape, full, caps, cap)
            out[opaque] = px[opaque]
            continue
        look = look or Look(can, pal)
        cov, caps, cap, edge = _fit(lines, font_path, max_cap, box_w, box_h, look.edge_for, min_scale, bold=bold)
        full, caps = _place(can.shape, cov, caps, box)
        glyph = full > 0.45
        grown = _grow(glyph, edge)
        depth = np.where(glyph, edge + 1, np.minimum(_depth(grown), edge))
        # depth in the new lettering -> depth in the original's
        if edge:
            orig_d = np.clip(np.round((depth - 0.5) / edge * look.edge + 0.5), 1, look.edge).astype(int)
            orig_d[glyph] = look.edge + 1
        else:
            orig_d = np.full(depth.shape, look.edge + 1)
        band = _row_bands(H, caps)
        ys, xs = np.nonzero(grown)
        for d in np.unique(orig_d[ys, xs]):
            sel = orig_d[ys, xs] == d
            out[ys[sel], xs[sel]] = look.colours[int(d)][band[ys[sel]] + 3]
    return out


def ink_palette(raw):
    """The 16-colour palette with see-through steps of its ink colour."""
    entries = [raw[4 * k:4 * k + 4] for k in range(16)]
    r, g, b, _ = entries[1]
    steps = [entries[0]] + [bytes([r, g, b, max(1, round(0x80 * k / 15))]) for k in range(1, 16)]
    return b''.join(steps)


def redraw(buf, bank, index):
    """(entry, original pixels, new pixels, raw palette of the new, bpp,
    tile positions): the lettering is made narrower until the entry's own
    tiles can hold it."""
    blocks = SPECS[bank, index]
    entry, can, pal, raw_pal, bpp = _entry(buf, bank, index)
    look = None
    borrow = [b[5]['look'] for b in blocks if len(b) > 5 and 'look' in b[5]]
    if borrow:
        _, can2, pal2, raw2, _ = _entry(buf, bank, borrow[0])
        assert raw2 == raw_pal, f'{bank:#x}:{index} and {borrow[0]} have different palettes'
        look = Look(can2, pal2)
    tiles = entry['tiles']
    tw, th = tiles[0]['w'], tiles[0]['h']
    for narrow in range(0, can.shape[1] // 2, 4):
        px = draw(can, pal, blocks, look, narrow)
        padded = np.zeros((px.shape[0] + th, px.shape[1] + tw), np.uint8)
        padded[:px.shape[0], :px.shape[1]] = px
        cells = texh.cover(padded > 0, tw, th, len(tiles))
        if cells:
            break
    assert cells, f'callout {bank:#x}:{index} needs more than {len(tiles)} tiles'
    if any(b[4] == 'ink' for b in blocks):
        assert bpp == 4
        raw_pal = ink_palette(raw_pal)
    return entry, can, padded, raw_pal, bpp, cells


def changes(buf):
    """({TEXH: {entry: [(tile data, rect)]}}, []) for every picture in SPECS."""
    banks = {}
    for bank, index in SPECS:
        entry, _, px, raw_pal, bpp, cells = redraw(buf, bank, index)
        tw, th = entry['tiles'][0]['w'], entry['tiles'][0]['h']
        banks.setdefault(bank, {})[index] = [
            (texh.compress(px[y:y + th, x:x + tw], bpp, raw_pal), (x, y, x + tw, y + th)) for x, y in cells]
    return banks, []
