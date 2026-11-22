"""Which message types does a game SEND? Live tracer, no rebuild, no breakpoint.
python diag/twin/msgtrace.py AB install    hook the session transport's send functions (vt+0x38/+0x40/+0x48)
python diag/twin/msgtrace.py AB clear      forget what was seen
python diag/twin/msgtrace.py AB show       types sent since the last clear
python diag/twin/msgtrace.py AB new SECS   clear, wait, show only types that are not in the idle set
                                           (idle set = diag/twin/msg_idle_<game>.txt, made by "idle SECS")
python diag/twin/msgtrace.py AB idle SECS  record SECS of doing nothing as the idle set
Cave in the text padding main+0x492AF20 (recorder + 3 trampolines), 256-bit "seen" map at main+0x492AFA0.
The hooked functions' first instruction is moved into the trampoline (known safe ones only). w1 = message type at their entry."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

REC, MAP = 0x563E800, 0x492AFA0   # code in the rodata padding (0x563E45C..0x563F000), map in the text padding
PACIBSP = 0xD503237F
# First instructions that can run from the trampoline (no pc-relative operand).
SAFE_FIRST = {PACIBSP, 0xD1004000, 0xB9400808}   # pacibsp / sub sp,sp,#0x10 / ldr w8,[x0,#8]
SAVED = {0x1cd7c80: PACIBSP, 0x1cd79d0: PACIBSP, 0x1cd8008: 0xD1004000, 0x1cd8220: 0xB9400808}


def b(pc, t):
    return 0x14000000 | (((t - pc) // 4) & 0x3FFFFFF)


def adr(pc, rd, t):
    imm = t - pc
    return 0x10000000 | ((imm & 3) << 29) | (((imm >> 2) & 0x7FFFF) << 5) | rd


def adrp_add(pc, rd, t):
    pages = (t >> 12) - (pc >> 12)
    return [0x90000000 | ((pages & 3) << 29) | (((pages >> 2) & 0x7FFFF) << 5) | rd,
            0x91000000 | ((t & 0xFFF) << 10) | (rd << 5) | rd]


def sends(m):
    mgr = m.u64(m.u64(m.base + 0x59DFEC8))
    vt = m.u64(mgr + 0x10)
    return [m.u64(vt + s) - m.base for s in (0x38, 0x40, 0x48)] + [0x1cd7c80]   # + the broadcast helper


def install(w):
    m = Mem(w)
    fns = sends(m)
    rec = adrp_add(REC, 9, MAP) + [0x53031D8A, 0x1200098B, 0x5280002E, 0x1ACB21CE, 0x386A692B, 0x2A0E016B, 0x382A692B, 0xD61F01A0]   # type in w12
    words = list(rec)
    hooks = []
    for i, fn in enumerate(fns):
        t = REC + 4 * len(words)
        first = m.u32(m.base + fn)
        if first == b(fn, t):
            print(w, hex(fn), 'already hooked')
            first = SAVED.get(fn, PACIBSP)
        elif first not in SAFE_FIRST:
            print(w, hex(fn), 'starts with %08x, not hooked' % first)
            continue
        SAVED[fn] = first
        # the message type is w2 for send-to-member (0x1cd79d0: x1 = member), w1 for the others
        words += [0x2A0203EC if fn == 0x1cd79d0 else 0x2A0103EC, adr(t + 4, 13, t + 12), b(t + 8, REC), first, b(t + 16, fn + 4)]
        hooks.append((fn, b(fn, t)))
    m.write(m.base + MAP, bytes(32))
    m.write(m.base + REC, b''.join(struct.pack('<I', x) for x in words), code=True)
    for fn, word in hooks:
        m.write(m.base + fn, struct.pack('<I', word), code=True)
    print(w, 'hooked', [hex(f) for f, _ in hooks])


def seen(w):
    bits = Mem(w).read(Mem(w).base + MAP, 32)
    return {t for t in range(256) if bits[t >> 3] >> (t & 7) & 1}


def clear(w):
    m = Mem(w)
    m.write(m.base + MAP, bytes(32))


def fmt(s):
    return ' '.join('%02x' % t for t in sorted(s)) or '-'


games, op = sys.argv[1], sys.argv[2]
if op == 'remove':
    for w in games:
        m = Mem(w)
        for fn, first in SAVED.items():
            if m.u32(m.base + fn) >> 26 == 5:
                m.write(m.base + fn, struct.pack('<I', first), code=True)
        print(w, 'hooks removed')
elif op == 'install':
    for w in games:
        install(w)
elif op == 'clear':
    for w in games:
        clear(w)
elif op == 'show':
    for w in games:
        print(w, fmt(seen(w)))
elif op in ('idle', 'new'):
    for w in games:
        clear(w)
    time.sleep(float(sys.argv[3]))
    for w in games:
        path = 'diag/twin/msg_idle_%s.txt' % w
        s = seen(w)
        if op == 'idle':
            open(path, 'w').write(fmt(s))
            print(w, 'idle set:', fmt(s))
        else:
            try:
                idle = {int(x, 16) for x in open(path).read().split() if x != '-'}
            except OSError:
                idle = set()
            print(w, 'new:', fmt(s - idle), '| all:', fmt(s))
