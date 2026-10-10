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

## PS2-only text (translated in translation/)

| Block | File offset | Layout |
|-------|-------------|--------|
| Timeline ("Kengo Retsuden") | `0x1E73E4` | 232 entries × 100 bytes: line1[48], line2[48], u32 tag. Fixed layout, so English is limited to 47 bytes per line |
| Gallery pointer table | `0x1ECEF0` | pointers to 77 captions + 7 episode titles |
| Save message pointer table | `0x1F9A3C` | pointers to 30 messages |
| Gallery/episode strings | `0x1F9DD0`–`0x1FAD8C` | repacked by `tools/insert_text.py` |
| Save message strings | `0x1F9510`–`0x1F9884`, plus slots near `0x1F99D0` | repacked |

`tools/ps2_dump_text.py` dumps the Japanese (to a gitignored folder).
`tools/insert_text.py` writes the English and makes a PCSX2 preview section.
Strings are 4-byte aligned after repacking.

## Text renderer (HISTORY rows and the gallery viewer)

| Address | What |
|---|---|
| `0x25E320` | `set_text(line, str)`: glyph count = strlen/2, one glyph per 2 bytes |
| `0x25E420` | Shift-JIS → font tile: `(lead-0x81)*188 + trail` for 0x81–0x9F, `0x16C4 + (lead-0xE0)*188 + trail` for 0xE0–0xFC; anything else (ASCII) → tile 0, blank |
| `0x25E070` | uploads each glyph: font base (`gp-0x7928`) + tile × 64 |
| `0x25D7D0` | draws a line, 16 px per tile; `＆` (`0x8197`) is a line break |
| `0x25ED10` | loads the font: 0xC0000 bytes from the `GIFT` resource (`HK_B.BIN` `0x73C3800`) |

Font tiles are 16×16, 2 bits per pixel (64 bytes: 16 rows, each a
little-endian u32, pixel k in bits 2k–2k+1). Levels 0–3 = transparent, dark
grey, light grey, white.

Plain ASCII never shows up, and full-width English (`Ｋｅｎｓｈｉｒｏ`) fits
only ~19 letters in a HISTORY row. The 2444 tiles behind Shift-JIS lead
bytes 0xF0–0xFC are blank, so `tools/pairfont.py` draws two 8-pixel letters
into each of them and gives every letter pair the translation uses its own
code. No code changes; the text stays the same length; a row holds 38
letters per line (the width of the row's box). `tools/build_iso.py` writes
the tiles (about 650 are used) into the copy of `HK_B.BIN`.

The HISTORY data table starts at `0x2E71D0` (4 blank entries before the
first one dumped), 100 bytes per entry: type byte, flag/picture id byte,
2 bytes, then the two 48-byte lines. Type 1 rows (quotes) stay hidden ("?")
until the matching "cleared" flag is set (`0x398E80`, 77 bytes, copied into
the HISTORY state at `+0x1C0`). The gallery viewer for a row shows both
lines, an episode title (`0x2ECFB0` table), the caption (`0x2ECE70` table)
and a button help bar (`0x2FB300`, laid out to line up with the icons).

The cute save messages (`0x2F9990` and `0x2FB8E0` tables) are only checked
for non-zero; nothing draws them.

## Resource tables in HK_I.IDX

Same 18 tables as the arcade. Each: tag, count, (group offset, size), then
(offset, size) pairs pointing into HK_B.BIN.

- `GIS2` (system UI): 46 resources. Data blobs at entries 0–45, their FARC
  headers at entries 46–91. Training mode screens should be among these.
- `GIFT` (font): FARC at `0x73C2800` + 0xC0800-byte bank at `0x73C3000`,
  probably the Japanese font the menus use.
- `GICP`: 73 portrait/cut-in resources.

A resource = FARC header (`GIRP`/`GIRT`/`GIRA` = offset/size of the PALH,
TEXH and ANMH parts) followed by the data blob.

## Texture format (TEXH), partly decoded

```
TEXH  u32 size  u16 ver(4)  u16 flags  u32 count  u32 pixel_size  u32 pixel_start  ...
      u32 entry_offset[count]              (relative to TEXH)
entry: u16 flags  u16 tile_count  u16 width  u16 height  8 bytes 0
       tile[tile_count] (32 bytes each):
         u32 -1  u32 ?  u32 fmt(0x64821)  u32 data_off  u32 data_off  u32 data_size
         u32 -1  u16 tile_w  u16 tile_h  u16 x0 y0 x1 y1 ...
```

Each 64×64 tile is compressed. Tile header: `u32 0x88, u16 8 (bpp), u16 w,
u16 h, u16 w, u16 h, u16 0`, then a bitstream. The decompressor is not found
yet. `0x25F230` only fixes up pointers when a bank is loaded, and `0x2BFA00`
is input code, not the decompressor.
