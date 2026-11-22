r"""Host a match with second players (2026-11-15): lan_fix_host.py plus what two games on one PC need.

Run by "Host a match (4 players).cmd" on the HOSTING PC (PC1) instead of the plain host .cmd.
It does three things, then runs lan_fix_host.py unchanged (same launcher, panel and fixed servers):

1. Tells the match server where second games listen (environment of the launcher, which hands it
   on to its frontdoor / frontend_api.py):
   - PC1's own second game signs in from PC1's LAN address (the host's first game uses
     127.0.0.1), so DUSK_P2P_PORTS gets "<LAN>=15501": its game listens on 15501
     (LICHII_PORT_MAP 15500=15501 in second_player.py).
   - A guest PC's second game comes through the relay below and is seen as 127.0.1.<d>, where d is
     the last number of that PC's address. DUSK_P2P_ADDR maps 127.0.1.<d> to <LAN prefix>.<d>
     (where its game really is) and DUSK_P2P_PORTS 127.0.1.<d> to 15501.
2. Relay for guest PCs' second games: TCP ports 18453 (game, TLS passed through unchanged) and
   18455 (room service: /hello, /ca.der, /register) on this PC, each connection forwarded to the
   launcher's own servers (127.0.0.1:18443 / :18445) from the local source address 127.0.1.<d>.
   Why: the match server tells players apart by the address their connection comes from
   (frontdoor.py:135 conn.getpeername(); frontend_api.py _players[...]['ip'], _room_of_ip,
   DUSK_P2P_PORTS / DUSK_P2P_ADDR keyed by it, panel rows "one row per address"). Two games on
   PC2 both come from PC2's one address; through the relay the second one has an address of its
   own, with no network setting changed on any PC (Windows accepts any 127.x source address).
3. Keeps running while the launcher runs (the relay lives in this process).

Only guest PCs on the same /24 network as this PC are relayed (192.168.1. with this PC at
192.168.1.); others get a clear refusal in the log.
Log: lan_fix\host_plus_log.txt.
"""
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / 'host_plus_log.txt'
GAME_PORT, ROOM_PORT = 18443, 18445            # the launcher's frontdoor and room service
RELAY_GAME, RELAY_ROOM = 18453, 18455          # this relay (second games of guest PCs)
# Tailscale play: a guest's second game goes in as 127.0.2.<k>, one k per guest PC (Tailscale
# addresses share no /24, so the last number cannot be used). The match server reads the
# 127.0.2.<k> -> 100.x pairs from MAP_FILE (DUSK_P2P_ADDR_FILE), written as guests arrive.
MAP_FILE = HERE / 'p2p_addr_map.txt'
# The address the host PC's own second game signs in from (second_player.py reads it while this
# script runs, i.e. while the relay port answers).
ADDRESS_FILE = HERE / 'host_address.txt'
_slots, _slots_lock = {}, threading.Lock()
SECOND_P2P = 15501                             # LICHII_PORT_MAP 15500=15501 of every second game


def log(text):
    line = time.strftime('%H:%M:%S ') + text
    try:
        print(line, flush=True)
    except (AttributeError, OSError):
        pass
    try:
        with LOG_FILE.open('a', encoding='utf-8') as f:
            f.write(line + '\n')
    except OSError:
        pass


def lan_ip():
    """This PC's address on the home network (no packet is sent). N1 (deep_audit_N): it can be
    chosen with DUSK_LAN_IP=<address> or a file lan_fix\\lan_ip.txt holding it. Else the route to
    192.168.0.1 is the first guess. On a PC whose VPN takes that route (a full VPN, a Tailscale
    exit node: 100.64-100.127.x; Hamachi: 25.x) the guess is not a home address, and on a PC
    without a gateway there is no route at all: then this PC's other addresses are used,
    192.168.x first, then 10.x, then 172.16-172.31.x."""
    forced = _override_text()
    if forced.lower() == 'tailscale':
        # Tailscale play (tailscale_support.diff): this PC's Tailscale address, or '' when Tailscale
        # is not signed in / connected (the callers stop with a clear message then).
        return tailscale_ip()
    if forced and _usable_override(forced):
        return forced
    guess = ''
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.168.0.1', 9))
        guess = s.getsockname()[0]
    except OSError:
        pass                                   # no route (no gateway): use the list below
    finally:
        s.close()
    if _home_address(guess):
        return guess
    for prefix in ('192.168.', '10.', '172.'):
        for address in lan_ip_candidates():
            if address.startswith(prefix):
                return address
    return guess or '127.0.0.1'


