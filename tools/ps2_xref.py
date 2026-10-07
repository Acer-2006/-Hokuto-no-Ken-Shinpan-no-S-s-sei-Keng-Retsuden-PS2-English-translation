"""Find MIPS lui/lo16 references to a virtual address in a PS2 ELF and disassemble around them."""
import struct, sys, capstone
VA, FO = 0x100000, 0x80
ps = open(sys.argv[1], 'rb').read()
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS64 + capstone.CS_MODE_LITTLE_ENDIAN)
def refs(target):
    hi = (target + 0x8000) >> 16; lo = target & 0xffff
    out = []
    code_end = 0x1c0000  # rough end of .text
    for i in range(FO, code_end, 4):
        w = struct.unpack_from('<I', ps, i)[0]
        if (w >> 26) == 0x0f and (w & 0xffff) == hi:   # lui
            rt = (w >> 16) & 31
            for k in range(1, 12):
                w2 = struct.unpack_from('<I', ps, i + 4 * k)[0]
                op = w2 >> 26
                if (w2 & 0xffff) == lo and ((w2 >> 21) & 31) == rt and op in (0x09, 0x23, 0x2b, 0x37, 0x3f, 0x21, 0x25, 0x24, 0x20):
                    out.append((i, i + 4 * k)); break
    return out
def dis(fo, before=12, after=20):
    start = fo - 4 * before
    for ins in md.disasm(ps[start:start + 4 * (before + after)], start - FO + VA):
        mark = '>>' if ins.address == fo - FO + VA else '  '
        print(f'{mark} {ins.address:08x}: {ins.mnemonic:8s} {ins.op_str}')
if __name__ == '__main__':
    for t in sys.argv[2:]:
        t = int(t, 16)
        r = refs(t)
        print(f'== refs to {t:#x}: {len(r)}')
        for a, b in r:
            print(f'-- lui at va {a - FO + VA:#x}')
            dis(a)
