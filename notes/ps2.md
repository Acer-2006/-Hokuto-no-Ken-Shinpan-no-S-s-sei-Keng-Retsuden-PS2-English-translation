# PS2 version (SLPM-66660): technical notes

Clean dump check: the full ISO's CRC32 is `A77EEDB6` (matches the known good
dump). PCSX2 game CRC: `9E8F0454`.

## Disc contents

| File | Size | What |
|------|------|------|
| `SLPM_666.60` | 2.0 MB | Main program (MIPS ELF, loads at `0x100000`, file offset = address − `0x100000` + `0x80`) |
| `DATA/HK_B.BIN` | 611 MB | All game data. Same name and archive format (`FARC`) as the arcade data |
| `DATA/HK_I.IDX` | 6.5 KB | Top-level `FARC` index for `HK_B.BIN` |
| `MODULES/*` | | Sony IOP modules |

The other ~4 GB of the ISO is padding.

## The arcade's English mode is still in the program

- All 50 English win quotes from the overseas arcade release are present.
  Pointer table at address `0x2D77F0`, indexed `character * 5 + n`.
- The function at `0x1B4190` returns "is this the overseas version?". It reads
  a region byte (`lbu -0x79D6($gp)` in `0x28EA60`) that is never set on PS2,
  so it always returns 0 (Japan).
- It is checked in **39 places** (win quotes, menus, title text, etc.).
- Win quote checks: `0x1AC03C` and `0x1ACB7C` (`jal 0x1B4190`, `nop` delay slot).

`patches/SLPM-66660_9E8F0454.pnach` has two PCSX2 test patches:
- **Test A**: `0x1B4190` → `jr ra / li v0,1` (whole game overseas mode)
- **Test B**: the two quote checks → `li v0,1` (quotes only)

## Training mode move names

Not stored as text anywhere (no Shift-JIS move names in the program or in
`HK_B.BIN`). They are images in `HK_B.BIN`, so they need graphics editing,
not a VWF.

## Data formats seen in HK_B.BIN

- `FARC` archives (361, vs 342 in the arcade data). Small header blocks with
  `GIRP`/`GIRT`/`GIRA` (palette/texture/anim resource) pointers.
- `TEXH` texture banks (416). Example at `0x800`: 544 entries, entry headers
  describe 64×64 tiles plus rectangles, pixel data starts at bank + `0x33F80`.
- `PALH` palette banks (327): 32-colour, 16-bit palettes.
- `ANMH`, `COLH` (animation, collision).

Byte-for-byte comparison with the arcade data doesn't work: the PS2 stores its
textures in a PS2-specific layout, so every archive differs.