# what Tailscale hands out (CGNAT shared space); DUSK_VPN_NET=<a.b.c.d/n> names another VPN's network
# (ZeroTier: the launcher sets it from the ZeroTier adapter), and the same mode then works for it
TAILSCALE_NET = os.environ.get('DUSK_VPN_NET', '').strip() or '100.64.0.0/10'
VPN_NAME = os.environ.get('DUSK_VPN_NAME', '').strip() or 'Tailscale'


def _override_text():
    """DUSK_LAN_IP, else the first word of lan_fix\\lan_ip.txt (review R1: utf-8-sig), else ''."""
    forced = os.environ.get('DUSK_LAN_IP', '').strip()
    if not forced:
        try:
            forced = (Path(__file__).resolve().parent / 'lan_ip.txt').read_text(encoding='utf-8-sig')
            forced = (forced.split() or [''])[0]
        except OSError:
            forced = ''
    return forced


def tailscale_mode():
    """Tailscale play is switched on: lan_ip.txt or DUSK_LAN_IP holds the word "tailscale" or a 100.x
    (Tailscale) address (review T1: the same test in every script)
    ("Host a match (Tailscale).cmd" sets DUSK_LAN_IP=tailscale)."""
    text = _override_text()
    return text.lower() == 'tailscale' or in_tailscale(text)


def in_tailscale(ip):
    import ipaddress
    try:
        return ipaddress.IPv4Address(ip) in ipaddress.IPv4Network(TAILSCALE_NET, strict=False)
    except ValueError:
        return False


