"""Read and write the game's compressed textures (TEXH banks in HK_B.BIN).

A graphics resource in HK_B.BIN is a FARC header (0x800 bytes) followed by a
blob holding PALH (palettes), TEXH (textures) and ANMH (animations). The
FARC's GIRP/GIRT/GIRA records give each part's offset inside the blob.

TEXH entry: u16 flags, u16 tile count, u16 width, u16 height, 8 bytes,
u32 -1, u32 ?, then 32-byte tile records:
  u32 format (0x..21 = 8bpp, 0x..11/12/10 = 4bpp), u32 data offset (from
  the TEXH start), u32 data offset again, u32 compressed size, u32 -1
  (texture id at run time), u16 tile w, u16 tile h, s16 x0, y0, x1, y1.

Tile data: 16-byte header (u16 a, u16 has-palette, u16 bpp, u16 w, u16 h,
u16 w, u16 b, u16 mode), then, when has-palette is 1, the tile's own
uncompressed palette: 16 (4bpp) or 256 (8bpp) RGBA colours, alpha 0x80 =
opaque, 8bpp palettes in the GS's swizzled order. The streams follow
(their offsets are relative to the end of the palette). Bit streams are read
as little-endian u32 words, most significant bit first; byte streams as
little-endian u32 words too, so every stream is 4-byte aligned.

Normal tiles (decoder at 0x290880): flag bits at 0, bytes at `a`.
  0    literal byte
  10   copy: 2 bytes, distance = b0 + 1, length = b1 + 3
       (b0 = b1 = 0 ends the stream; that is the only stop condition)
  110  short copy: 1 byte, distance = (b >> 6) + 1, length = (b & 63) + 2
  111  zero run: 1 byte, length = b + 2 (b < 0x80) or ((b & 0x7f) + 16) * 8
Mode 3 tiles (decoder at 0x290600, images with at most 32 colours, like the
command lists): flag bits at 0, 4-bit literals at `b`, bytes at `a`.
  0 x  literal: next nibble (low nibble first) | x << 4
  10   copy, as above (including the end marker)
  11   short copy, as above
A value of 1 in `a` means the pixels are stored uncompressed.

The game doesn't clear its buffer and copies may reach back before the start
into whatever was there, so encoded tiles cover every byte, never reach back
before the start, and always end with the end marker.
"""
import struct

import numpy as np


class _Bits:
    def __init__(self, raw):
        n = len(raw) // 4
        self.words = struct.unpack_from(f'<{n}I', raw) if n else ()
        self.pos = 0

    def __call__(self):
        w = self.words[self.pos >> 5]
        b = (w >> (31 - (self.pos & 31))) & 1
        self.pos += 1
        return b


def decompress(tile):
    """(raw palette bytes or b'', pixel bytes, bpp, w, h)"""
    a, has_pal, bpp, w, h, _, b, mode = struct.unpack_from('<8H', tile, 0)
    pal_size = (4 << bpp) if has_pal & 1 else 0
    palette = bytes(tile[16:16 + pal_size])
    base = 16 + pal_size
    size = w * h * bpp // 8
    if a == 1 and len(tile) >= base + size:          # stored uncompressed
        return palette, bytes(tile[base:base + size]), bpp, w, h
    bit = _Bits(tile[base:base + (b if mode == 3 else a)])
    data = tile[base + a:]
    nibbles = tile[base + b:base + a] if mode == 3 else b''
    out = bytearray()
    dp = npos = 0
    limit = 4 * size + 4096

    def copy(dist, ln):
        for _ in range(ln):
            out.append(out[-dist] if dist <= len(out) else 0)

    try:
        while len(out) < limit:
            if mode == 3:
                if not bit():
                    v = nibbles[npos >> 1] >> (4 * (npos & 1)) & 15
                    npos += 1
                    out.append(v | (bit() << 4))
                    continue
                if bit():
                    x = data[dp]
                    dp += 1
                    copy((x >> 6) + 1, (x & 63) + 2)
                    continue
            else:
                if not bit():
                    out.append(data[dp])
                    dp += 1
                    continue
                if bit():
                    x = data[dp]
                    dp += 1
                    if bit():
                        out.extend(bytes(x + 2 if x < 0x80 else ((x & 0x7f) + 16) * 8))
                    else:
                        copy((x >> 6) + 1, (x & 63) + 2)
                    continue
            d0, d1 = data[dp], data[dp + 1]
            dp += 2
            if d0 == 0 and d1 == 0:
                break
            copy(d0 + 1, d1 + 3)
    except IndexError:
        pass
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


# --- encoder ---------------------------------------------------------------

def _run_lengths(eq):
    """For each i, how many consecutive True values start at i."""
    n = len(eq)
    idx = np.arange(n + 1)
    nxt = np.where(np.append(~eq, True), idx, n)
    nxt = np.minimum.accumulate(nxt[::-1])[::-1]
    return (nxt - idx)[:n]


def _pack_bits(bits):
    bits = bits + [0] * (-len(bits) % 32)
    words = [int(''.join(map(str, bits[k:k + 32])), 2) for k in range(0, len(bits), 32)]
    return struct.pack(f'<{len(words)}I', *words)


