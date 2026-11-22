"""Travel-overlay rule shared by to_hub2b.py / to_match2b.py (read only; 2026-11-17, static).

References: diag/twin/ref_travel_C.png (copy of C_stuck.png: the overlay over the idle hub, game C) and
ref_travel_B.png (copy of B_hand_3.png: the same overlay as the Travel tab of the hub menu, game B), both 640x360,
the size screen.py works at (it loads every reference with .resize((640, 360))).

Rule (the overlay's own panel, not the whole frame: the background behind it differs between the two refs):
- grey 640x360 frame (screen.py's convert('L') + resize; BOX filter for larger shots, as its tolerant check);
- three panel boxes: tab title 'Travel' (15,12)-(110,36), destination list 'Hall / Courtyard' (20,58)-(205,102),
  preview picture (38,185)-(202,302); each reduced 4:1 by BOX averaging (structure, not exact pixels: works at
  1x and 0.5x like screen.py's tolerant check);
- score = for each reference, the LARGEST of the three mean absolute differences (0-255); then the smallest
  over the references. 'travel' when score < T_TRAVEL = 8.
- The footer 'Travel to House of Night: Hall' is not used: it differs by 8.5 between the two refs.
Measured 2026-11-17 on every 16:9 shot in diag/twin (722 files): the two refs score 2.4 against each other; every
other shot scores 19.9 or more (hub A_nav_done / B_nav_done 28+, hub menu A_hp_menu 34+, C_r4 = overlay fading
21.2, matchmaking menus 34+). Margin: 8 sits between 2.4 and 19.9.
Extra references: any diag/twin/ref_travel*.png is used (640x360, overlay fully open)."""
import glob
import os

from PIL import Image, ImageChops, ImageStat

T_TRAVEL = 8.0
BOXES = {'tab': (15, 12, 110, 36), 'list': (20, 58, 205, 102), 'prev': (38, 185, 202, 302)}


def _grey640(im):
    im = im.convert('L')
    if im.size != (640, 360):
        im = im.resize((640, 360), Image.BOX if im.size[0] > 640 else Image.BILINEAR)
    return im


def _sigs(im):
    im = _grey640(im)
    out = {}
    for k, b in BOXES.items():
        c = im.crop(b)
        out[k] = c.resize((max(1, c.size[0] // 4), max(1, c.size[1] // 4)), Image.BOX)
    return out


REFS = []
for _p in sorted(glob.glob(os.path.join('diag', 'twin', 'ref_travel*.png'))):
    try:
        REFS.append(_sigs(Image.open(_p)))
    except OSError:
        pass


def travel_dist(im):
    if not REFS:
        return None
    s = _sigs(im)
    return min(max(ImageStat.Stat(ImageChops.difference(s[k], r[k])).mean[0] for k in BOXES) for r in REFS)


def is_travel(im):
    d = travel_dist(im)
    return d is not None and d < T_TRAVEL


if __name__ == '__main__':          # python diag/twin/to_hub2b_ref.py SHOT.png ...  -> score and verdict per shot
    import sys
    print('references: %d' % len(REFS))
    for p in sys.argv[1:]:
        d = travel_dist(Image.open(p))
        print('%-28s score %s -> %s' % (p, 'n/a' if d is None else '%.1f' % d, 'travel' if is_travel(Image.open(p)) else 'not travel'))
