"""rig_tailscale_make.py: builds diag/twin/rig_tailscale.diff (tailscale_rig_notes.md) from copies of
diag/twin/pkgtest.py, run_night.sh and start3.py. Writes nothing in diag/twin except the diff.
python diag/twin/rig_tailscale_make.py SCRATCH_DIR
SCRATCH_DIR gets a/ and b/ (a = the files as they are, b = with RIG_NET=tailscale). Apply with
    git -c core.autocrlf=false apply diag/twin/rig_tailscale.diff        (from the workspace root)
only while no run_night.sh / pkgtest.py step is running (bash reads a running script from disk).
The LAN default (RIG_NET unset or lan) behaves exactly as before."""
import os
import subprocess
import sys

WS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(WS, 'diag', 'twin', 'rig_tailscale.diff')
scratch = sys.argv[1]
FILES = ('pkgtest.py', 'run_night.sh', 'start3.py')
texts = {}
for side in ('a', 'b'):
    os.makedirs(os.path.join(scratch, side, 'diag', 'twin'), exist_ok=True)
for name in FILES:
    raw = open(os.path.join(WS, 'diag', 'twin', name), 'rb').read()
    assert b'\r\n' not in raw, name + ' has CRLF; this script keeps LF only'
    texts[name] = raw.decode('utf-8')
    open(os.path.join(scratch, 'a', 'diag', 'twin', name), 'wb').write(raw)


def once(name, old, new):
    n = texts[name].count(old)
    assert n == 1, '%s: anchor not unique (%d): %r' % (name, n, old[:80])
    texts[name] = texts[name].replace(old, new)


# ------------------------------------------------------------------------------------------- pkgtest.py
once('pkgtest.py', '''def lan_ip():
    """lan_fix_host.py / host_plus.py / second_player.py's pick (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.168.0.1', 9))
        return s.getsockname()[0]
    finally:
        s.close()
''', '''def lan_ip():
    """lan_fix_host.py / host_plus.py / second_player.py's pick (no packet is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.168.0.1', 9))
        return s.getsockname()[0]
    finally:
        s.close()


def rig_tailscale():
    """RIG_NET=tailscale (run_night.sh; tailscale_rig_notes.md): the rig hosts players who join with this
    PC's Tailscale address, as "Host a match (Tailscale).cmd" does. Unset / lan = the home network (as before)."""
    return os.environ.get('RIG_NET', '').strip().lower() == 'tailscale'


def tailscale_ip4():
    """This PC's Tailscale IPv4 (100.64-100.127.x) from `tailscale ip -4`, or ''. Read only: nothing is signed
    in, set or changed (no `tailscale up / login / set`, no firewall)."""
    import ipaddress
    for exe in ('tailscale', r'C:\\Program Files\\Tailscale\\tailscale.exe'):
        try:
            out = subprocess.run([exe, 'ip', '-4'], capture_output=True, text=True, timeout=5,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        for word in out.split():
            try:
                if ipaddress.IPv4Address(word) in ipaddress.IPv4Network('100.64.0.0/10'):
                    return word
            except ValueError:
                pass
    return ''


def rig_ip():
    """The address the other players join with: the LAN one, or (RIG_NET=tailscale) this PC's 100.x."""
    return tailscale_ip4() if rig_tailscale() else lan_ip()
''')
once('pkgtest.py', '''    online.update(mode='host', server=lan_ip(), password=PASSWORD)
    conf['online'] = online
    shipped.write_text(json.dumps(conf, indent=2), encoding='utf-8')
    log(f'scratch launcher_settings.json: game {conf["game"]}, room password set, host {lan_ip()}')''',
     '''    online.update(mode='host', server=rig_ip(), password=PASSWORD)
    conf['online'] = online
    shipped.write_text(json.dumps(conf, indent=2), encoding='utf-8')
    log(f'scratch launcher_settings.json: game {conf["game"]}, room password set, host {rig_ip()}')''')
