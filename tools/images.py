"""English replacements for text drawn into the game's textures.

Each replacement is generated at build time from your own disc: the tool
decodes the original tile, draws the English in the same style and palette
indices, re-compresses it and checks it fits the original's space. No game
graphics are stored in this repository.
"""
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import texh

BOLD = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'   # Latin matches the game's gothic

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
    font = ImageFont.truetype(BOLD, size * ss)
    while font.getbbox('H')[3] - font.getbbox('H')[1] < cap * ss:
        size += 1
        font = ImageFont.truetype(BOLD, size * ss)
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
    """Yields (tile dict, new tile bytes, description) for every image edit."""
    res = texh.resource(buf, HISTORY)
    entries = list(texh.entries(buf, res['GIRT'][0]))
    for idx, text in CHAPTERS.items():
        tile = entries[idx]['tiles'][0]
        old = bytes(buf[tile['data']:tile['data'] + tile['size']])
        px, _ = texh.pixels(old)
        bpp = struct.unpack_from('<H', old, 4)[0]
        new = fit(lambda wdt: texh.compress(label_pixels(text, px, wdt), bpp),
                  len(old), [None] + list(range(120, 40, -6)))
        yield tile, new, f'HISTORY chapter label {idx}: {text}'
