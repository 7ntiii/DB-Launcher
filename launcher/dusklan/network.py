"""This PC's networks, the room's small HTTP protocol, and finding rooms without typing an address.

Everything here only reads: no adapter, firewall or Windows setting is changed.
"""
import hashlib
import ipaddress
import json
import os
import socket
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
TAILSCALE_NET = ipaddress.IPv4Network('100.64.0.0/10')


def http(url, data=None, timeout=8):
    """GET, or (data given) a POST with the data as JSON, which is what the room's sign-up service reads."""
    body = json.dumps(data).encode() if data is not None else None
    headers = {'Content-Type': 'application/json'} if data is not None else {}
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers), timeout=timeout) as reply:
        return reply.read()


def room_id(password):
    """What stands for the password on the wire: players with the same password meet in the same room."""
    return hashlib.sha256(('duskbloods-room-v1:' + password.strip()).encode('utf-8')).hexdigest()[:32]


def split_address(text, default_port=config.GAME_PORT):
    """'192.168.1.20' or '192.168.1.20:18443' -> (host, port); ('', port) when nothing usable was typed."""
    text = (text or '').strip().replace('http://', '').replace('https://', '').strip('/')
    host, _, port = text.partition(':')
    try:
        return host.strip(), int(port) if port.strip() else default_port
    except ValueError:
        return host.strip(), default_port


def networks():
    """The IPv4 networks this PC is on: [{'name', 'kind': 'home'|'vpn', 'ip', 'net', 'public'}].

    'public' is Windows' own label for the network: on a Public network Windows blocks incoming
    connections, so a host there cannot be reached by the other players.
    """
    rows = _adapter_rows()
    found = []
    for alias, ip, prefix, category in rows:
        try:
            address = ipaddress.IPv4Address(ip)
            net = ipaddress.IPv4Network(f'{ip}/{int(prefix)}', strict=False)
        except ValueError:
            continue
        if address.is_loopback or address.is_link_local or address.is_unspecified:
            continue
        low = alias.lower()
        public = category.strip().lower() == 'public'
        if low.startswith('tailscale') or address in TAILSCALE_NET:
            found.append({'name': 'Tailscale', 'kind': 'vpn', 'ip': ip, 'net': str(TAILSCALE_NET), 'public': public})
        elif low.startswith('zerotier'):
            found.append({'name': 'ZeroTier', 'kind': 'vpn', 'ip': ip, 'net': str(net), 'public': public})
        elif any(word in low for word in ('hamachi', 'radmin', 'wireguard', 'openvpn', 'vpn')):
            found.append({'name': alias, 'kind': 'vpn', 'ip': ip, 'net': str(net), 'public': public})
        elif address.is_private:
            found.append({'name': alias, 'kind': 'home', 'ip': ip, 'net': str(net), 'public': public})
    found.sort(key=lambda n: (n['kind'] != 'home', not n['ip'].startswith('192.168.'), n['ip']))
    return found


def _adapter_rows():
    """(adapter name, address, prefix length, Windows category) for every IPv4 address."""
    if os.name == 'nt':
        script = ("$c = @{}; Get-NetConnectionProfile | ForEach-Object { $c[$_.InterfaceAlias] = "
                  "[string]$_.NetworkCategory }; Get-NetIPAddress -AddressFamily IPv4 | ForEach-Object { "
                  "$_.InterfaceAlias + '|' + $_.IPAddress + '|' + $_.PrefixLength + '|' + $c[$_.InterfaceAlias] }")
        try:
            out = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True,
                                 text=True, timeout=20, creationflags=NO_WINDOW).stdout
        except (OSError, subprocess.SubprocessError):
            out = ''
        rows = [tuple(line.strip().split('|')) for line in out.splitlines() if line.count('|') == 3]
        if rows:
            return rows
    try:      # without PowerShell: the addresses only, each taken as a /24 network
        return [('network', ip, '24', '') for ip in socket.gethostbyname_ex(socket.gethostname())[2]]
    except OSError:
        return []


def home_network(found):
    return next((n for n in found if n['kind'] == 'home'), None)


