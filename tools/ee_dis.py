"""Word-by-word disassembler for PS2 EE code (falls back to raw hex for EE-only opcodes)."""
import capstone, struct
VA, FO = 0x100000, 0x80
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS64 + capstone.CS_MODE_LITTLE_ENDIAN)
def dis(ps, a, b, mark=None):
    out = []
    for addr in range(a, b, 4):
        w = ps[addr - VA + FO: addr - VA + FO + 4]
        ins = list(md.disasm(w, addr))
        op = int.from_bytes(w, 'little') >> 26
        if op == 0x1f: txt = f'sq       {(int.from_bytes(w,"little")>>16)&31}, {int.from_bytes(w,"little")&0xffff:#x}(r{(int.from_bytes(w,"little")>>21)&31})'
        elif op == 0x1e: txt = f'lq       {(int.from_bytes(w,"little")>>16)&31}, {int.from_bytes(w,"little")&0xffff:#x}(r{(int.from_bytes(w,"little")>>21)&31})'
        elif ins: txt = f'{ins[0].mnemonic:8s} {ins[0].op_str}'
        else: txt = f'.word {int.from_bytes(w, "little"):#010x}'
        out.append(f'{">>" if addr == mark else "  "} {addr:08x}: {txt}')
    return '\n'.join(out)
