"""Build the English disc from your own copy of the game.

usage: build_iso.py [--unlock-history] original.iso out.iso [translation_dir]

Copies the ISO, then patches it in place (file sizes and positions don't
change):
  - SLPM_666.60: overseas (English) mode on, plus all translated text
  - DATA/HK_B.BIN: letter-pair tiles added to the blank part of the font,
    and English versions of Japanese text drawn in textures (images.py)

--unlock-history (for testing) treats every HISTORY mission as cleared, so
all quote rows and gallery pictures can be viewed without playing them.

Nothing from the game is stored in this repository; the script only works
on the ISO you give it, and checks that it's an unmodified dump first.
"""
import hashlib, mmap, os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iso_list import list_files
from insert_text import patch_program
from pairfont import HalfWidthFont, FONT_GLYPHS
import images

ELF = 'SLPM_666.60'
DATA = 'DATA/HK_B.BIN'
ELF_SHA1 = '386cf62c6b04177f563c3f12c88566d1239c177a'   # retail SLPM-66660
FONT_TILES = 0x73C3000 + 0x800    # GIFT font texture inside HK_B.BIN

VA_BASE, FILE_BASE = 0x100000, 0x80
CODE_PATCHES = {
    # "is this the overseas version?" (0x1B4190) -> always yes: jr ra / li v0,1
    0x1B4190: 0x03E00008,
    0x1B4194: 0x24020001,
}
UNLOCK_HISTORY = {
    # HISTORY setup copies the 77 "mission cleared" flags; skip the check so
    # every flag is set (0x2A8CD8: bne v0,a0 -> nop)
    0x2A8CD8: 0x00000000,
}


def copy_iso(src, dst):
    try:   # keep the 4 GB of padding sparse where the platform allows it
        subprocess.run(['cp', '--sparse=always', src, dst], check=True)
    except (OSError, subprocess.CalledProcessError):
        shutil.copyfile(src, dst)


def main():
    args = sys.argv[1:]
    unlock = '--unlock-history' in args
    args = [a for a in args if a != '--unlock-history']
    if len(args) < 2:
        sys.exit(__doc__)
    src, dst = args[:2]
    tdir = args[2] if len(args) > 2 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'translation')

    files = list_files(src)
    elf_lba, elf_size = files[ELF]
    data_lba, data_size = files[DATA]
    with open(src, 'rb') as f:
        f.seek(elf_lba * 2048)
        orig = f.read(elf_size)
    if hashlib.sha1(orig).hexdigest() != ELF_SHA1:
        sys.exit(f'{ELF} does not match the retail disc (already patched, or a different release?)')

    prog, pairs, (used, total) = patch_program(orig, tdir)
    patches = {**CODE_PATCHES, **(UNLOCK_HISTORY if unlock else {})}
    for va, word in patches.items():
        struct.pack_into('<I', prog, va - VA_BASE + FILE_BASE, word)
    assert len(prog) == elf_size

    font = HalfWidthFont()
    tiles = pairs.tiles(font)
    print(f'text: {used}/{total} string bytes, {len(pairs.codes)} letter-pair tiles')

    with open(src, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        hk_b = memoryview(mm)[data_lba * 2048:data_lba * 2048 + data_size]
        edits = [(t['data'], t['size'], new, desc) for t, new, desc in images.replacements(hk_b)]
        del hk_b
        mm.close()
    print(f'images: {len(edits)} textures replaced')

    copy_iso(src, dst)
    with open(dst, 'r+b') as f:
        f.seek(elf_lba * 2048)
        f.write(prog)
        base = data_lba * 2048 + FONT_TILES
        for idx, data in tiles:
            assert idx < FONT_GLYPHS
            f.seek(base + idx * 64)
            if any(f.read(64)):
                sys.exit(f'font tile {idx} is not blank; unexpected HK_B.BIN')
            f.seek(base + idx * 64)
            f.write(data)
        for off, old_size, new, desc in edits:
            assert len(new) <= old_size, desc
            f.seek(data_lba * 2048 + off)
            f.write(new.ljust(old_size, b'\0'))
    print(f'wrote {dst}')


if __name__ == '__main__':
    main()
