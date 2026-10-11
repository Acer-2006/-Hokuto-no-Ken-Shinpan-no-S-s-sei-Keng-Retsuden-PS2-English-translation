# Fonts

The build draws the English text with these fonts, so every build gets the
same result whatever is installed on the computer.

| File | From | Licence |
|---|---|---|
| `NotoSansCJKjp-Regular-Latin.otf` | Noto Sans CJK JP Regular 2.004 | SIL OFL 1.1 (`OFL.txt`) |
| `NotoSansCJKjp-Bold-Latin.otf` | Noto Sans CJK JP Bold 2.004 | SIL OFL 1.1 (`OFL.txt`) |
| `NotoSerifCJKjp-SemiBold-Latin.otf` | Noto Serif CJK JP SemiBold 2.002 | SIL OFL 1.1 (`OFL.txt`) |
| `NotoSerifCJKjp-Bold-Latin.otf` | Noto Serif CJK JP Bold 2.002 | SIL OFL 1.1 (`OFL.txt`) |
| `NotoSerifCJKjp-Black-Latin.otf` | Noto Serif CJK JP Black 2.002 | SIL OFL 1.1 (`OFL.txt`) |
| `LiberationSerif-Regular.ttf` | Liberation Serif 2.1.5, unmodified | SIL OFL 1.1 (`OFL.txt`) |
| `DejaVuSansMono.ttf` | DejaVu Sans Mono 2.37, unmodified | Bitstream Vera licence (`LICENSE-DejaVu.txt`) |

The Noto files are subsets holding only the Latin characters (U+0020-007E,
U+00A0-00FF, U+2010-2027, U+2030-2033), made with fontTools:

```
pyftsubset NotoSerifCJK-Bold.ttc --font-number=0 \
  --unicodes="U+0020-007E,U+00A0-00FF,U+2010-2027,U+2030-2033" \
  --layout-features='*' --name-IDs='*' --name-languages='*' \
  --output-file=NotoSerifCJKjp-Bold-Latin.otf
```

Sources: https://github.com/notofonts/noto-cjk, https://github.com/liberationfonts
and https://dejavu-fonts.github.io/
