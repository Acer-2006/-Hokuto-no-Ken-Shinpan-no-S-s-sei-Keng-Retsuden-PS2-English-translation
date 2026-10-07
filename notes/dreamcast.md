# Dreamcast conversion: technical notes

Source for the backport: the 2020 homebrew Dreamcast conversion of the
Atomiswave arcade game. These notes describe where things are; they contain
no game data.

## Disc layout (GDI)

| Track | LBA    | Contents |
|-------|--------|----------|
| 03    | 45000  | ISO9660 filesystem header, `0GDTEX.PVR`, then the arcade cart data stored raw (outside the filesystem) |
| 04    | 450000 | `1ST_READ.BIN` (the arcade program, unscrambled, load address `0x8C010000`) |

`tools/gdi_extract.py disc.gdi out/` pulls the two filesystem files out.

## Arcade data (track 03)

Raw, not in the filesystem. Made of `FARC` archives (342 of them):

```
FARC  u32 version(1)  u32 count  u32 ?
      u32 entry_offset[count]           (relative to FARC start)
      char name[]                       (often "null")
entry: char tag[4]  u32 data_offset  u32 size  u32 0
```

Common entry tags: `GIRT`/`GIRP`/`GIRA` (texture / palette / animation
resources), `GIDC`, `GIDS`, `GISV`. Other chunk magics seen nearby: `TEXH`,
`PALH`, `ANMH`, `COLH`, `SCRT`. Free space is padded with the string
"Hokuto for Atomiswave. ARC System Works co."

The PS2 port is by the same developer, so check whether it reuses `FARC`.

## Text in `1ST_READ.BIN`

All in-game text found so far is in the program file, Shift-JIS, null
terminated. `@` is a line break in the Japanese quotes.

| What | File offset | Count | Notes |
|------|-------------|-------|-------|
| English win quotes (arcade USA) | pointer table `0x13FC1C` | 50 | Generic per-character quotes. Some typos in the original English. |
| Japanese win quotes | pointer table `0x13436C` | 66 | Mostly matchup-specific (who you beat matters) |
| Japanese win quotes (Jagi extra) | pointer table `0x1344D4` | 9 | |
| Test/service menu | around `0x129000`–`0x12B000` | | Already English |
| Debug menus | around `0x126000`–`0x128000` | | Already English, not shown to players |

Pointer value = file offset + `0x8C010000`.

**The English and Japanese quote sets don't line up 1:1.** The US arcade
replaced the matchup-specific Japanese quotes with a smaller set of generic
ones. Backporting covers what exists; the extra Japanese lines need new
translations (or reuse the character's generic English quote).

`tools/dc_dump_quotes.py` dumps both sets to `work/` (gitignored).
