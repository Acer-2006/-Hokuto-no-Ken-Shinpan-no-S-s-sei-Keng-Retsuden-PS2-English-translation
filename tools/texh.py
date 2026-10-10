"""Read the game's compressed textures (TEXH banks in HK_B.BIN).

A graphics resource in HK_B.BIN is a FARC header (0x800 bytes) followed by a
blob holding PALH (palettes), TEXH (textures) and ANMH (animations). The
FARC's GIRP/GIRT/GIRA records give each part's offset inside the blob.

TEXH entry: u16 flags, u16 tile count, u16 width, u16 height, 8 bytes,
u32 -1, u32 ?, then 32-byte tile records:
  u32 format (0x..21 = 8bpp, 0x..11/12/10 = 4bpp), u32 data offset (from
  the TEXH start), u32 data offset again, u32 compressed size, u32 -1
  (texture id at run time), u16 tile w, u16 tile h, s16 x0, y0, x1, y1.

Tile data: 16-byte header (u16 flag bytes, u16 has-palette, u16 bpp, u16 w,
u16 h, u16 sw, u16 sh, u16), then, when has-palette is 1 (formats 0x66...),
the tile's own uncompressed palette: 16 (4bpp) or 256 (8bpp) RGBA colours,
alpha 0x80 = opaque, 8bpp palettes in the GS's swizzled order. Then the
flag bit stream and the byte stream. Flags are read as
little-endian u32 words, most significant bit first:
  0    literal byte
  10   copy: 2 bytes, distance = b0 + 1, length = b1 + 3
  110  short copy: 1 byte, distance = (b >> 6) + 1, length = (b & 63) + 2
  111  zero run: 1 byte, length = b + 2 (b < 0x80) or ((b & 0x7f) + 16) * 8
Copies reaching back before the start of the output read zeros here (the
game reads whatever its buffer held, so the encoder never does that). Output
stops at sw*sh*bpp/8 bytes (the second width/height in the header; a few
tiles store only their top rows). The game doesn't clear its buffer first,
so a new tile must encode every byte, trailing zeros included.
"""
import struct

import numpy as np


def decompress(tile):
    """(raw palette bytes or b'', pixel bytes, bpp, w, h)"""
    flen, has_pal, bpp, w, h, sw, sh = struct.unpack_from('<HHHHHHH', tile, 0)
    pal_size = (4 << bpp) if has_pal & 1 else 0
    palette = bytes(tile[16:16 + pal_size])
    size = w * h * bpp // 8
    stored = min(size, sw * sh * bpp // 8)
    flags = tile[16 + pal_size:16 + pal_size + flen]
    data = tile[16 + pal_size + flen:]
    words = struct.unpack_from(f'<{flen // 4}I', flags)
    out = bytearray()
    bp = dp = 0

    def bit():
        nonlocal bp
        b = (words[bp >> 5] >> (31 - (bp & 31))) & 1
        bp += 1
        return b

    def copy(dist, ln):
        for _ in range(ln):   # reaching back before the start reads zeros
            out.append(out[-dist] if dist <= len(out) else 0)

    while len(out) < stored and dp < len(data) and bp < flen * 8:
        if not bit():
            out.append(data[dp])
            dp += 1
        elif not bit():
            copy(data[dp] + 1, data[dp + 1] + 3)
            dp += 2
        elif not bit():
            b = data[dp]
            dp += 1
            copy((b >> 6) + 1, (b & 63) + 2)
        else:
            b = data[dp]
            dp += 1
            out.extend(bytes(b + 2 if b < 0x80 else ((b & 0x7f) + 16) * 8))
    out = bytes(out[:size]) + bytes(max(0, size - len(out)))
    return palette, out, bpp, w, h


def unswizzle_palette(raw):
    """RGBA rows in index order (8bpp palettes are stored in GS CSM1 order)."""
    c = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 4).copy()
    if len(c) == 256:
        i = np.arange(256)
        c = c[(i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)]
    c[:, 3] = np.minimum(c[:, 3].astype(np.uint16) * 2, 255)
    return c


def pixels(tile):
    """(h, w) array of palette indices, plus the tile's own palette or None."""
    pal, raw, bpp, w, h = decompress(tile)
    a = np.frombuffer(raw, dtype=np.uint8)
    if bpp == 4:
        a = np.stack([a & 15, a >> 4], axis=1).reshape(-1)
    return a.reshape(h, w), (unswizzle_palette(pal) if pal else None)


def resource(buf, farc):
    """{'GIRP': (offset, size), ...} for the resource whose FARC starts at farc."""
    parts = {}
    for k in range(3):
        tag, _, _, _, off, size = struct.unpack_from('<4sIIIII', buf, farc + 0x60 + 0x18 * k)
        parts[tag.decode('latin1')] = (farc + 0x800 + off, size)
    return parts