def hello(host, timeout=3):
    """The room's greeting, or None when no DB room answers there."""
    try:
        answer = json.loads(http(f'http://{host}:{config.ROOM_PORT}/hello', timeout=timeout))
    except (OSError, ValueError):
        return None
    return answer if isinstance(answer, dict) and answer.get('service') == 'duskbloods-online' else None


def find_rooms(found, progress=None):
    """Look for open rooms on the given networks: [{'ip', 'name', 'network', 'ms'}], fastest first.

    Every address that could be a host gets one short connection attempt to the room port; a PC that
    answers is asked for its greeting. Which addresses are tried:
      a network of up to 1022 hosts   every address
      a larger network (some VPNs)    the 254 addresses around this PC's own, plus the PCs Windows
                                      already knows on it (its neighbour list)
      Tailscale                       the devices Tailscale itself lists (its network is far too large)
    """
    targets, seen = [], set()
    for network in found:
        if network['name'] == 'Tailscale':
            addresses = _tailscale_peers()
        else:
            net = ipaddress.IPv4Network(network['net'], strict=False)
            if net.num_addresses <= 1024:
                addresses = [str(host) for host in net.hosts()]
            else:
                near = ipaddress.IPv4Network(network['ip'] + '/24', strict=False)
                addresses = [str(host) for host in near.hosts()]
                addresses += [ip for ip in _neighbours() if ipaddress.IPv4Address(ip) in net]
        for ip in addresses:
            if ip != network['ip'] and ip not in seen:
                seen.add(ip)
                targets.append((ip, network['name']))
    own = {n['ip'] for n in found}
    rooms, done = [], [0]

    def probe(target):
        ip, name = target
        started = time.perf_counter()
        try:
            with socket.create_connection((ip, config.ROOM_PORT), timeout=0.7):
                pass
        except OSError:
            return None
        finally:
            done[0] += 1
            if progress and done[0] % 32 == 0:
                progress(done[0], len(targets))
        ms = round((time.perf_counter() - started) * 1000)
        greeting = hello(ip)
        return {'ip': ip, 'name': greeting.get('name', ''), 'network': name, 'ms': ms} if greeting else None

    if targets:
        with ThreadPoolExecutor(max_workers=96) as pool:
            for room in pool.map(probe, targets):
                if room and room['ip'] not in own:
                    rooms.append(room)
    rooms.sort(key=lambda r: r['ms'])
    return rooms


def _neighbours():
    """IPv4 addresses of PCs Windows has talked to (arp -a); read only."""
    try:
        out = subprocess.run(['arp', '-a'], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].count('.') == 3 and '-' in parts[1]:
            try:
                address = ipaddress.IPv4Address(parts[0])
            except ValueError:
                continue
            if not address.is_multicast and not parts[0].endswith('.255'):
                found.append(parts[0])
    return found


def _tailscale_peers():
    """The other devices of this PC's Tailscale network that are online (asked from Tailscale itself)."""
    roots = [os.environ.get(name, '') for name in ('ProgramFiles', 'ProgramFiles(x86)')]
    programs = ['tailscale'] + [os.path.join(root, 'Tailscale', 'tailscale.exe') for root in roots if root]
    for program in programs:
        try:
            out = subprocess.run([program, 'status', '--json'], capture_output=True, text=True, timeout=10,
                                 creationflags=NO_WINDOW).stdout
            peers = (json.loads(out).get('Peer') or {}).values()
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        return [ip for peer in peers if peer.get('Online', True)
                for ip in (peer.get('TailscaleIPs') or []) if ':' not in ip]
    return []


def ping(ip):
    """Round trip to a PC in milliseconds (one Windows ping), or None."""
    try:
        out = subprocess.run(['ping', '-n', '1', '-w', '900', ip], capture_output=True, text=True, timeout=4,
                             creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for part in out.replace('<', '=').split():
        low = part.lower()
        if '=' in low and low.endswith('ms') and 'ttl' not in low:
            digits = ''.join(c for c in low.split('=')[-1] if c.isdigit())
            if digits:
                return int(digits)
    return None


def port_busy(port):
    """True when a program on this PC already listens on the port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(('127.0.0.1', port)) == 0
