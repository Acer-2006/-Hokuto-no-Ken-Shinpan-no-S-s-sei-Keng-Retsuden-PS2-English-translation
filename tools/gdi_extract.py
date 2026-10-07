"""Extract the ISO9660 filesystem from a Dreamcast GDI (2048-byte data tracks)."""
import os, sys, struct

def main(gdi_path, out_dir):
    base = os.path.dirname(gdi_path)
    lines = open(gdi_path).read().split('\n')[1:]
    tracks = []
    for ln in lines:
        p = ln.split()
        if len(p) >= 5:
            tracks.append((int(p[1]), int(p[3]), os.path.join(base, p[4])))
    data = [(lba, sz, open(f, 'rb')) for lba, sz, f in tracks if sz == 2048]
    data.sort()
    def read(lba, n):
        out = b''
        while n > 0:
            trk = [t for t in data if t[0] <= lba][-1]
            off = (lba - trk[0]) * 2048
            trk[2].seek(off)
            chunk = trk[2].read(min(n, 2048))
            if not chunk:
                chunk = b'\0' * min(n, 2048)
            out += chunk
            n -= len(chunk)
            lba += 1
        return out
    hd = [t for t in data if t[0] >= 45000][0][0]
    pvd = read(hd + 16, 2048)
    assert pvd[1:6] == b'CD001', pvd[:8]
    root = pvd[156:156+34]
    def walk(lba, size, path):
        buf = read(lba, size)
        i = 0
        while i < len(buf):
            l = buf[i]
            if l == 0:
                i = (i // 2048 + 1) * 2048
                continue
            rec = buf[i:i+l]
            elba = struct.unpack('<I', rec[2:6])[0]
            esz = struct.unpack('<I', rec[10:14])[0]
            flags = rec[25]
            nl = rec[32]
            name = rec[33:33+nl]
            i += l
            if name in (b'\0', b'\1'):
                continue
            name = name.decode('ascii', 'replace').split(';')[0]
            p = os.path.join(path, name)
            if flags & 2:
                os.makedirs(os.path.join(out_dir, p), exist_ok=True)
                walk(elba, esz, p)
            else:
                with open(os.path.join(out_dir, p), 'wb') as f:
                    f.write(read(elba, esz))
                print(f'{elba:7d} {esz:10d} {p}')
    walk(struct.unpack('<I', root[2:6])[0], struct.unpack('<I', root[10:14])[0], '')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