once('pkgtest.py', '''    hp = host_plus_module()
    own = hp.lan_ip()
    prefix = '.'.join(own.split('.')[:3])
''', '''    hp = host_plus_module()
    ts = rig_tailscale()
    own = tailscale_ip4() if ts else hp.lan_ip()
    if ts and not own:
        log('RIG_NET=tailscale, but `tailscale ip -4` gives no 100.x address: sign in to Tailscale (Connected) '
            'yourself, then start again. Nothing started.')
        return 1
    # host_plus.py main(): 'tailscale' = guests' second games go in as 127.0.2.<k> (p2p_addr_map.txt)
    prefix = 'tailscale' if ts else '.'.join(own.split('.')[:3])
    for stale in (hp.MAP_FILE, hp.ADDRESS_FILE):        # host_plus.py main() clears both at its start too
        try:
            stale.unlink()
        except OSError:
            pass
''')
once('pkgtest.py', '''    env['DUSK_P2P_PORTS'] = ','.join([f'{own}={hp.SECOND_P2P}'] + [f'127.0.1.{d}={hp.SECOND_P2P}' for d in range(1, 255)])
    env['DUSK_P2P_ADDR'] = ','.join(f'127.0.1.{d}={prefix}.{d}' for d in range(1, 255))
    for k in [k for k in env if k.startswith('DUSK_') and k not in (
            'DUSK_MATCH_WAIT', 'DUSK_TICKET_TTL', 'DUSK_P2P_FORMAT', 'DUSK_HOST_IP', 'DUSK_MATCH_HOLD',
            'DUSK_WAIT_LONGPOLL', 'DUSK_PANEL_PORT', 'DUSK_PANEL_HTML', 'DUSK_P2P_PORTS', 'DUSK_P2P_ADDR',
            'DUSK_STATUS_FILE', 'DUSK_MATCH_FILE')]:
        env.pop(k)                                       # no rig leftovers (DUSK_MATCH_MIN, DUSK_DEFAULT_ROOM ...)
    hosts = ['127.0.0.1'] + local_addresses()
''', '''    if ts:
        # host_plus.py main() + lan_fix_host.py with Tailscale play: this PC's second game on 15501, guests'
        # second games 127.0.2.<k> (their 100.x from p2p_addr_map.txt), our 100.x advertised, TURN per address
        env['DUSK_P2P_PORTS'] = ','.join([f'{own}={hp.SECOND_P2P}'] + [f'127.0.2.{k}={hp.SECOND_P2P}' for k in range(1, 255)])
        env['DUSK_P2P_ADDR'] = ''
        env.update(DUSK_ADVERTISE_IP=own, DUSK_TAILSCALE='1', DUSK_P2P_ADDR_FILE=str(hp.MAP_FILE))
        hp.ADDRESS_FILE.write_text(own + '\\n', encoding='utf-8')   # second_player.py signs in from it
    else:
        env['DUSK_P2P_PORTS'] = ','.join([f'{own}={hp.SECOND_P2P}'] + [f'127.0.1.{d}={hp.SECOND_P2P}' for d in range(1, 255)])
        env['DUSK_P2P_ADDR'] = ','.join(f'127.0.1.{d}={prefix}.{d}' for d in range(1, 255))
    keep = ('DUSK_MATCH_WAIT', 'DUSK_TICKET_TTL', 'DUSK_P2P_FORMAT', 'DUSK_HOST_IP', 'DUSK_MATCH_HOLD',
            'DUSK_WAIT_LONGPOLL', 'DUSK_PANEL_PORT', 'DUSK_PANEL_HTML', 'DUSK_P2P_PORTS', 'DUSK_P2P_ADDR',
            'DUSK_STATUS_FILE', 'DUSK_MATCH_FILE')
    if ts:
        keep += ('DUSK_ADVERTISE_IP', 'DUSK_TAILSCALE', 'DUSK_P2P_ADDR_FILE')
    for k in [k for k in env if k.startswith('DUSK_') and k not in keep]:
        env.pop(k)                                       # no rig leftovers (DUSK_MATCH_MIN, DUSK_DEFAULT_ROOM ...)
    hosts = ['127.0.0.1'] + local_addresses()
    if ts:
        hosts = ['127.0.0.1', own] + [h for h in hosts[1:] if h != own]   # --nat-ip and the frontdoor's host = 100.x
''')
once('pkgtest.py', '''    save_state(serve_pid=os.getpid(), server_pid=server.pid, front_pid=front.pid, run=str(run), lan=own,
               host_ip=fenv['DUSK_HOST_IP'])''', '''    save_state(serve_pid=os.getpid(), server_pid=server.pid, front_pid=front.pid, run=str(run), lan=own,
               host_ip=fenv['DUSK_HOST_IP'], rig_net='tailscale' if ts else 'lan')''')
once('pkgtest.py', '''    want = ['Second player on the host PC: sign-in ' + lan_ip() + ':18443', 'Room joined', 'Second player started']''',
     '''    want = ['Second player on the host PC: sign-in ' + rig_ip() + ':18443', 'Room joined', 'Second player started']''')
once('pkgtest.py', '''def cmd_rows():
    lan = lan_ip()''', '''def cmd_rows():
    lan = rig_ip()''')
once('pkgtest.py', '''def cmd_check():
    lan = lan_ip()''', '''def cmd_check():
    lan = rig_ip()''')

# ------------------------------------------------------------------------------------------- start3.py
once('start3.py', '''        rows = [(r.get('ip'), r.get('kind')) for r in st.get('players', [])]''',
     '''        # Tailscale rig (tailscale_rig_notes.md): a row the panel marks "NOT on Tailscale" (joined with a home
        # address) cannot play with the remote players: never counted. Home matches never show that mark.
        rows = [(r.get('ip'), r.get('kind')) for r in st.get('players', [])
                if 'NOT on Tailscale' not in (r.get('detail') or '')]''')

