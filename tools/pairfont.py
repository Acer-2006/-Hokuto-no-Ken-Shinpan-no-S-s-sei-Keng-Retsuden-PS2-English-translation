"""Two-letters-per-tile English text for the game's Shift-JIS text renderer.

The renderer used by HISTORY and the gallery (set_text at 0x25E320) only
draws Shift-JIS characters, one 16x16 tile per character, 24 tiles per line.
Full-width English fits only 23 letters per line and is widely spaced.

The font (GIFT resource in HK_B.BIN) has room for 12288 tiles, but the
Shift-JIS user-defined area (lead bytes 0xF0-0xFC) maps to tiles that are
all blank. We draw two 8-pixel-wide letters into each of those tiles, so
every Shift-JIS code there stands for a pair of letters ("Ke", "ns", ...).
Each distinct pair that the translation uses gets its own code.

The text keeps its length (2 letters = 2 bytes), lines hold 48 letters, and
the game's code is unchanged.
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_FILE = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
FONT_SIZE = 13            # pixels; DejaVu Sans Mono advance at 13px is 7.8px
BASELINE = 13             # same baseline as the game's full-width letters
SS = 4                    # supersampling for anti-aliasing
THRESHOLDS = (0.18, 0.45, 0.72)   # coverage -> 2bpp levels 1, 2, 3

FONT_GLYPHS = 12288       # tiles in the GIFT texture (0xC0000 bytes)
FREE_FIRST = 0x16C4 + 16 * 188    # tile for Shift-JIS 0xF040
FREE_COUNT = 13 * 188             # lead bytes 0xF0-0xFC
FULLWIDTH_SPACE = b'\x81\x40'     # tile 0, blank


def code_for(n):
    """Shift-JIS code (2 bytes) of the n-th free tile."""
    lead, t = divmod(n, 188)
    trail = 0x40 + t if t < 63 else 0x41 + t
    return bytes([0xF0 + lead, trail])


def tile_for_code(code):
    """Same mapping as the game's 0x25E420, for lead bytes 0xE0-0xFC."""
    lead, trail = code
    t = trail - 0x40 if trail < 0x7F else trail - 0x41
    return 0x16C4 + (lead - 0xE0) * 188 + t


class HalfWidthFont:
    def __init__(self, path=FONT_FILE, size=FONT_SIZE):
        self.font = ImageFont.truetype(path, size * SS)
        self.cache = {}

    def glyph(self, ch):
        """8x16 array of 2bpp levels (0 = transparent, 3 = solid)."""
        if ch not in self.cache:
            w, h = 8, 16
            im = Image.new('L', (w * SS, h * SS), 0)
            asc, _ = self.font.getmetrics()
            x = (w * SS - self.font.getlength(ch)) / 2
            ImageDraw.Draw(im).text((x, BASELINE * SS - asc), ch, font=self.font, fill=255)
            cov = np.asarray(im, dtype=float).reshape(h, SS, w, SS).mean(axis=(1, 3)) / 255
            q = np.zeros((h, w), dtype=np.uint32)
            for level, t in enumerate(THRESHOLDS, 1):
                q[cov >= t] = level
            self.cache[ch] = q
        return self.cache[ch]

    def tile(self, pair):
        """64-byte game tile: 16 rows, each a little-endian u32 of 16 2-bit pixels."""
        px = np.hstack([self.glyph(pair[0]), self.glyph(pair[1])])
        shifts = np.arange(16, dtype=np.uint32) * 2
        rows = (px << shifts).sum(axis=1).astype('<u4')
        return rows.tobytes()


class PairEncoder:
    """Assigns a free Shift-JIS code to every distinct letter pair."""

    def __init__(self):
        self.codes = {}

    def encode(self, text):
        if len(text) % 2:
            text += ' '
        out = b''
        for i in range(0, len(text), 2):
            pair = text[i:i + 2]
            if pair == '  ':
                out += FULLWIDTH_SPACE
                continue
            if pair not in self.codes:
                if len(self.codes) >= FREE_COUNT:
                    raise ValueError(f'out of free font tiles at pair {pair!r}')
                self.codes[pair] = code_for(len(self.codes))
            out += self.codes[pair]
        return out

    def tiles(self, font):
        """(tile index, 64 bytes) for every pair used."""
        return [(tile_for_code(c), font.tile(p)) for p, c in self.codes.items()]
