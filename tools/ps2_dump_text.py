"""Dump the PS2-only text blocks (timeline, gallery, save messages) from SLPM_666.60.

Output goes to an out_dir that should stay out of git (it contains the game's
original Japanese text). usage: ps2_dump_text.py SLPM_666.60 out_dir
"""
import json, os, struct, sys

TL_START, TL_STRIDE = 0x1E73E4, 0x64      # timeline entries: line1[0x30] line2[0x30] tag(u32)
TL_FIELDS = [('line1', 0x00, 0x30), ('line2', 0x30, 0x30)]

def cstr(d, o, n):
    raw = d[o:o + n].split(b'\0')[0]
    return raw.decode('cp932')

def timeline(d):
    recs = []
    o = TL_START
    while True:
        try:
            l1 = cstr(d, o, 0x30)
        except UnicodeDecodeError:
            break
        if not l1 and not cstr(d, o + 0x30, 0x30) and d[o + 0x60:o + 0x64] == b'\0' * 4:
            break
        tag = d[o + 0x60:o + 0x64].hex()
        rec = {'id': f'TL{len(recs):03d}', 'offset': o, 'tag': tag}
        for name, off, size in TL_FIELDS:
            rec[name] = cstr(d, o + off, size)
            rec[name + '_max_bytes'] = size - 1
        recs.append(rec)
        o += TL_STRIDE
    return recs

def strings_in(d, lo, hi):
    out, i = [], lo
    while i < hi:
        if d[i] == 0:
            i += 1; continue
        j = d.index(b'\0', i)
        raw = d[i:j]
        try:
            t = raw.decode('cp932')
            if any('぀' <= c <= '鿿' or '＀' <= c <= '￯' for c in t):
                # room = bytes until the next non-zero byte (in-place budget)
                k = j
                while k < hi and d[k] == 0: k += 1
                out.append({'offset': i, 'text': t, 'bytes': len(raw), 'room': k - i - 1})
        except UnicodeDecodeError:
            pass
        i = j + 1
    return out

if __name__ == '__main__':
    d = open(sys.argv[1], 'rb').read()
    out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    tl = timeline(d)
    json.dump(tl, open(os.path.join(out, 'timeline_jp.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    sysmsg = strings_in(d, 0x1F9400, 0x1FAD80)
    json.dump(sysmsg, open(os.path.join(out, 'ps2_sys_jp.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('timeline records:', len(tl), 'system/gallery strings:', len(sysmsg))
