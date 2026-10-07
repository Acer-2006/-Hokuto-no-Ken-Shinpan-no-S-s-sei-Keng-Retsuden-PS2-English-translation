"""List / extract an ISO9660 image (PS2 DVD). usage: iso_list.py image.iso [out_dir]"""
import os, struct, sys

def main(iso, out=None):
    f = open(iso, 'rb')
    def read(lba, n):
        f.seek(lba * 2048); return f.read(n)
    pvd = read(16, 2048)
    assert pvd[1:6] == b'CD001'
    print('volume:', pvd[40:72].decode('ascii', 'replace').strip())
    root = pvd[156:190]
    def walk(lba, size, path):
        buf = read(lba, size); i = 0
        while i < len(buf):
            l = buf[i]
            if l == 0:
                i = (i // 2048 + 1) * 2048; continue
            rec = buf[i:i+l]; i += l
            elba, esz = struct.unpack('<I', rec[2:6])[0], struct.unpack('<I', rec[10:14])[0]
            name = rec[33:33+rec[32]]
            if name in (b'\0', b'\1'): continue
            name = name.decode('ascii', 'replace').split(';')[0]
            p = os.path.join(path, name)
            if rec[25] & 2:
                if out: os.makedirs(os.path.join(out, p), exist_ok=True)
                walk(elba, esz, p)
            else:
                print(f'{elba:8d} {esz:11d} {p}')
                if out:
                    with open(os.path.join(out, p), 'wb') as g:
                        f.seek(elba * 2048); left = esz
                        while left:
                            c = f.read(min(left, 1 << 24)); g.write(c); left -= len(c)
    walk(struct.unpack('<I', root[2:6])[0], struct.unpack('<I', root[10:14])[0], '')

if __name__ == '__main__':
    main(*sys.argv[1:])
