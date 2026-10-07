"""Dump the win-quote tables from the Dreamcast/Atomiswave program (1ST_READ.BIN).

Writes TSV files to an output folder that is gitignored (work/ by default).
Nothing from the game goes into the repo.

usage: python tools/dc_dump_quotes.py path/to/1ST_READ.BIN [out_dir]
"""
import os, struct, sys

LOAD_ADDR = 0x8C010000          # where 1ST_READ.BIN is loaded in Dreamcast RAM
EN_TABLE = (0x13FC1C, 50)       # English win quotes (arcade USA), flat pointer list
JP_TABLES = [(0x13436C, 66),    # Japanese win quotes, mostly matchup-specific
             (0x1344D4, 9)]


def read_cstr(data, off):
    end = data.index(b"\0", off)
    return data[off:end]


def dump(data, start, count, encoding):
    rows = []
    for i in range(count):
        slot = start + 4 * i
        ptr = struct.unpack_from("<I", data, slot)[0]
        if not (LOAD_ADDR <= ptr < LOAD_ADDR + len(data)):
            rows.append((i, slot, 0, ""))
            continue
        off = ptr - LOAD_ADDR
        text = read_cstr(data, off).decode(encoding, "replace")
        rows.append((i, slot, off, text.replace("\t", " ")))
    return rows


def main():
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "work"
    os.makedirs(out, exist_ok=True)
    data = open(src, "rb").read()
    with open(os.path.join(out, "dc_quotes_en.tsv"), "w", encoding="utf-8") as f:
        f.write("index\tptr_slot\ttext_offset\ttext\n")
        for r in dump(data, *EN_TABLE, "cp932"):
            f.write(f"{r[0]}\t{r[1]:#x}\t{r[2]:#x}\t{r[3]}\n")
    with open(os.path.join(out, "dc_quotes_jp.tsv"), "w", encoding="utf-8") as f:
        f.write("table\tindex\tptr_slot\ttext_offset\ttext\n")
        for t, (start, count) in enumerate(JP_TABLES):
            for r in dump(data, start, count, "cp932"):
                # '@' is the game's line-break code
                f.write(f"{t}\t{r[0]}\t{r[1]:#x}\t{r[2]:#x}\t{r[3]}\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
