"""Simplified Chinese text for Red Alert 2, made from your own Chinese copy.

    python3 -I scripts/make_zh_hans.py <Chinese LANGUAGE.MIX> <game dir> [<YR translation>]

Takes the string table (RA2.CSF) of a Traditional Chinese Red Alert 2
1.006 (its LANGUAGE.MIX), converts every string to Simplified Chinese with
mainland wording (OpenCC's tw2sp: brew install opencc) and writes it into
<game dir> as RA2.CSF, which the game reads before the one in its own
LANGUAGE.MIX; the launcher sees the Chinese table and uses the Simplified
Chinese code page (src/ra2/main.cpp).

The game font (GAME.FNT in RA2.MIX's LOCAL.MIX, the same in every
language: 1 bit a pixel, 16 rows of 24, a width byte first; glyph n is
the (n-1)th record, 0 is none) maps every
CJK ideograph, but those outside Big5 (most simplified ones) to one
placeholder glyph. Those of GB2312 are drawn from a system font (STHeiti
Light, 15 px, like the font's own) and added; the font goes into <game
dir> as GAME.FNT too.

When <game dir> holds Yuri's Revenge too (LANGMD.MIX), its string table
is written as RA2MD.CSF, which it reads the same way: every string whose
English is Red Alert 2's (most of them: the shared units, buildings and
menus) in the Chinese one's words, those that only say "Yuri's Revenge"
where Red Alert 2's said "Red Alert 2" likewise with the name changed, and
the rest (Yuri's side, the expansion's missions and menus) left in
English, or taken from <YR translation> when given: a JSON array of
[label, index, text] in Simplified Chinese (your own translation of your
copy's strings; like the output, never commit or share it). It uses the
same GAME.FNT.

Delete RA2.CSF, RA2MD.CSF and GAME.FNT from <game dir> to go back to the
install's own language. The output is made from your files: never commit or share
it.
"""

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csf  # noqa: E402
import mixls  # noqa: E402

# Newlines inside strings go through OpenCC as this private-use character,
# so that one string is one line.
NEWLINE = '\ue000'

# Westwood's public key for encrypted MIX headers, read from the player's own
# game.exe in <game dir> (mixls.public_key); set in main.
PUBLIC_KEY = None

FONT = '/System/Library/Fonts/STHeiti Light.ttc'
GLYPH_PX = 15  # the width and height of the font's own CJK glyphs


def member(data, name, where):
    entry = mixls.parse(data, PUBLIC_KEY).get(mixls.mix_id(name))
    if not entry:
        sys.exit(f'{where} has no {name}')
    off, size = entry
    return data[off:off + size]


def table_from_mix(path, name='RA2.CSF'):
    return csf.parse(member(Path(path).read_bytes(), name, path))


def in_dir(game_dir, name):
    """The file `name` in game_dir, in whatever case it is spelled there."""
    for f in Path(game_dir).iterdir():
        if f.name.lower() == name.lower():
            return f
    sys.exit(f'{game_dir} has no {name}')


def draw_glyph(font, ch):
    """`ch` as the font's glyph record: width, then 16 rows of 3 bytes."""
    from PIL import Image, ImageDraw
    im = Image.new('L', (24, 16), 0)
    left, top, right, bottom = font.getbbox(ch)
    x = (GLYPH_PX - (right - left)) // 2 - left
    y = 1 + (GLYPH_PX - (bottom - top)) // 2 - top
    ImageDraw.Draw(im).text((x, y), ch, fill=255, font=font)
    rows = bytearray()
    for py in range(16):
        bits = 0
        for px in range(24):
            bits = bits << 1 | (im.getpixel((px, py)) >= 110)
        rows += bits.to_bytes(3, 'big')
    return bytes([GLYPH_PX]) + bytes(rows)


def font_with_simplified(fnt):
    from PIL import ImageFont
    magic, field, row_bytes, rows, line, count, glyph_size = struct.unpack_from('<4s6I', fnt, 0)
    if magic != b'fonT' or (row_bytes, rows, glyph_size) != (3, 16, 49):
        sys.exit(f'GAME.FNT: unexpected format {magic} {row_bytes}x{rows}, {glyph_size} a glyph')
    cmap = list(struct.unpack_from('<65536H', fnt, 28))
    placeholder = cmap[0x9879]  # 项, outside Big5
    gb2312 = [bytes([hi, lo]).decode('gb2312', 'ignore') for hi in range(0xB0, 0xF8)
              for lo in range(0xA1, 0xFF)]
    missing = sorted({ch for ch in gb2312 if ch and cmap[ord(ch)] in (0, placeholder)})
    font = ImageFont.truetype(FONT, GLYPH_PX)
    glyphs = bytearray(fnt[28 + 131072:])
    for i, ch in enumerate(missing):
        cmap[ord(ch)] = count + 1 + i
        glyphs += draw_glyph(font, ch)
    header = struct.pack('<4s6I', magic, field, row_bytes, rows, line, count + len(missing),
                         glyph_size)
    return header + struct.pack('<65536H', *cmap) + bytes(glyphs), len(missing)


