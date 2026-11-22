"""Press the host panel's Start match once N players search (default 3). Rig only (pkgtest host)."""
import json, sys, time, urllib.request
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
API = 'http://127.0.0.1:18451/api/'
t0 = time.time()
last = None
while time.time() - t0 < 900:
    try:
        st = json.loads(urllib.request.urlopen(API + 'state', timeout=5).read())
        # Tailscale rig (tailscale_rig_notes.md): a row the panel marks "NOT on Tailscale" (joined with a home
        # address) cannot play with the remote players: never counted. Home matches never show that mark.
        rows = [(r.get('ip'), r.get('kind')) for r in st.get('players', [])
                if 'NOT on ' not in (r.get('detail') or '')]
        if rows != last:
            print(time.strftime('%H:%M:%S'), rows, flush=True)
            last = rows
        if len([r for r in rows if r[1] == 'search']) >= N and not st['server'].get('starting'):
            req = urllib.request.Request(API + 'start', data=b'{}', headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5).read()
            print(time.strftime('%H:%M:%S'), 'Start match pressed with', N, 'searching', flush=True)
            break
    except Exception as e:
        print('panel:', e, flush=True)
    time.sleep(2)
