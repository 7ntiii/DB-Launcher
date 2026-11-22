"""Keeps the twin games searching while the rig hosts for another PC (TWIN_HOST_PANEL=1): a game's
search ends by itself after about 8 minutes, and after a match the game is back in the hub. Every
few seconds this reads the panel state; a local game whose row says "Search ended" or "In the
menus" is taken to the Dusk Battle menu (screen checked) and Y is pressed once.
Usage: python diag/twin/keep_searching.py [MINUTES=120]"""
import json, sys, time, urllib.request
sys.path.insert(0, 'diag/twin')
from screen import grab, state, press
from tctl import GAMES
LAN = __import__('os').environ.get('TWIN_LAN_IP', '192.168.1.11')
IPS = {'A': '127.0.0.1', 'B': LAN, 'C': __import__('os').environ.get('TWIN_IP_C', '10.0.0.225'),
       'D': __import__('os').environ.get('TWIN_IP_D', '169.254.0.1')}
end = time.time() + 60 * float(sys.argv[1] if len(sys.argv) > 1 else 120)
since = {}
while time.time() < end:
    time.sleep(5)
    try:
        st = json.loads(urllib.request.urlopen('http://127.0.0.1:18451/api/state', timeout=3).read())
    except Exception:
        continue
    rows = {p['ip']: p for p in st['players']}
    for w in GAMES:
        row = rows.get(IPS[w])
        if row is None or row['kind'] not in ('ended', 'menu'):
            since.pop(w, None)
            continue
        since.setdefault(w, time.time())
        if time.time() - since[w] < 12:          # give a fresh state a moment (match just cancelled, loading)
            continue
        try:
            s, _ = state(grab(w))
        except Exception:
            continue
        if s == 'mmenu':
            press(w, 'Y')
            print(time.strftime('%H:%M:%S'), w, 'search started again', flush=True)
            since.pop(w, None)
            time.sleep(3)
        elif s in ('hub', 'err', 'settings'):
            press(w, {'hub': 'Minus', 'err': 'A', 'settings': 'B'}[s])
            print(time.strftime('%H:%M:%S'), w, 'screen', s, flush=True)
