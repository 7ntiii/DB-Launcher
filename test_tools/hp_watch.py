"""gdb watcher for memory writes in a game started with LICHII_GDBSTUB (twin: TWIN_GDB_A=1).
Connects, lets the game run, and takes commands from diag/twin/hp_watch.cmd (one per line):
  W ADDR [LEN]   write watchpoint (hex address)      B OFF   breakpoint at main+OFF (logged, kept)
  U              remove every watchpoint / breakpoint  Q       detach
Every hit is logged to diag/twin/hp_watch.log with pc, lr, x0-x3, the frame-pointer backtrace
(main offsets) and the watched bytes before and after the instruction (the watch is taken off,
the instruction stepped, the watch put back). HPW_LIMIT hits (default 60), then all are removed.
python diag/twin/hp_watch.py [PORT=6543] [WHO=A]"""
import os, socket, struct, sys, time
sys.path.insert(0, 'diag/net'); sys.path.insert(0, 'diag/twin')
from gdb import Gdb
from lanlog import main_base
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6543
WHO = sys.argv[2] if len(sys.argv) > 2 else 'A'
LOG, CMD = 'diag/twin/hp_watch.log', 'diag/twin/hp_watch.cmd'
LIMIT = int(os.environ.get('HPW_LIMIT', '60'))
TEXT = 0x492b000


def log(s):
    line = time.strftime('%H:%M:%S ') + s
    print(line, flush=True)
    with open(LOG, 'a') as f:
        f.write(line + '\n')


for _ in range(600):
    try:
        g = Gdb(PORT); break
    except OSError:
        time.sleep(1)
log('connected ' + g.cmd('?')[:20])
# The game stops again while it boots: nudge it for the first 20 s (as quic_watch.py does).
for _ in range(20):
    g._send('c'); time.sleep(1); g.s.sendall(b'')
    try:
        g._recv(timeout=10)
    except socket.timeout:
        pass
g._send('c')
watches, bps, hits, base = {}, set(), 0, None
dumps = []
skip, skipped = set(), 0          # pcs (main offsets) whose hits are not logged unless the bytes change (command: S OFF)


def where(a):
    return f'main+{a - base:#x}' if base is not None and base <= a < base + TEXT else f'{a:#x}'


def backtrace(fp, depth=14):
    out = []
    for _ in range(depth):
        if not fp:
            break
        try:
            fp, ret = struct.unpack('<QQ', g.mem(fp, 16))
        except Exception:
            break
        out.append(where(ret & 0xffffffffff))
    return ','.join(out)


def clear():
    for a, n in watches.items():
        g.cmd(f'z2,{a:x},{n:x}')
    for a in bps:
        g.cmd(f'z0,{a:x},4')
    watches.clear(); bps.clear()


while True:
    try:
        r = g._recv(timeout=1)
    except socket.timeout:
        if not os.path.exists(CMD):
            continue
        lines = open(CMD).read().split('\n'); os.remove(CMD)
        if base is None:
            try:
                base = main_base(WHO)
            except Exception:
                pass
        g.s.sendall(b'\x03')
        try:
            g._recv(timeout=10)
        except socket.timeout:
            log('interrupt timed out'); continue
        for ln in lines:
            p = ln.split()
            if not p:
                continue
            if p[0] == 'W':
                a, n = int(p[1], 16), int(p[2], 16) if len(p) > 2 else 4
                watches[a] = n; log(f'watch {a:#x} len {n}: {g.cmd(f"Z2,{a:x},{n:x}")} now {g.mem(a, n).hex()}')
            elif p[0] == 'B':
                a = base + int(p[1], 16)
                bps.add(a); log(f'bp {where(a)}: {g.cmd(f"Z0,{a:x},4")}')
            elif p[0] == 'D':         # D REG OFF LEN: at every breakpoint also dump LEN bytes at xREG+OFF
                dumps.append((int(p[1]), int(p[2], 16), int(p[3], 16))); log(f'dump x{p[1]}+{p[2]} len {p[3]}')
            elif p[0] == 'M':         # M BASE: main's base (when there is no LAN assist log to read it from)
                if p[1] == 'auto':    # the r-x Code mapping of main's exact size
                    import re
                    r = g.cmd('qRcmd,' + 'get mappings'.encode().hex(), timeout=30)
                    try:
                        r = bytes.fromhex(r).decode('latin1')
                    except ValueError:
                        pass
                    for a, b in re.findall(r'(0x[0-9a-f]+) - (0x[0-9a-f]+) r-x Code', r):
                        if int(b, 16) + 1 - int(a, 16) == TEXT:
                            base = int(a, 16)
                else:
                    base = int(p[1], 16)
                log(f'main base {base:#x}' if base else 'main base not found')
                open('diag/twin/hp_watch_base.txt', 'w').write(hex(base or 0))
            elif p[0] == 'S':
                skip.add(int(p[1], 16)); log(f'skip main+{int(p[1], 16):#x}')
            elif p[0] == 'U':
                clear(); dumps.clear(); hits = 0; log('all removed')
            elif p[0] == 'Q':
                clear(); log('detached'); g._send('c'); g.s.close(); sys.exit(0)
        g._send('c')
        continue
    except EOFError:
        log('closed'); break
    if r.startswith('O') or r in ('OK', ''):
        continue
    x = g.regs(); pc = x[32]
    before = {a: g.mem(a, n).hex() for a, n in watches.items()}
    text = (f'hit {r[:34]} pc={where(pc)} lr={where(x[30])} x0={x[0]:#x} x1={x[1]:#x} x2={x[2]:#x} '
            f'x3={x[3]:#x} x8={x[8]:#x} x19={x[19]:#x} x20={x[20]:#x} bt={backtrace(x[29])}')
    if pc in bps:                    # a breakpoint: the 0x60 bytes x0 points into, and [x1] (0x30)
        for reg, off, n in dumps:
            try:
                text += f' x{reg}+{off:#x}=' + g.mem(x[reg] + off, n).hex()
            except Exception:
                text += f' x{reg}+{off:#x}=?'
        try:
            text += ' x0mem=' + g.mem((x[0] - 1) & ~0, 0x60).hex() + ' x1mem=' + g.mem(x[1], 0x10).hex()
            text += ' [x1]=' + g.mem(struct.unpack('<Q', g.mem(x[1], 8))[0], 0x30).hex()
        except Exception as ex:
            text += f' (dump failed {ex!r})'
    for a, n in watches.items():
        g.cmd(f'z2,{a:x},{n:x}')
    if pc in bps:
        g.cmd(f'z0,{pc:x},4')
    try:
        g.cmd('s', timeout=10)
    except socket.timeout:
        log('step timeout')
    after = {a: g.mem(a, n).hex() for a, n in watches.items()}
    quiet = base is not None and (pc - base) in skip and before == after
    if quiet:
        skipped += 1
    else:
        log(text + ' | ' + ' '.join(f'{a:#x}:{before[a]}->{after[a]}' for a in watches) + f' (skipped {skipped})')
        hits += 1
    if hits >= LIMIT:
        clear(); log('hit limit: all removed')
    else:
        for a, n in watches.items():
            g.cmd(f'Z2,{a:x},{n:x}')
        if pc in bps:
            g.cmd(f'Z0,{pc:x},4')
    g._send('c')
