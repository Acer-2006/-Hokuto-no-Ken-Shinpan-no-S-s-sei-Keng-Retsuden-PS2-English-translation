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
they need. Nothing from the game is included in this repository.