def palettes(buf, palh):
    """List of palettes (arrays of RGBA rows) in a PALH block."""
    assert buf[palh:palh + 4] == b'PALH'
    n = struct.unpack_from('<I', buf, palh + 0xC)[0]
    out = []
    for i in range(n):
        e = palh + struct.unpack_from('<I', buf, palh + 0x10 + 4 * i)[0]
        _, _, ncol, _, off = struct.unpack_from('<BBHII', buf, e)
        c = np.frombuffer(bytes(buf[palh + off:palh + off + 2 * ncol]), dtype='<u2').astype(np.uint32)
        rgba = np.stack([(c & 31) * 255 // 31, ((c >> 5) & 31) * 255 // 31,
                         ((c >> 10) & 31) * 255 // 31, np.where(c >> 15, 255, 0)], axis=1)
        out.append(rgba.astype(np.uint8))
    return out


def entries(buf, texh):
    """Parse a TEXH bank. Yields dicts with the entry size and its tiles."""
    assert buf[texh:texh + 4] == b'TEXH'
    count = struct.unpack_from('<I', buf, texh + 0xC)[0]
    for i in range(count):
        eo = texh + struct.unpack_from('<I', buf, texh + 0x20 + 4 * i)[0]
        flags, nt, w, h = struct.unpack_from('<HHHH', buf, eo)
        tiles = []
        for t in range(nt):
            r = eo + 0x18 + 0x20 * t
            fmt, off, _, size, _, tw, th, x0, y0, x1, y1 = struct.unpack_from('<IIIIIHHhhhh', buf, r)
            tiles.append({'record': r, 'format': fmt, 'data': texh + off, 'size': size,
                          'x': x0, 'y': y0, 'w': tw, 'h': th})
        yield {'index': i, 'offset': eo, 'flags': flags, 'w': w, 'h': h, 'tiles': tiles}


def render(buf, entry, palette=None):
    """(h, w, 4) RGBA image of a whole entry, tiles pasted at their positions.
    Tiles with their own palette use it; others use `palette` (or grey)."""
    img = np.zeros((entry['h'], entry['w'], 4), dtype=np.uint8)
    for t in entry['tiles']:
        px, pal = pixels(bytes(buf[t['data']:t['data'] + t['size']]))
        if pal is None:
            if palette is not None and len(palette) > px.max():
                pal = palette
            else:
                g = np.linspace(0, 255, 256 if px.max() > 15 else 16).astype(np.uint8)
                pal = np.stack([g, g, g, np.full_like(g, 255)], axis=1)
        rgba = pal[px]
        x, y = t['x'], t['y']
        sy, sx = max(0, -y), max(0, -x)
        ey, ex = min(px.shape[0], entry['h'] - y), min(px.shape[1], entry['w'] - x)
        if ey > sy and ex > sx:
            img[y + sy:y + ey, x + sx:x + ex] = rgba[sy:ey, sx:ex]
    return img


def _run_lengths(eq):
    """For each i, how many consecutive True values start at i."""
    n = len(eq)
    idx = np.arange(n + 1)
    nxt = np.where(np.append(~eq, True), idx, n)
    nxt = np.minimum.accumulate(nxt[::-1])[::-1]
    return (nxt - idx)[:n]


def compress_stream(data):
    """Encode bytes with the game's LZ scheme. Returns (flag bytes, byte stream).
    Optimal parse over literal / zero run / short copy / long copy."""
    data = np.frombuffer(bytes(data), dtype=np.uint8)
    n = len(data)
    padded = np.concatenate([np.zeros(256, dtype=np.uint8), data])
    match = {}
    for d in range(1, 257):
        match[d] = _run_lengths(padded[256:] == padded[256 - d:256 - d + n])
    zero = _run_lengths(data == 0)
    INF = 1 << 60
    cost = [INF] * (n + 1)
    choice = [None] * (n + 1)
    cost[n] = 0
    for i in range(n - 1, -1, -1):
        best, pick = cost[i + 1] + 9, ('L',)
        zl = int(zero[i])
        if zl >= 2:
            for ln in (min(zl, 129), min(zl, 1144) // 8 * 8):
                if ln >= 2 and (ln <= 129 or ln >= 128):
                    c = cost[i + ln] + 11
                    if c < best:
                        best, pick = c, ('Z', ln)
        for d in range(1, min(4, i) + 1):    # never reach back before the start
            l = min(int(match[d][i]), 65)
            if l >= 2:
                c = cost[i + l] + 11
                if c < best:
                    best, pick = c, ('S', d, l)
        for d in range(1, min(256, i) + 1):
            l = min(int(match[d][i]), 258)
            if l >= 3:
                c = cost[i + l] + 18
                if c < best:
                    best, pick = c, ('M', d, l)
        cost[i], choice[i] = best, pick
    bits, out = [], bytearray()
    i = 0
    while i < n:
        p = choice[i]
        if p[0] == 'L':
            bits.append(0); out.append(int(data[i])); i += 1
        elif p[0] == 'M':
            bits += [1, 0]; out += bytes([p[1] - 1, p[2] - 3]); i += p[2]
        elif p[0] == 'S':
            bits += [1, 1, 0]; out.append(((p[1] - 1) << 6) | (p[2] - 2)); i += p[2]
        else:
            ln = p[1]
            bits += [1, 1, 1]
            out.append(ln - 2 if ln <= 129 else 0x80 | (ln // 8 - 16))
            i += ln
    while len(bits) % 32:
        bits.append(0)
    words = [int(''.join(map(str, bits[k:k + 32])), 2) for k in range(0, len(bits), 32)]
    return struct.pack(f'<{len(words)}I', *words), bytes(out)


def compress(pixels, bpp, palette=b''):
    """Build tile data (header, palette, flags, bytes) from a (h, w) index array."""
    h, w = pixels.shape
    a = pixels.astype(np.uint8).reshape(-1)
    raw = (a[0::2] | (a[1::2] << 4)).tobytes() if bpp == 4 else a.tobytes()
    flags, data = compress_stream(raw)
    head = struct.pack('<8H', len(flags), 1 if palette else 0, bpp, w, h, w, h, len(flags))
    tile = head + palette + flags + data
    return tile + bytes(-len(tile) % 16)
