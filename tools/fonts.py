"""The fonts bundled in fonts/ (see fonts/README.md).

Text is always laid out with Pillow's basic engine so that the result is the
same on every system, whether or not Pillow was built with libraqm.
"""
import os

from PIL import ImageFont

DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'fonts')

SANS_REGULAR = os.path.join(DIR, 'NotoSansCJKjp-Regular-Latin.otf')
SANS_BOLD = os.path.join(DIR, 'NotoSansCJKjp-Bold-Latin.otf')
SERIF_SEMIBOLD = os.path.join(DIR, 'NotoSerifCJKjp-SemiBold-Latin.otf')
SERIF_BOLD = os.path.join(DIR, 'NotoSerifCJKjp-Bold-Latin.otf')
SERIF_BLACK = os.path.join(DIR, 'NotoSerifCJKjp-Black-Latin.otf')
MONO = os.path.join(DIR, 'DejaVuSansMono.ttf')
SERIF_TEXT = os.path.join(DIR, 'LiberationSerif-Regular.ttf')


def load(path, size):
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.BASIC)


def cap_sized(path, cap, ss=1):
    """The font at the size whose capital H is `cap` * `ss` pixels tall."""
    probe = load(path, 40 * ss)
    hb = probe.getbbox('H')
    return load(path, max(1, round(40 * ss * cap * ss / (hb[3] - hb[1]))))
