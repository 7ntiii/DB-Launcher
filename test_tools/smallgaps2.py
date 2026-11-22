"""Read-only checker for diag/net/smallgaps2_live.py: python diag/twin/smallgaps2.py [GAMES=AB] [WATCH_SECONDS=0]
Prints per game: role / mode / offline flag, each group's words (stock / patched / other), and the state values that
show the features working. WATCH_SECONDS > 0: poll every 1 s, print a line only when it changed. Never writes.

State read (all [V] from main_text, smallgaps2_notes.md):
  role   u8 main+0x492AFD8 (0 = host), OFF u8 *(main+0x5B65C20)+0xBDA, MODE u32 *(main+0x5B3CE08)+0x1268,
         members = (mgr3+0x1250 - mgr3+0x1248) / 0x108, server member id u64 mgr3+0x678.
  DEEPSEA  local player chr = *(WCM+0x1A8), WCM = *(main+0x5B3CD88); module = *(*(chr+0x2470)+0x2F0):
           +0x10 u64 (low 12 bits: links set by kills, 0xE071BC), +0x18 u64 (low 12 bits: links the cleanup clears).
           Every chr-set entry with a non-zero mask is listed too (remote copies).
  SPECIAL  every chr-set chr with module *(*(c+0x2470)+0x240): +0x10 started, +0x11 timer running, +0x14 f32 timer.
           Prints counts: total / started / timer running / released-ready (+0x10 = 1, +0x11 = 0).
  SUNGOD   *(*(WCM+0x5B8)+0x50)+0x10 (s32, -1 = no request; IsExistSunGodRequest).
  CUTSCENE skip mediator *(main+0x5B9DB58) (x0 of the press 0x11B9280 from 0x1B814BC): vector {+8 begin, +0x10 end}
           of 8-byte entries {u32 cutscene id, +4 skip (kind 2 / local skip), +5 this game voted, +6/+7 x / y count
           from kind 1} (smallgaps3_notes.md). Also msgtrace.py for 0x25 (kind byte = first payload byte): with
           CUTSCENE_SKIP_ALL the presser's game sends kind 0 then kind 1 + kind 2.
  TF_TIMER_ONLY (built in) shares 0xE4A12C / 0xE4A458 with SPECIAL_INIT: its words are printed too; SPECIAL_INIT
           must show 0xE4A12C 'OTHER F40301AA' on a v3.6+ build and must NOT be applied there."""
import importlib.util
import os
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE = os.path.join(HERE, '..', 'net', 'smallgaps2_live.py')
spec = importlib.util.spec_from_file_location('sg2', LIVE)
sg2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sg2)
GROUPS = ['CUTSCENE_SKIP_ALL', 'DEEPSEA_CLEANUP', 'SPECIAL_INIT']

games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
watch = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
mems = {w: Mem(w) for w in games}


def s32(m, a):
    return struct.unpack('<i', m.read(a, 4))[0]


def f32(m, a):
    return struct.unpack('<f', m.read(a, 4))[0]


