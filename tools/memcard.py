"""English memory card messages and sound test names.

The memory card messages are pictures: white 1-bit text (indices 0 and 15 of
a 16-grey palette) in 560x256 entries made of a few 128x128, 64x64, 32x32...
tiles, plus small "Yes"/"No" pictures. There are three sets, each in its own
resource: checking and loading at start-up, saving (after a game), and the
save/load screen in OPTION.

Only the tiles that hold text exist, so the English (wrapped to 510 pixels,
left-aligned like the originals; " / " starts a new line) gets the same
tiles moved to wherever its text is. translation/memcard.tsv gives the
English and the entries that show it (B = start-up, S = saving, O = options).

The OPTION resource also has the names shown in SOUND SETTINGS (BGM and
PLAY VOICE), in translation/bgm.tsv.
"""
import csv
import os

import numpy as np
from PIL import Image, ImageDraw

import fonts
import texh

BANKS = {   # TEXH offsets in HK_B.BIN
    'B': 0x5EA6000,
    'S': 0x5EB2800,
    'O': 0x5E3E000,
}
TEXT, BACK = 15, 0
FONT = fonts.SERIF_TEXT
SIZES = (19, 18, 17)            # first one that fits
WIDTH = 510                     # longest line
KEEP_TOGETHER = ('memory card (8MB) (for PlayStation 2)', 'MEMORY CARD slot 1', 'system data')
LEFT = 4                        # first column of text
FIRST_BASELINE, PITCH = 27, 23  # rows, as in the originals


def load(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'translation', 'memcard.tsv')
    out = {}
    with open(path, encoding='utf-8') as f:
        for row in list(csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE))[1:]:
            if not row:
                continue
            _, screens, text = row
            for s in screens.split():
                out[(s[0], int(s[1:]))] = text
    return out


