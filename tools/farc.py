"""Helpers for the FARC archives used by both the arcade/Dreamcast and PS2 data."""
import re, struct

def parse_farc(d, o):
    if d[o:o+4] != b'FARC': return None
    n = struct.unpack_from('<I', d, o + 8)[0]
    if not 0 < n < 500: return None
    offs = struct.unpack_from(f'<{n}I', d, o + 0x10)
    name = d[o + 0x10 + 4*n: o + 0x10 + 4*n + 0x20].split(b'\0')[0].decode('latin1')
    ents = []
    for e in offs:
        tag, eo, es = struct.unpack_from('<4sII', d, o + e)
        ents.append((tag.decode('latin1'), eo, es))
    return {'off': o, 'name': name, 'entries': ents, 'end': max(eo + es for _, eo, es in ents)}

def all_farcs(d):
    out = []
    for m in re.finditer(rb'FARC\x01\x00\x00\x00', d):
        f = parse_farc(d, m.start())
        if f: out.append(f)
    return out
