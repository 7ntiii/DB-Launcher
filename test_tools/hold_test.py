"""Host-start test on the twin rig (DUSK_MATCH_HOLD=1): waits until both games are searching, keeps them
searching for HOLD seconds (do they give up by themselves?), then presses the panel's Start match.
python diag/twin/hold_test.py [HOLD=90]"""
import json, sys, time, urllib.request
hold = float(sys.argv[1]) if len(sys.argv) > 1 else 90
def api(path, body=None):
    req = urllib.request.Request('http://127.0.0.1:18450' + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json'})
    return json.loads(urllib.request.urlopen(req, timeout=3).read())
def line(st):
    return time.strftime('%H:%M:%S') + ' waiting=%d | ' % st['server']['waiting'] + ' | '.join(
        '%d %s: %s %s ping=%s' % (p['pid'], 'host' if p['local'] else 'guest', p['status'], p['detail'], p['ping_ms']) for p in st['players'])
t0 = time.time(); since = None
while time.time() - t0 < 600:
    try:
        st = api('/api/state')
    except OSError:
        time.sleep(2); continue
    if st['server']['waiting'] >= 2:
        since = since or time.time()
        if time.time() - since >= hold:
            print(line(st)); print('pressing Start after %.0f s of searching' % (time.time() - since), api('/api/start', {})); break
    elif since:
        print(line(st)); print('a player STOPPED searching after %.0f s' % (time.time() - since)); since = None
    if int(time.time() - t0) % 15 == 0:
        print(line(st), flush=True)
    time.sleep(1)
for i in range(12):
    time.sleep(20)
    st = api('/api/state'); print(line(st), flush=True)
    for p in st['players']:
        print('    ', {k: p.get(k) for k in ('pid', 'phase', 'clock_left', 'player_no', 'timer_gap', 'move_delay', 'ping_kind')})
print([e['text'] for e in st['events']])