def write_into(game_dir, name, data):
    out = Path(game_dir) / name
    with tempfile.NamedTemporaryFile(dir=out.parent, delete=False) as t:
        t.write(data)
    Path(t.name).replace(out)
    return out


def to_simplified(texts):
    joined = '\n'.join(t.replace('\n', NEWLINE) for t in texts)
    try:
        r = subprocess.run(['opencc', '-c', 'tw2sp.json'], input=joined, capture_output=True,
                           text=True, check=True)
    except FileNotFoundError:
        sys.exit('opencc not found: brew install opencc')
    out = r.stdout.split('\n')
    if out and out[-1] == '' and len(out) == len(texts) + 1:
        out.pop()
    if len(out) != len(texts):
        sys.exit(f'opencc returned {len(out)} strings for {len(texts)}')
    return [t.replace(NEWLINE, '\n') for t in out]


# Red Alert 2's name in the table's strings (in Simplified Chinese), and
# Yuri's Revenge's.
RA2_TITLE_ZH = '红色警戒 2'
YR_TITLE_ZH = '尤里的复仇'


def yuri_table(game_dir, zh, extra):
    """Yuri's Revenge's English table (LANGMD.MIX's RA2MD.CSF) with the
    strings it shares with Red Alert 2 (LANGUAGE.MIX's RA2.CSF) taken from
    `zh`, Red Alert 2's table in Simplified Chinese (label -> texts); the
    counts of strings it changed and kept. `extra` ((label, index) ->
    text, labels in lower case) comes first: the strings `zh` lacks or
    has in English."""
    yr = table_from_mix(in_dir(game_dir, 'LANGMD.MIX'), 'RA2MD.CSF')
    en = {name.lower(): values
          for name, values in table_from_mix(in_dir(game_dir, 'LANGUAGE.MIX'))['labels']}
    zh = {name.lower(): texts for name, texts in zh.items()}
    changed = kept = 0
    labels = []
    for name, values in yr['labels']:
        key = name.lower()
        out = []
        for i, (text, sound) in enumerate(values):
            ra2 = en.get(key, [])
            ra2_text = ra2[i][0] if i < len(ra2) else None
            ra2_zh = zh[key][i] if key in zh and i < len(zh[key]) else None
            if (key, i) in extra:
                text, changed = extra[(key, i)], changed + 1
            elif ra2_zh is not None and ra2_text == text:
                text, changed = ra2_zh, changed + 1
            elif (ra2_zh is not None and ra2_text is not None and
                  ra2_text.replace('Red Alert 2', "Yuri's Revenge") == text and
                  RA2_TITLE_ZH in ra2_zh):
                text, changed = ra2_zh.replace(RA2_TITLE_ZH, YR_TITLE_ZH), changed + 1
            else:
                kept += 1
            out.append((text, sound))
        labels.append((name, out))
    yr['labels'] = labels
    yr['language'] = csf.LANGUAGE_CHINESE
    return yr, changed, kept


def main():
    global PUBLIC_KEY
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__.strip().split('\n\n')[1])
    PUBLIC_KEY = mixls.public_key(sys.argv[2])
    table = table_from_mix(sys.argv[1])
    if table['language'] != csf.LANGUAGE_CHINESE:
        sys.exit(f'{sys.argv[1]}: its RA2.CSF is language {table["language"]}, not Chinese (9)')
    texts = [text for _, values in table['labels'] for text, _ in values]
    simplified = iter(to_simplified(texts))
    table['labels'] = [(name, [(next(simplified), extra) for _, extra in values])
                       for name, values in table['labels']]
    game_dir = sys.argv[2]
    out = write_into(game_dir, 'RA2.CSF', csf.serialize(table))
    print(f'{out}: {len(table["labels"])} labels, {len(texts)} strings in Simplified Chinese')
    if any(f.name.lower() == 'langmd.mix' for f in Path(game_dir).iterdir()):
        zh = {name: [text for text, _ in values] for name, values in table['labels']}
        extra = {}
        if len(sys.argv) == 4:
            for label, index, text in json.loads(Path(sys.argv[3]).read_text(encoding='utf-8')):
                extra[(label.lower(), int(index))] = text
        yr, changed, kept = yuri_table(game_dir, zh, extra)
        out = write_into(game_dir, 'RA2MD.CSF', csf.serialize(yr))
        print(f"{out}: Yuri's Revenge, {changed} strings in Simplified Chinese, {kept} in English")
    ra2_mix = in_dir(game_dir, 'RA2.MIX')
    local = member(ra2_mix.read_bytes(), 'LOCAL.MIX', ra2_mix)
    fnt, added = font_with_simplified(member(local, 'GAME.FNT', f'{ra2_mix}/LOCAL.MIX'))
    out = write_into(game_dir, 'GAME.FNT', fnt)
    print(f'{out}: {added} simplified glyphs added')


if __name__ == '__main__':
    main()