def _covered(entry):
    tiles = entry['tiles']
    W = max(t['x'] + t['w'] for t in tiles)
    H = max(t['y'] + t['h'] for t in tiles)
    m = np.zeros((H, W), bool)
    for t in tiles:
        m[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']] = True
    return m


def wrap(text, font, width=WIDTH):
    for phrase in KEEP_TOGETHER:
        text = text.replace(phrase, phrase.replace(' ', '\u00a0'))
    lines = []
    for para in text.split(' / '):
        words = para.split(' ')
        while words:
            n = 1
            while n < len(words) and font.getlength(' '.join(words[:n + 1])) <= width:
                n += 1
            lines.append(' '.join(words[:n]))
            words = words[n:]
    return lines


def message_pixels(entry, text):
    """(index image, new tile positions) for a message entry."""
    tiles = entry['tiles']
    tw, th = tiles[0]['w'], tiles[0]['h']
    assert all((t['w'], t['h']) == (tw, th) for t in tiles)
    for size in SIZES:
        font = fonts.load(FONT, size)
        lines = wrap(text, font)
        im = Image.new('L', (entry['w'], entry['h']), 0)
        d = ImageDraw.Draw(im)
        d.fontmode = '1'
        for k, line in enumerate(lines):
            d.text((LEFT, FIRST_BASELINE + PITCH * k), line, font=font, fill=255, anchor='ls')
        ink = np.asarray(im) > 127
        if ink[-1].any() or ink[:, -1].any():
            continue
        cells = texh.cover(ink, tw, th, len(tiles))
        if cells:
            break
    else:
        raise ValueError(f'does not fit: {text}')
    W = max(x for x, _ in cells) + tw
    H = max(y for _, y in cells) + th
    px = np.full((max(H, ink.shape[0]), max(W, ink.shape[1])), BACK, np.uint8)
    px[:ink.shape[0], :ink.shape[1]][ink] = TEXT
    return px, cells


def label_pixels(entry, orig, text):
    """Index image for the small Yes/No pictures: same left edge and
    vertical centre as the Japanese."""
    covered = _covered(entry)
    ys, xs = np.nonzero(orig)
    font = fonts.load(FONT, SIZES[0])
    im = Image.new('L', (200, 60), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    d.text((20, 40), text, font=font, fill=255, anchor='ls')
    ink = np.asarray(im) > 127
    iy, ix = np.nonzero(ink)
    ink = ink[iy.min():iy.max() + 1, ix.min():ix.max() + 1]
    x0 = int(xs.min())
    y0 = int(round((ys.min() + ys.max()) / 2 - (ink.shape[0] - 1) / 2))
    px = np.full(covered.shape, BACK, np.uint8)
    px[y0:y0 + ink.shape[0], x0:x0 + ink.shape[1]][ink] = TEXT
    assert not px[~covered].any(), text
    return px


def _canvas(buf, entry):
    m = _covered(entry)
    can = np.zeros(m.shape, np.uint8)
    for t in entry['tiles']:
        px, _ = texh.pixels(bytes(buf[t['data']:t['data'] + t['size']]))
        can[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w']] = px
    return can


def replacements(buf, texts=None):
    texts = texts or load()
    for bank, texh_off in BANKS.items():
        entries = list(texh.entries(buf, texh_off))
        ids = sorted(i for b, i in texts if b == bank)
        tiles, rects, datas = [], [], []
        for i in ids:
            e, text = entries[i], texts[(bank, i)]
            orig = _canvas(buf, e)
            assert set(np.unique(orig)) <= {BACK, TEXT}, (bank, i)
            if e['w'] <= 64:
                px = label_pixels(e, orig, text)
                cells = [(t['x'], t['y']) for t in e['tiles']]
            else:
                px, cells = message_pixels(e, text)
            for t, (x, y) in zip(e['tiles'], cells):
                tiles.append(t)
                rects.append((x, y, x + t['w'], y + t['h']))
                datas.append(texh.compress(px[y:y + t['h'], x:x + t['w']], 4))
        yield from texh.repack(texh_off, tiles, datas, rects, what=f'memory card messages {bank}')
    yield from track_replacements(buf)


# --- sound test track names (OPTION > SOUND SETTINGS) --------------------------
#
# One line in 32x32 tiles, as many tiles as the Japanese needed, so long
# names use a smaller size.

TRACKS = ('O', range(93, 124))
TRACK_SIZES = (18, 17, 16, 15, 14, 13)


def load_tracks(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'translation', 'bgm.tsv')
    with open(path, encoding='utf-8') as f:
        rows = list(csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE))[1:]
    return {int(r[0]): r[1] for r in rows if r}


def _line(text, size):
    """1-bit ink of one line, cropped, and the baseline's row in it."""
    font = fonts.load(FONT, size)
    im = Image.new('L', (int(font.getlength(text)) + 40, 3 * size), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = '1'
    d.text((20, 2 * size), text, font=font, fill=255, anchor='ls')
    ink = np.asarray(im) > 127
    ys, xs = np.nonzero(ink)
    return ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1], 2 * size - ys.min()


def track_pixels(entry, orig, text):
    """(index image, tile positions): the name centred in the entry (the
    game centres the entry between the arrows), capitals centred on the
    Japanese one's middle, tiles in a row under it."""
    tiles = entry['tiles']
    tw, th = tiles[0]['w'], tiles[0]['h']
    ys, xs = np.nonzero(orig)
    middle = (ys.min() + ys.max()) / 2
    for size in TRACK_SIZES:
        ink, base = _line(text, size)
        if ink.shape[1] <= tw * len(tiles):
            break
    else:
        raise ValueError(f'track name too long: {text}')
    left = max(0, (entry['w'] - ink.shape[1]) // 2)
    cap, _ = _line('H', size)
    top = int(round(middle + cap.shape[0] / 2)) - base
    y = min(t['y'] for t in tiles)
    assert y <= top and top + ink.shape[0] <= y + th, text
    cells = [(left + k * tw, y) for k in range(len(tiles))]
    px = np.full((y + th, left + tw * len(tiles)), BACK, np.uint8)
    px[top:top + ink.shape[0], left:left + ink.shape[1]][ink] = TEXT
    return px, cells


def track_replacements(buf, names=None):
    names = names or load_tracks()
    bank, ids = TRACKS
    texh_off = BANKS[bank]
    entries = list(texh.entries(buf, texh_off))
    tiles, rects, datas = [], [], []
    for i in ids:
        e = entries[i]
        orig = _canvas(buf, e)
        assert set(np.unique(orig)) <= {BACK, TEXT}, i
        px, cells = track_pixels(e, orig, names[i])
        for t, (x, y) in zip(e['tiles'], cells):
            tiles.append(t)
            rects.append((x, y, x + t['w'], y + t['h']))
            datas.append(texh.compress(px[y:y + t['h'], x:x + t['w']], 4))
    yield from texh.repack(texh_off, tiles, datas, rects, what='sound test track names')
