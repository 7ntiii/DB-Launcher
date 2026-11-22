import os
"""Screen state of a twin game from a live screenshot, by comparison with saved reference shots.
python diag/twin/screen.py [A] [B]  -> prints state + distance. States: black (loading), hub, menu
(title menu), mmenu (Dusk Battle menu open), mmgo (matchmaking running), err (error dialog),
settings (matchmaking settings), other.

Render scale (four_players3_notes.md 1): the debug server's screenshot is always 640x360 (the
emulator blits the frame into the requested layout), so the geometry never changes with
resolution_setup. What changes is the pixel detail of the UI: at 1X the 1080p frame is shrunk 3:1,
at 0.5X a 540p frame 1.5:1, so thin text edges differ. The 1X check compares the menu row pixel by
pixel (threshold 7; a 1X shot taken at another capture height already sits at 5-6), so a 0.5X
game's open Dusk Battle menu came out 'other'. A game whose qt-config.ini renders at another scale
than 1X (or every game with SCREEN_TOLERANT=1) is therefore classified on area-averaged images: the
row is reduced 2:1 by box filtering before the comparison (structure, not exact pixels), with its
own thresholds. A 1X game keeps the original check unchanged (SCREEN_TOLERANT=0 forces it for all)."""
import sys
sys.path.insert(0, 'diag/twin')
from tctl import call
from PIL import Image, ImageChops, ImageStat
D = 'diag/twin/'
ROW = (20, 118, 200, 142)          # left panel row: "Start matchmaking" / "Cancel" (640x360)
def _load(p):
    return Image.open(D + p).convert('L').resize((640, 360))
REF_ROW = {'mmenu': ['A_t21c.png', 'B_t21c.png'], 'mmgo': ['B_t21d.png', 'A_mm.png'],
           'hub': ['A_nav_done.png', 'B_nav_done.png'], 'err': ['A_t21a.png', 'B_t21b.png'],
           'settings': ['A_t21b.png']}
REF_FULL = {'menu': ['A_nav_menu.png'], 'hub': ['A_nav_done.png', 'B_nav_done.png']}
_row = {k: [_load(p).crop(ROW) for p in v] for k, v in REF_ROW.items()}
_full = {k: [_load(p).resize((64, 36)) for p in v] for k, v in REF_FULL.items()}

# --- scale-tolerant check (games not at 1X) ---
T_ROW, T_ROW_HUB, T_FULL_HUB, T_FULL_MENU = 5.5, 6.5, 8, 6   # calibrated: four_players3_notes.md 1
EXTRA_ROW = {'mmgo': ['A_hold.png', 'B_hold.png']}            # "Cancel" row, matchmaking running
def _load_area(p):                 # area filter (BOX): no aliasing whatever the source size
    im = Image.open(D + p).convert('L')
    return im.resize((640, 360), Image.BOX if im.size[0] > 640 else Image.BILINEAR)
def _sig(im):
    c = im.crop(ROW)
    return c.resize((c.size[0] // 2, c.size[1] // 2), Image.BOX)
_row_t = {k: [_sig(_load_area(p)) for p in v + EXTRA_ROW.get(k, [])] for k, v in REF_ROW.items()}
_full_t = {k: [_load_area(p).resize((64, 36), Image.BOX) for p in v] for k, v in REF_FULL.items()}

RES_NAMES = ['1/4x', '1/2x', '3/4x', '1x', '5/4x', '3/2x', '2x', '3x', '4x', '5x', '6x', '7x', '8x']
def config_path(who):
    if os.environ.get('TWIN_CONFIG_' + who):          # set by pkgtest.py run for child tools
        return os.environ['TWIN_CONFIG_' + who]
    if who == 'A':
        return os.path.join(os.environ.get('APPDATA', ''), 'eden', 'config', 'qt-config.ini')
    return f'{D}user{who}/config/qt-config.ini'
def render_scale(who):
    """resolution_setup index the emulator reads (3 = 1X): resolution_setup\\default=true or
    missing means the default 1X whatever the value (frontend_common/config.cpp ReadSetting)."""
    value, default, section = None, 'true', ''
    try:
        with open(config_path(who), encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if line.startswith('['):
                    section = line
                elif section == '[Renderer]' and line.startswith('resolution_setup\\default='):
                    default = line.split('=', 1)[1].strip().lower()
                elif section == '[Renderer]' and line.startswith('resolution_setup='):
                    value = line.split('=', 1)[1].strip()
    except OSError:
        return 3
    if default == 'true' or value is None:
        return 3
    try:
        return int(value)
    except ValueError:
        return 3
_tolerant = {}
def tolerant(who):
    force = os.environ.get('SCREEN_TOLERANT')
    if force in ('0', '1'):
        return force == '1'
    if not who:
        return False
    if who not in _tolerant:
        _tolerant[who] = render_scale(who) != 3
    return _tolerant[who]

def d(a, b):
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]
def grab(who):
    out = f'{D}_live_{who}.png'
    try:
        os.remove(out)                    # never re-read an old frame (debug server not up yet)
    except OSError:
        pass
    try:
        call(who, {'method': 'screenshot', 'params': {'height': 360}}, out)
    except Exception:
        pass
    if not os.path.exists(out):
        im = Image.new('L', (640, 360), 0)
    else:
        im = Image.open(out).convert('L').resize((640, 360))
    im.info['twin_game'] = who            # state() picks the check for this game's render scale
    return im
def state(im, who=None):
    who = who or im.info.get('twin_game')
    if tolerant(who):
        return state_tolerant(im)
    small = im.resize((64, 36))
    if ImageStat.Stat(small).mean[0] < 6:
        return 'black', 0.0
    fd = {k: min(d(small, r) for r in v) for k, v in _full.items()}
    rd = {k: min(d(im.crop(ROW), r) for r in v) for k, v in _row.items()}
    if fd['hub'] < 8 and rd['hub'] < 6:
        return 'hub', fd['hub']
    if fd['menu'] < 6:
        return 'menu', fd['menu']
    k = min(rd, key=rd.get)
    return (k, rd[k]) if rd[k] < 7 else ('other', rd[k])
def state_tolerant(im):
    if im.size != (640, 360):
        im = im.convert('L').resize((640, 360), Image.BOX)
    if ImageStat.Stat(im.resize((64, 36))).mean[0] < 6:     # same black test as the 1X check
        return 'black', 0.0
    small = im.resize((64, 36), Image.BOX)
    fd = {k: min(d(small, r) for r in v) for k, v in _full_t.items()}
    s = _sig(im)
    rd = {k: min(d(s, r) for r in v) for k, v in _row_t.items()}
    if fd['hub'] < T_FULL_HUB and rd['hub'] < T_ROW_HUB:
        return 'hub', fd['hub']
    if fd['menu'] < T_FULL_MENU:
        return 'menu', fd['menu']
    k = min(rd, key=rd.get)
    return (k, rd[k]) if rd[k] < (T_ROW_HUB if k == 'hub' else T_ROW) else ('other', rd[k])
def press(who, *btns, hold=8):
    call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': list(btns), 'frames': hold}, {'frames': 20}]}})
if __name__ == '__main__':
    for w in sys.argv[1:] or 'AB':
        print(w, *state(grab(w)), RES_NAMES[render_scale(w)] + (' (tolerant check)' if tolerant(w) else ''))