def tailscale_ip():
    """This PC's Tailscale IPv4 address (100.64-100.127.x), or '' when Tailscale is not connected.
    The adapters first; then `tailscale ip -4` (read only; nothing is signed in or changed)."""
    try:
        found = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        found = []
    for address in found:
        if in_tailscale(address):
            return address
    try:
        out = subprocess.run(['tailscale', 'ip', '-4'], capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout
    except (OSError, subprocess.SubprocessError):
        out = ''
    return next((w for w in out.split() if in_tailscale(w)), '')


def _usable_override(ip):
    """review R1: lan_ip.txt / DUSK_LAN_IP must be a plain IPv4 address, not loopback or 169.254.x."""
    import ipaddress
    try:
        address = ipaddress.IPv4Address(ip)
    except ValueError:
        address = None
    if address is None or address.is_loopback or address.is_link_local or address.is_unspecified:
        sys.stderr.write(f'lan_ip.txt / DUSK_LAN_IP: "{ip}" is not a usable IPv4 address; ignored.\n')
        return False
    return True


def _home_address(ip):
    import ipaddress
    try:
        address = ipaddress.IPv4Address(ip)
    except ValueError:
        return False
    return address.is_private and not (address.is_loopback or address.is_link_local)


def lan_ip_candidates():
    """Every home-network address of this PC (all adapters: LAN, Wi-Fi, ZeroTier, ...)."""
    try:
        found = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        found = []
    return [a for a in found if _home_address(a)]


def pipe(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


def relay(listen_port, target_port, prefix, own):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(('0.0.0.0', listen_port))
    except OSError as error:
        log(f'relay port {listen_port} busy ({error}): guest PCs cannot start a second game')
        return
    server.listen(32)
    log(f'relay {listen_port} -> 127.0.0.1:{target_port} ready')
    seen = set()
    while True:
        try:
            conn, (peer, _) = server.accept()
        except OSError:
            return
        parts = peer.split('.')
        if peer.startswith('127.') or peer == own:
            conn.close()                       # this PC's own check (second_player.py) or a stray
            continue
        if prefix == 'tailscale':
            if not in_tailscale(peer):
                log(f'relay {listen_port}: refused {peer} (Tailscale play: join with {own})')
                conn.close()
                continue
            parts = ['127', '0', '2', str(_slot(peer))]
            if parts[3] == '0':
                log(f'relay {listen_port}: refused {peer} (no free slot)')
                conn.close()
                continue
        elif '.'.join(parts[:3]) != prefix:
            log(f'relay {listen_port}: refused {peer} (only other PCs on {prefix}.x)')
            conn.close()
            continue
        source = f'127.0.{2 if prefix == "tailscale" else 1}.{parts[3]}'
        try:
            out = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            out.bind((source, 0))
            out.connect(('127.0.0.1', target_port))
        except OSError as error:
            log(f'relay {listen_port}: {peer} -> 127.0.0.1:{target_port} failed ({error}); is the '
                f'launcher hosting (Start game pressed)?')
            conn.close()
            continue
        if (listen_port, peer) not in seen:
            seen.add((listen_port, peer))
            log(f'relay {listen_port}: second game of {peer} goes in as {source}')
        threading.Thread(target=pipe, args=(conn, out), daemon=True).start()
        threading.Thread(target=pipe, args=(out, conn), daemon=True).start()


def _slot(peer):
    """Tailscale play: the k of 127.0.2.<k> for this guest PC (1..254, 0 = full); the pairs go
    to MAP_FILE at once, so the match server knows where that second game really listens."""
    with _slots_lock:
        if peer not in _slots:
            if len(_slots) >= 254:
                return 0
            _slots[peer] = len(_slots) + 1
            text = ''.join(f'127.0.2.{k}={ip}\n' for ip, k in sorted(_slots.items(), key=lambda x: x[1]))
            tmp = MAP_FILE.with_name(MAP_FILE.name + '.tmp')
            tmp.write_text(text, encoding='utf-8')
            tmp.replace(MAP_FILE)
        return _slots[peer]


def main():
    own = lan_ip()
    tailscale = tailscale_mode()
    for stale in (MAP_FILE, ADDRESS_FILE):
        try:
            stale.unlink()
        except OSError:
            pass
    if tailscale and not own:
        log('Tailscale play is switched on, but this PC has no Tailscale address (100.x): open '
            'Tailscale, sign in, wait for Connected, then start this file again.')
        return 1
    prefix = 'tailscale' if tailscale else '.'.join(own.split('.')[:3])
    if tailscale:
        ports = [f'{own}={SECOND_P2P}'] + [f'127.0.2.{k}={SECOND_P2P}' for k in range(1, 255)]
        addrs = []
    else:
        ports = [f'{own}={SECOND_P2P}'] + [f'127.0.1.{d}={SECOND_P2P}' for d in range(1, 255)]
        addrs = [f'127.0.1.{d}={prefix}.{d}' for d in range(1, 255)]
    env = dict(os.environ)
    if tailscale:
        env['DUSK_P2P_ADDR_FILE'] = str(MAP_FILE)
        ADDRESS_FILE.write_text(own + '\n', encoding='utf-8')
    env.setdefault('DUSK_HOST_IP', own)        # N1: lan_fix_host.py uses the same address
    old_ports = env.get('DUSK_P2P_PORTS', '')
    old_addrs = env.get('DUSK_P2P_ADDR', '')
    env['DUSK_P2P_PORTS'] = ','.join(([old_ports] if old_ports else []) + ports)
    env['DUSK_P2P_ADDR'] = ','.join(([old_addrs] if old_addrs else []) + addrs)
    log(f'host with second players: this PC {own}; its second game listens on {SECOND_P2P}; '
        f'guest PCs {"on Tailscale" if tailscale else prefix + ".x"}: second games through ports '
        f'{RELAY_GAME} / {RELAY_ROOM}')
    for listen_port, target_port in ((RELAY_GAME, GAME_PORT), (RELAY_ROOM, ROOM_PORT)):
        threading.Thread(target=relay, args=(listen_port, target_port, prefix, own),
                         daemon=True).start()
    # started by the launcher itself (Play.Duskbloods.exe --run-script host_plus.py): no Python is needed then,
    # and the next script runs through the same launcher program
    py = [sys.executable, '--run-script'] if getattr(sys, 'frozen', False) else [sys.executable]
    # a frozen launcher started from a frozen launcher must unpack its OWN files (PyInstaller would reuse the
    # parent's temp folder: 'Failed to remove temporary directory', and the server swap finds no new folder)
    host = subprocess.Popen(py + [str(HERE / 'lan_fix_host.py')], cwd=str(HERE),
                            env=dict(env, PYINSTALLER_RESET_ENVIRONMENT='1'))
    code = host.wait()
    try:
        ADDRESS_FILE.unlink()
    except OSError:
        pass
    log(f'host script ended ({code}); relay stops')
    return code


if __name__ == '__main__':
    sys.exit(main())