# ------------------------------------------------------------------------------------------- run_night.sh
once('run_night.sh', '''# Logs: diag/twin/night_*.log. Match number for log names: M=<n> (default 1).
cd <WORKSPACE> || exit 2
M=${M:-1}
''', '''# Logs: diag/twin/night_*.log. Match number for log names: M=<n> (default 1).
# RIG_NET=tailscale (tailscale_rig_notes.md): the rig hosts on this PC's Tailscale address (`tailscale ip -4`,
# read only); every other player joins with that 100.x. RIG_PLAYERS=<n> (default 4) players in all: start3
# presses Start match at n searching, `match` waits for n-2 remote ones. Unset / lan = the home match as before.
cd <WORKSPACE> || exit 2
M=${M:-1}
RIG_NET=${RIG_NET:-lan}; export RIG_NET
RIG_PLAYERS=${RIG_PLAYERS:-4}
serve_net() { python -c "import json; print(json.load(open('diag/twin/pkgtest/state.json')).get('rig_net', 'lan'))" 2>/dev/null || echo lan; }
''')
once('run_night.sh', '''    stopper 'watch_match|start3|hold_clock|fps_watch|to_match2b|fx_probe'
    taskkill //IM lichii.exe //F >/dev/null 2>&1; sleep 3''', '''    if [ "$RIG_NET" = tailscale ]; then
        TSIP=$( (tailscale ip -4 2>/dev/null || "/c/Program Files/Tailscale/tailscale.exe" ip -4 2>/dev/null) | tr -d '\\r' \\
            | grep -E '^100\\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\\.' | head -n 1)   # read only
        [ -n "$TSIP" ] || { echo "RIG_NET=tailscale: no 100.x address from 'tailscale ip -4' (sign in to Tailscale first); nothing done"; exit 1; }
        echo "$(date +%T) Tailscale rig: every other player joins with $TSIP (Online, Join a room), $RIG_PLAYERS players in all"
    fi
    if powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name='python.exe'\\" | Where-Object { \\$_.CommandLine -match 'pkgtest.py serve' }" | grep -q python \\
        && [ "$(serve_net)" != "$RIG_NET" ]; then
        echo "a pkgtest serve for '$(serve_net)' is running, this start is '$RIG_NET': run 'python diag/twin/pkgtest.py stop' first; nothing done"
        exit 1
    fi
    stopper 'watch_match|start3|hold_clock|fps_watch|to_match2b|fx_probe'
    taskkill //IM lichii.exe //F >/dev/null 2>&1; sleep 3''')
once('run_night.sh', '''    nohup $R diag/twin/start3.py 3 > diag/twin/night_start3_m$M.log 2>&1 &
    echo "$(date +%T) v$V: both rig games in the hub, start3 waiting for the laptop (log night_start3_m$M.log)"''',
     '''    N3=3; [ "$RIG_NET" = tailscale ] && N3=$RIG_PLAYERS
    nohup $R diag/twin/start3.py $N3 > diag/twin/night_start3_m$M.log 2>&1 &
    echo "$(date +%T) v$V: both rig games in the hub, start3 waiting for $N3 searching players (log night_start3_m$M.log)"''')
once('run_night.sh', '''    until tail -n 1 diag/twin/night_start3_m$M.log | grep -q "192.168.1.66', 'search'"; do sleep 1; done
    echo "$(date +%T) laptop searching"''', '''    if [ "$RIG_NET" = tailscale ]; then
        python diag/twin/remote_search.py $((RIG_PLAYERS - 2)) || exit 1
    else
        until tail -n 1 diag/twin/night_start3_m$M.log | grep -q "192.168.1.66', 'search'"; do sleep 1; done
        echo "$(date +%T) laptop searching"
    fi''')

once('run_night.sh', '''    sed -n 2,13p "$0"''', '''    sed -n 2,14p "$0"''')

for name in FILES:
    open(os.path.join(scratch, 'b', 'diag', 'twin', name), 'wb').write(texts[name].encode('utf-8'))
# remote_search.py is a new file of its own (diag/twin), not in the diff
d = subprocess.run(['git', '-c', 'core.autocrlf=false', 'diff', '--no-index', 'a/diag/twin', 'b/diag/twin'],
                   cwd=scratch, capture_output=True)
open(OUT, 'wb').write(d.stdout.replace(b'a/a/diag/twin/', b'a/diag/twin/').replace(b'b/b/diag/twin/', b'b/diag/twin/'))
print('scratch:', os.path.join(scratch, 'b'))
print('diff written:', OUT, len(d.stdout), 'bytes')