def words(m):
    out = []
    for g in GROUPS:
        st = []
        for off, orig, new, _ in getattr(sg2, g):
            cur = m.read(m.base + off, len(new) // 2).hex().upper()
            st.append('%X=%s' % (off, 'patched' if cur == new else 'orig' if cur == orig else 'OTHER ' + cur))
        out.append('  %s: %s' % (g, ', '.join(st)))
    st = []
    for off, orig, new in TF_WORDS:
        cur = m.read(m.base + off, 4).hex().upper()
        st.append('%X=%s' % (off, 'TF' if cur == new else 'stock' if cur == orig else 'OTHER ' + cur))
    out.append('  TF_TIMER_ONLY (built-in): %s' % ', '.join(st))
    cur = m.read(m.base + 0x11B932C, 4).hex().upper()
    out.append('  0x11B932C %s' % {'63000014': 'shipped CUTSCENE b (presser-only skip)',
                                   '610C0054': 'stock b.ne (shared cutscenes vote)'}.get(cur, 'OTHER ' + cur))
    return out


# trespasser_flow_live.py TF_TIMER_ONLY, built in since v3.6 (memory byte order)
TF_WORDS = ((0xE4A12C, 'E0050054', 'F40301AA'), (0xE4A130, '08404039', 'F30300AA'),
            (0xE4A134, 'F40301AA', '68424039'), (0xE4A138, 'F30300AA', '40000054'),
            (0xE4A458, '00050054', '1F2003D5'))
SKIP_MED_G = 0x5B9DB58   # CSRemoSkipMediator pointer, [V 0x1B814BC..0x1B814C4]


def skip_entries(m):
    med = m.u64(m.base + SKIP_MED_G)
    if not med:
        return '  CUTSCENE mediator: null'
    b, e = m.u64(med + 8), m.u64(med + 0x10)
    n = (e - b) // 8 if b and e and e >= b else 0
    ents = []
    for k in range(min(n, 8)):
        raw = m.read(b + 8 * k, 8)
        cid = struct.unpack('<I', raw[:4])[0]
        ents.append('%d skip %d voted %d count %d/%d' % (cid, raw[4], raw[5], raw[6], raw[7]))
    return '  CUTSCENE entries %d: %s' % (n, '; '.join(ents) or '-')


def chrset(m, wcm):
    sm = m.u64(wcm + 0x540)
    if not sm:
        return
    for si in range(min(m.u32(sm + 8), 16)):
        s = m.u64(sm + 0x10 + 8 * si)
        if not s:
            continue
        n, cs = m.u32(s + 0x10), m.u64(s + 8)
        if not n or n > 8192 or not cs:
            continue
        arr = m.u64(cs + 8)
        for j in range(n):
            c = m.u64(arr + 0x38 * j)
            if c:
                yield si, j, c


def state(w):
    m = mems[w]
    lines = []
    role = m.read(m.base + 0x492AFD8, 1)[0]
    off = m.read(m.u64(m.base + 0x5B65C20) + 0xBDA, 1)[0]
    mgr3 = m.u64(m.base + 0x5B3CE08)
    mode = m.u32(mgr3 + 0x1268) if mgr3 else -1
    members = (m.u64(mgr3 + 0x1250) - m.u64(mgr3 + 0x1248)) // 0x108 if mgr3 else -1
    lines.append('%s role %d (%s) OFF %d MODE %d members %d server-member %X' % (
        w, role, 'host' if role == 0 else 'guest', off, mode, members, m.u64(mgr3 + 0x678) if mgr3 else 0))
    lines += words(m)
    try:
        lines.append(skip_entries(m))
    except Exception as e:
        lines.append('  CUTSCENE entries unreadable: %s' % e)
    wcm = m.u64(m.base + 0x5B3CD88)
    if not wcm:
        lines.append('  no WCM (not in a map)')
        return '\n'.join(lines)
    # Sun God request (expect -1 all match: no script in the build asks for it)
    sgo = m.u64(m.u64(wcm + 0x5B8) + 0x50) if m.u64(wcm + 0x5B8) else 0
    lines.append('  SUNGOD request id %s' % (s32(m, sgo + 0x10) if sgo else 'no object'))
    # deep-sea links
    lp = m.u64(wcm + 0x1A8)
    if lp:
        mod = m.u64(m.u64(lp + 0x2470) + 0x2F0)
        if mod:
            lines.append('  DEEPSEA local +0x10 %03X +0x18 %03X' % (m.u64(mod + 0x10) & 0xFFF, m.u64(mod + 0x18) & 0xFFF))
        else:
            lines.append('  DEEPSEA local: no module')
    total = started = running = ready = 0
    other_ds = []
    for si, j, c in chrset(m, wcm):
        try:
            mods = m.u64(c + 0x2470)
            if not mods:
                continue
            ds = m.u64(mods + 0x2F0)
            if ds and c != lp:
                a, b = m.u64(ds + 0x10) & 0xFFF, m.u64(ds + 0x18) & 0xFFF
                if a or b:
                    other_ds.append('%d/%d:%03X/%03X' % (si, j, a, b))
            sp = m.u64(mods + 0x240)
            if not sp:
                continue
            total += 1
            b10, b11 = m.read(sp + 0x10, 2)
            started += b10 != 0
            running += b10 != 0 and b11 != 0
            ready += b10 != 0 and b11 == 0
        except Exception:
            pass
    if other_ds:
        lines.append('  DEEPSEA other chrs (set/index:+0x10/+0x18) ' + ' '.join(other_ds[:12]))
    lines.append('  SPECIAL modules %d started %d timer-running %d release-ready %d' % (total, started, running, ready))
    return '\n'.join(lines)


last = {}
t0 = time.time()
while True:
    for w in games:
        try:
            s = state(w)
        except Exception as e:  # game closed or debug server busy
            s = '%s read failed: %s' % (w, e)
        if s != last.get(w):
            print('%6.1f %s' % (time.time() - t0, s), flush=True)
            last[w] = s
    if watch <= 0 or time.time() - t0 > watch:
        break
    time.sleep(1.0)
