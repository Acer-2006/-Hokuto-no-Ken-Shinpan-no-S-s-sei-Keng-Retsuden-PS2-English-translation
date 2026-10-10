"""List / extract an ISO9660 image (PS2 DVD). usage: iso_list.py image.iso [out_dir]"""
import os, struct, sys


def list_files(iso):
    """{path: (lba, size)} for every file on the disc."""
    files = {}
    with open(iso, 'rb') as f:
        def read(lba, n):
            f.seek(lba * 2048)
            return f.read(n)
        pvd = read(16, 2048)
        assert pvd[1:6] == b'CD001', 'not an ISO9660 image'
        root = pvd[156:190]

        def walk(lba, size, path):
            buf = read(lba, size)
            i = 0
            while i < len(buf):
                l = buf[i]
                if l == 0:
                    i = (i // 2048 + 1) * 2048
                    continue
                rec = buf[i:i + l]
                i += l
                elba, esz = struct.unpack('<I', rec[2:6])[0], struct.unpack('<I', rec[10:14])[0]
                name = rec[33:33 + rec[32]]
                if name in (b'\0', b'\1'):
                    continue
                p = os.path.join(path, name.decode('ascii', 'replace').split(';')[0])
                if rec[25] & 2:
                    walk(elba, esz, p)
                else:
                    files[p] = (elba, esz)
        walk(struct.unpack('<I', root[2:6])[0], struct.unpack('<I', root[10:14])[0], '')
    return files


def main(iso, out=None):
    files = list_files(iso)
    with open(iso, 'rb') as f:
        for p, (lba, size) in sorted(files.items(), key=lambda x: -x[1][0]):
            print(f'{lba:8d} {size:11d} {p}')
            if out:
                os.makedirs(os.path.join(out, os.path.dirname(p)), exist_ok=True)
                with open(os.path.join(out, p), 'wb') as g:
                    f.seek(lba * 2048)
                    left = size
                    while left:
                        c = f.read(min(left, 1 << 24))
                        g.write(c)
                        left -= len(c)


if __name__ == '__main__':
    main(*sys.argv[1:])