def _parse(data, mode3):
    """Optimal parse (token costs in bits). Returns [(token, position)]."""
    n = len(data)
    match = {}
    for d in range(1, 257):
        eq = np.zeros(n, dtype=bool)
        if d < n:
            eq[d:] = data[d:] == data[:-d]
        match[d] = _run_lengths(eq)
    zero = _run_lengths(data == 0)
    lit_cost = 6 if mode3 else 9
    short_cost = 10 if mode3 else 11
    cost = [0] * (n + 1)
    choice = [None] * (n + 1)
    for i in range(n - 1, -1, -1):
        best, pick = cost[i + 1] + lit_cost, ('L', 1)
        if not mode3 and zero[i] >= 2:
            zl = int(zero[i])
            for ln in {min(zl, 129), min(zl, 1144) // 8 * 8}:
                if ln >= 2:
                    c = cost[i + ln] + 11
                    if c < best:
                        best, pick = c, ('Z', ln)
        for d in range(1, min(4, i) + 1):          # never reach back before the start
            ln = min(int(match[d][i]), 65)
            if ln >= 2:
                c = cost[i + ln] + short_cost
                if c < best:
                    best, pick = c, ('S', ln, d)
        for d in range(1, min(256, i) + 1):
            ln = min(int(match[d][i]), 258)
            if ln >= 3 and not (d == 1 and ln == 3):   # (1, 3) is the end marker
                c = cost[i + ln] + 18
                if c < best:
                    best, pick = c, ('M', ln, d)
        cost[i], choice[i] = best, pick
    tokens, i = [], 0
    while i < n:
        tokens.append((choice[i], i))
        i += choice[i][1]
    return tokens


CACHE_DIR = None    # set to a folder to keep compressed tiles between builds


def compress(pixels, bpp, palette=b'', mode3=False):
    """Build tile data from a (h, w) index array. mode3 needs values < 32."""
    if CACHE_DIR:
        import hashlib, os
        key = hashlib.sha1(pixels.astype(np.uint8).tobytes() + bytes([bpp, mode3])
                           + struct.pack('<2H', *pixels.shape) + palette).hexdigest()
        path = os.path.join(CACHE_DIR, key)
        if os.path.exists(path):
            with open(path, 'rb') as f:
                return f.read()
        tile = _compress(pixels, bpp, palette, mode3)
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(tile)
        return tile
    return _compress(pixels, bpp, palette, mode3)


def _compress(pixels, bpp, palette, mode3):
    h, w = pixels.shape
    a = pixels.astype(np.uint8).reshape(-1)
    raw = (a[0::2] | (a[1::2] << 4)) if bpp == 4 else a
    if mode3:
        assert raw.max() < 32, 'mode 3 holds at most 32 colours'
    bits, out, nib = [], bytearray(), []
    for (kind, ln, *d), i in _parse(raw, mode3):
        if kind == 'L':
            if mode3:
                bits += [0, int(raw[i]) >> 4]
                nib.append(int(raw[i]) & 15)
            else:
                bits.append(0)
                out.append(int(raw[i]))
        elif kind == 'M':
            bits += [1, 0]
            out += bytes([d[0] - 1, ln - 3])
        elif kind == 'S':
            bits += [1, 1] if mode3 else [1, 1, 0]
            out.append(((d[0] - 1) << 6) | (ln - 2))
        else:
            bits += [1, 1, 1]
            out.append(ln - 2 if ln <= 129 else 0x80 | (ln // 8 - 16))
    bits += [1, 0]
    out += b'\0\0'                                  # end marker
    flags = _pack_bits(bits)
    data = bytes(out) + bytes(-len(out) % 4)
    if mode3:
        nib += [0] * (-len(nib) % 8)
        nibbles = bytes(nib[k] | (nib[k + 1] << 4) for k in range(0, len(nib), 2))
        head = struct.pack('<8H', len(flags) + len(nibbles), 1 if palette else 0, bpp,
                           w, h, w, len(flags), 3)
        body = flags + nibbles + data
    else:
        head = struct.pack('<8H', len(flags), 1 if palette else 0, bpp, w, h, w, h, len(flags))
        body = flags + data
    tile = head + palette + body
    return tile + bytes(-len(tile) % 16)


def repack(texh_off, tiles, datas, rects=None, what=''):
    """Edits that store `datas` back to back where `tiles` were, and point
    their records at them (optionally with new rectangles)."""
    order = sorted(range(len(tiles)), key=lambda i: tiles[i]['data'])
    start = tiles[order[0]]['data']
    end = max(t['data'] + t['size'] for t in tiles)
    assert sum(t['size'] for t in tiles) == end - start, f'{what}: tiles are not contiguous'
    blob = bytearray()
    for i in order:
        rel = start + len(blob) - texh_off
        yield tiles[i]['record'] + 4, struct.pack('<III', rel, rel, len(datas[i])), f'{what} tile record'
        if rects:
            yield tiles[i]['record'] + 0x18, struct.pack('<4h', *rects[i]), f'{what} tile position'
        blob += datas[i]
    if start + len(blob) > end:
        raise ValueError(f'{what} grew by {start + len(blob) - end} bytes')
    yield start, bytes(blob).ljust(end - start, b'\0'), f'{what} ({len(tiles)} tiles)'
