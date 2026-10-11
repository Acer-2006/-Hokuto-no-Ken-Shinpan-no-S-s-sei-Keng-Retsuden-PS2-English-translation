"""Fix for the English win quotes losing letters.

The results screen draws the arcade's English win quote with an 8x16 font
(entry 0 of the results resource, TEXH 0x4D86800: a 128x128 tile holding
ASCII 0x20-0x7F in 16 columns). The drawing code (0x1AF420) takes each
letter's texture rectangle from (column * 8 - 1, row * 16 - 1), so for the
first row of the font (space to '/', which includes ' , . - ! ") and the
first column ('0', '@', 'P', '`', 'p') a corner lands on -1 and the letter
is not drawn at all: "Don't worry, I didn't hit a vital point." comes out
as "Don t worry  I didn t hit a vital  oint".

The fix moves the font's pixels one to the right and one down inside its
tile (the rightmost column and bottom row are empty) and drops the -1 from
the code, so every letter samples exactly the pixels it did before. The
tile's rectangle moves up and left by one, so the entry itself looks the
same anywhere it is drawn whole.
"""
import numpy as np

import texh

RESULTS = 0x4D86800       # results screen (TEXH)
FONT = 0                  # entry with the quote font

# address -> (original word, new word)
CODE = {
    0x1AF580: (0x3C0342EE, 0x3C0342F0),   # '･' (0xA5) column: 119.0 -> 120.0
    0x1AF584: (0x3C02429E, 0x3C0242A0),   # '･' row: 79.0 -> 80.0
    0x1AF5BC: (0x3C033F80, 0x3C030000),   # u = column * 8 - 1.0 -> - 0.0
    0x1AF5F0: (0x3C023F80, 0x3C020000),   # v = row * 16 - 1.0 -> - 0.0
}


def changes(buf):
    """({TEXH: {entry: [(tile data, rect)]}}, []) with the font moved."""
    entry = list(texh.entries(buf, RESULTS))[FONT]
    (t,) = entry['tiles']
    px, pal = texh.pixels(bytes(buf[t['data']:t['data'] + t['size']]))
    assert pal is None and px.shape == (128, 128)
    assert not px[:, -1].any() and not px[-1].any(), 'quote font reaches the tile edge'
    moved = np.zeros_like(px)
    moved[1:, 1:] = px[:-1, :-1]
    rect = (t['x'] - 1, t['y'] - 1, t['x'] - 1 + t['w'], t['y'] - 1 + t['h'])
    return {RESULTS: {FONT: [(texh.compress(moved, 4), rect)]}}, []
