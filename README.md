# Hokuto-no-Ken-Shinpan-no-Sōsōsei-Kengō-Retsuden-PS2-English-translation
Hokuto no Ken: Shinpan no Sōsōsei Kengō Retsuden English translation, aims to translate the game by backporting the English from the Dreamcast version

<img width="265" height="376" alt="image" src="https://github.com/user-attachments/assets/a12d91c0-cce2-44cd-9cf8-a91af6edbebb" />


<img width="960" height="240" alt="image" src="https://github.com/user-attachments/assets/468a6471-0cac-461f-9aa2-fd549fdea043" />


## Building the patched disc

You need your own dump of the Japanese PS2 disc (SLPM-66660) and Python 3
with Pillow and NumPy (`pip install pillow numpy`).

```
python tools/build_iso.py "your-original.iso" "Hokuto no Ken (English).iso"
```

The script checks that the disc is the retail release, copies it, and
patches the copy: English (overseas) mode on, the translated HISTORY
timeline, gallery captions and episode titles, and the extra font tiles
they need. Japanese drawn into pictures is redrawn in English from your
disc's own graphics: the HISTORY chapter labels, the training-mode command
lists, the HISTORY unlock notices, the memory card messages and the sound
test names. Nothing from the game is included in this repository.

The first build takes a few minutes (the pictures are re-compressed); the
results are cached in a `.tile-cache` folder next to the output, so later
builds are quicker. The fonts used for the English are in `fonts/` (open
licences, see `fonts/README.md`), so the result doesn't depend on what's
installed on your computer.
