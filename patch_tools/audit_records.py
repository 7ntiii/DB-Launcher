"""Static, read-only audit of the Duskbloods LAN built-in patch records.

python tools/audit_records.py [--json out.json]

Reads (never writes anything in the repo): src/lichii/src/core/file_sys/patch_manager.cpp (working tree
and `git show HEAD:`), diag/net/nso/main_{text,ro,data}.bin, diag/net/*_live.py, diag/net/cave_registry.md,
src/lichii/src/core/dusk_lan.cpp.  Prints a report on stdout.
"""
import ast
import glob
import os
import re
import struct
import subprocess
import sys

import capstone
from capstone import arm64 as A

WS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
NET = os.path.join(WS, 'diag', 'net')
LICHII = os.path.join(WS, 'src', 'lichii')
CPP = os.path.join(LICHII, 'src', 'core', 'file_sys', 'patch_manager.cpp')
LAN = os.path.join(LICHII, 'src', 'core', 'dusk_lan.cpp')

TEXT_END = 0x492AD90          # main_text.bin size
TEXT_PAGE_END = 0x492B000
RO_BASE = 0x492B000
NEAR_LO, NEAR_HI = 0x563EE00, 0x563F000
RO_PAD = 0x563E45C            # ro file end; zero padding (v3.5 caves + NEAR_TRAMP pool) up to 0x563F000
DATA_BASE = 0x563F000
IMAGE_END = 0x6B30000         # kDuskMainImageSize
FAR_LO, FAR_HI = 0xC500000, 0xC510000
FAR_DATA = 0xC50F000

# ---------------------------------------------------------------- stock image
TEXT = open(os.path.join(NET, 'nso', 'main_text.bin'), 'rb').read()
RO = open(os.path.join(NET, 'nso', 'main_ro.bin'), 'rb').read()
DATA = open(os.path.join(NET, 'nso', 'main_data.bin'), 'rb').read()
assert len(TEXT) == TEXT_END, hex(len(TEXT))


def stock(a, n):
    out = bytearray()
    for i in range(a, a + n):
        if i < len(TEXT):
            out.append(TEXT[i])
        elif RO_BASE <= i < RO_BASE + len(RO):
            out.append(RO[i - RO_BASE])
        elif DATA_BASE <= i < DATA_BASE + len(DATA):
            out.append(DATA[i - DATA_BASE])
        else:
            out.append(0)
    return bytes(out)


# ---------------------------------------------------------------- cpp parsing
ARR_RE = re.compile(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{(.*?)\};', re.S)
REC_RE = re.compile(r'BuiltinPatchRecord\{\s*(0x[0-9A-Fa-f]+)\s*,\s*(\w+)\s*,\s*(\{\}|\w+)\s*(?:,\s*(true|false))?\s*\}')


def parse_cpp(src):
    nocom = re.sub(r'//[^\n]*', '', src)
    arrays = {}
    for m in ARR_RE.finditer(nocom):
        n, name, body = int(m.group(1)), m.group(2), m.group(3)
        vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]+)', body)]
        arrays[name] = (n, bytes(vals))
    m = re.search(r'constexpr\s+std::array\s+DUSK_LAN_RECORDS\s*\{(.*?)\n\};', nocom, re.S)
    recs = []
    for i, r in enumerate(REC_RE.finditer(m.group(1))):
        off = int(r.group(1), 16)
        name = r.group(2)
        oname = None if r.group(3) == '{}' else r.group(3)
        pad = r.group(4) == 'true'
        recs.append(dict(idx=i, off=off, name=name, oname=oname, pad=pad))
    for r in recs:
        n, b = arrays.get(r['name'], (None, None))
        if b is not None and len(b) == 0 and n:
            b = bytes(n)          # `std::array<u8, N> X{};` = N zeros
        r['decl'] = n
        r['bytes'] = b
        if r['oname']:
            n2, o = arrays.get(r['oname'], (None, None))
            if o is not None and len(o) == 0 and n2:
                o = bytes(n2)
            r['odecl'] = n2
            r['orig'] = o
        else:
            r['odecl'] = 0
            r['orig'] = b''
    return arrays, recs


def region(a):
    if a < TEXT_END:
        return 'text'
    if a < TEXT_PAGE_END:
        return 'pad'
    if a < RO_PAD:
        return 'ro'
    if a < NEAR_HI:
        return 'near'
    if a < IMAGE_END:
        return 'data'
    if FAR_LO <= a < FAR_DATA:
        return 'far'
    if FAR_DATA <= a < FAR_HI:
        return 'fardata'
    return 'outside'


CODE_REGIONS = ('text', 'pad', 'near', 'far')

# ---------------------------------------------------------------- live data files
def live_index():
    idx = {}
    for f in sorted(glob.glob(os.path.join(NET, '*_live.py'))):
        try:
            tree = ast.parse(open(f, encoding='utf-8', errors='replace').read())
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)):
                try:
                    val = ast.literal_eval(node.value)
                except Exception:
                    continue
                gname = node.targets[0].id if isinstance(node.targets[0], ast.Name) else '?'
                for t in val:
                    if isinstance(t, tuple) and len(t) >= 3 and isinstance(t[0], int):
                        idx.setdefault(t[0], []).append((os.path.basename(f), gname, t[1], t[2]))
    return idx


def registry():
    rows = []
    for line in open(os.path.join(NET, 'cave_registry.md'), encoding='utf-8'):
        m = re.match(r'\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*0x([0-9A-Fa-f]+)\.\.0x([0-9A-Fa-f]+)\s*\|(.*)\|', line)
        if m:
            rows.append((m.group(1), m.group(2), int(m.group(3), 16), int(m.group(4), 16), m.group(5).strip()))
    return rows


# ---------------------------------------------------------------- main audit
def main():
    out = []
    P = out.append
    src = open(CPP, encoding='utf-8').read()
    arrays, recs = parse_cpp(src)
    head_src = subprocess.run(['git', '-C', LICHII, 'show', 'HEAD:src/core/file_sys/patch_manager.cpp'],
                              capture_output=True, text=True, encoding='utf-8').stdout
    _, hrecs = parse_cpp(head_src)
    P('records now: %d, HEAD: %d' % (len(recs), len(hrecs)))

    # (1)(2)(8) per-record checks, PatchNSO rules
    problems = []
    for r in recs:
        off, b, o = r['off'], r['bytes'], r['orig']
        tag = '0x%X %s' % (off, r['name'])
        if b is None:
            problems.append(tag + ': bytes array not found'); continue
        if r['decl'] != len(b):
            problems.append(tag + ': declared %d bytes, %d listed' % (r['decl'], len(b)))
        if r['oname'] and r['orig'] is None:
            problems.append(tag + ': original array %s not found' % r['oname']); continue
        if r['oname'] and r['odecl'] != len(o):
            problems.append(tag + ': original declared %d, %d listed' % (r['odecl'], len(o)))
        reg = region(off)
        end = off + len(b)
        if off >= IMAGE_END:
            if not (r['pad'] and not r['oname'] and FAR_LO <= off and end <= FAR_HI):
                problems.append(tag + ': far record breaks PatchNSO rule (pad=%s orig=%s range %X..%X)'
                                % (r['pad'], r['oname'], off, end))
        elif r['pad']:
            if not (off >= TEXT_END and end <= TEXT_PAGE_END) or stock(off, len(b)).strip(b'\0'):
                problems.append(tag + ': executable_padding record outside text padding / not zero')
            if r['oname']:
                problems.append(tag + ': padding record also has an original')
        else:
            if not r['oname']:
                problems.append(tag + ': non-far, non-padding record without original')
            elif len(o) != len(b):
                problems.append(tag + ': size mismatch bytes %d orig %d' % (len(b), len(o)))
            if o != stock(off, len(o)):
                problems.append(tag + ': ORIGINAL != stock (%s vs %s)' % (o.hex(), stock(off, len(o)).hex()))
            if end > IMAGE_END:
                problems.append(tag + ': crosses image end')
        if off % 4 and reg in CODE_REGIONS:
            problems.append(tag + ': unaligned code record')
        r['region'] = reg
        r['end'] = end
    # overlaps
    srt = sorted(recs, key=lambda r: (r['off'], r['end']))
    overlaps = []
    for a, c in zip(srt, srt[1:]):
        if c['off'] < a['end']:
            overlaps.append('0x%X %s [..0x%X) overlaps 0x%X %s' % (a['off'], a['name'], a['end'], c['off'], c['name']))
    # also non-adjacent overlaps
    maxend, maxr = -1, None
    for r in srt:
        if r['off'] < maxend and maxr is not None and not any(('%s' % r['name']) in x for x in overlaps):
            overlaps.append('0x%X %s inside 0x%X %s' % (r['off'], r['name'], maxr['off'], maxr['name']))
        if r['end'] > maxend:
            maxend, maxr = r['end'], r
    dup_names = {}
    for r in recs:
        dup_names.setdefault(r['name'], []).append(r['off'])
    dups = {k: v for k, v in dup_names.items() if len(v) > 1}
    P('\n## (1)(2)(8) record checks: %d problems' % len(problems))
    out.extend('  ' + p for p in problems)
    P('overlaps: %d' % len(overlaps))
    out.extend('  ' + p for p in overlaps)
    P('array used by several records: %s' % {k: [hex(x) for x in v] for k, v in dups.items()})
    P('regions: %s' % {k: sum(1 for r in recs if r['region'] == k) for k in
                       ('text', 'pad', 'ro', 'near', 'data', 'far', 'fardata', 'outside')})

    # patched image (sparse): word map
    patched = {}
    owner = {}
    for r in recs:
        for i, byte in enumerate(r['bytes'] or b''):
            patched[r['off'] + i] = byte
            owner[r['off'] + i] = r

    def pbyte(a):
        return patched[a] if a in patched else stock(a, 1)[0]

    def pword(a):
        return struct.unpack('<I', bytes(pbyte(a + i) for i in range(4)))[0]

    def written(a):
        return a in patched

    md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
    md.detail = True

    def xname(reg):
        n = md.reg_name(reg)
        if n and n[0] == 'w' and n[1:].isdigit():
            n = 'x' + n[1:]
        return n

    refs = []   # (src_rec, src_pc, kind, target)
    data_refs = []  # (src_rec, pc, addr, mnemonic)
    undecodable = []
    # contiguous runs of written code words (records are mostly one word each)
    runs = []
    for r in sorted((r for r in recs if r['region'] in CODE_REGIONS and r['bytes']), key=lambda r: r['off']):
        if runs and runs[-1][1] == r['off'] and region(runs[-1][0]) == r['region']:
            runs[-1][1] = r['end']
        else:
            runs.append([r['off'], r['end']])
    RUNS = runs
    for lo, hi in runs:
        b = bytes(pbyte(a) for a in range(lo, hi))
        tracked = {}   # reg -> (addr, kind) kind 'page' or 'full'
        n = len(b) // 4
        for k in range(n):
            pc = lo + 4 * k
            r = owner[pc]
            w = struct.unpack_from('<I', b, 4 * k)[0]
            ins = list(md.disasm(b[4 * k:4 * k + 4], pc))
            if not ins:
                if w != 0:
                    undecodable.append((r, pc, w))
                tracked.clear()
                continue
            i = ins[0]
            mn = i.mnemonic
            ops = i.operands
            if mn in ('b', 'bl') or mn.startswith('b.') or mn in ('cbz', 'cbnz', 'tbz', 'tbnz'):
                t = ops[-1].imm
                refs.append((r, pc, mn, t))
            elif mn == 'adr':
                tracked[xname(ops[0].reg)] = (ops[1].imm, 'full')
                data_refs.append((r, pc, ops[1].imm, 'adr'))
                continue
            elif mn == 'adrp':
                tracked[xname(ops[0].reg)] = (ops[1].imm, 'page')
                continue
            elif mn == 'add' and len(ops) == 3 and ops[2].type == A.ARM64_OP_IMM and xname(ops[1].reg) in tracked:
                base, kind = tracked[xname(ops[1].reg)]
                sh = 0
                if ops[2].shift.type != 0:
                    sh = ops[2].shift.value
                addr = base + (ops[2].imm << sh)
                tracked[xname(ops[0].reg)] = (addr, 'full')
                if region(addr) in ('fardata', 'pad', 'near', 'data', 'ro') and region(addr) != 'ro':
                    data_refs.append((r, pc, addr, 'add'))
                continue
            elif mn in ('br', 'blr') and xname(ops[0].reg) in tracked:
                t, kind = tracked[xname(ops[0].reg)]
                refs.append((r, pc, mn + '_far', t))
            else:
                for op in ops:
                    if op.type == A.ARM64_OP_MEM and xname(op.mem.base) in tracked:
                        base, kind = tracked[xname(op.mem.base)]
                        addr = base + op.mem.disp
                        if region(addr) in ('fardata', 'far', 'pad', 'near'):
                            data_refs.append((r, pc, addr, mn))
            # invalidate written regs
            try:
                _, wr = i.regs_access()
                for reg in wr:
                    tracked.pop(xname(reg), None)
            except Exception:
                pass
            if mn in ('b', 'br', 'ret'):
                tracked.clear()

    # (3) branch targets
    bad = []
    for (r, pc, kind, t) in refs:
        reg = region(t)
        why = None
        if t % 4:
            why = 'unaligned'
        elif reg == 'text':
            if pword(t) == 0:
                why = 'lands on a zero word in text'
            elif not list(md.disasm(stock(t, 4) if not written(t) else struct.pack('<I', pword(t)), t)):
                why = 'lands on an undecodable word'
        elif reg in ('pad', 'near', 'far'):
            if not written(t):
                why = 'lands in UNWRITTEN %s space' % reg
            elif pword(t) == 0:
                why = 'lands on a written zero word'
        else:
            why = 'lands in %s' % reg
        if kind == 'adr' and why is None:
            continue
        if why:
            bad.append('0x%X (%s) %s -> 0x%X: %s' % (pc, r['name'], kind, t, why))
    P('\n## (3) branches decoded: %d, bad: %d' % (len(refs), len(bad)))
    out.extend('  ' + x for x in bad)
    P('undecodable nonzero words in code records: %d' % len(undecodable))
    for (r, pc, w) in undecodable[:40]:
        P('  0x%X %s word %08X' % (pc, r['name'], w))

    # (4) unreferenced caves. Unit = registry row, else a named (non DUSK_W_) record, else a run.
    LIVE = live_index()
    REG = registry()

    def feat(a):
        names = ['%s:%s' % (f, g) for (f, g, _, _) in LIVE.get(a, [])]
        regs = ['%s/%s' % (o, t) for (o, t, lo, hi, _) in REG if lo <= a < hi]
        return ', '.join(sorted(set(names))[:3] + regs)

    def unit_of(a):
        if a not in owner or region(a) not in ('pad', 'near', 'far'):
            return None
        for (o, t, lo, hi, _) in REG:
            if lo <= a < hi and region(lo) in ('near', 'far'):
                return ('reg', lo, hi, '%s/%s' % (o, t))
        r = owner[a]
        if not r['name'].startswith('DUSK_W_'):
            return ('rec', r['off'], r['end'], r['name'])
        for lo, hi in RUNS:
            if lo <= a < hi:
                return ('run', lo, hi, 'run')
        return None

    units = {}
    for r in recs:
        for a in range(r['off'], r['end'], 4):
            u = unit_of(a)
            if u:
                units.setdefault(u, set()).add(a)
    inbound = {u: set() for u in units}
    edges = {}
    text_src = {u: set() for u in units}
    for (r, pc, kind, t) in refs:
        tu = unit_of(t)
        su = unit_of(pc)
        if tu is None or tu == su:
            continue
        inbound[tu].add(su if su else ('text', pc))
        edges.setdefault(su if su else 'ROOT', set()).add(tu)
    # fall-through: last word before a unit belongs to another unit and is not an unconditional jump
    for u in units:
        lo = min(units[u])
        pu = unit_of(lo - 4)
        if pu is not None and pu != u:
            w = pword(lo - 4)
            uncond = (w & 0xFC000000) == 0x14000000 or (w & 0xFFFFFC1F) in (0xD61F0000, 0xD65F0000)
            if not uncond and w != 0:
                inbound[u].add(pu)
                edges.setdefault(pu, set()).add(u)
    # runtime-written hook words in dusk_lan.cpp (b targets)
    lan = open(LAN, encoding='utf-8', errors='replace').read()
    runtime_roots = []
    m = re.search(r'BB_HOOK = (0x[0-9A-F]+).*?BB_HOOK_PATCHED = (0x[0-9A-F]+)', lan, re.S)
    if m:
        site, w = int(m.group(1), 16), int(m.group(2), 16)
        t = site + (((w & 0x3FFFFFF) ^ 0x2000000) - 0x2000000) * 4
        tu = unit_of(t)
        runtime_roots.append((site, t, tu))
        if tu:
            inbound[tu].add(('runtime', site))
            edges.setdefault('ROOT', set()).add(tu)
    seen = set()
    stack = ['ROOT']
    while stack:
        x = stack.pop()
        for y in edges.get(x, ()):
            if y not in seen:
                seen.add(y)
                stack.append(y)
    unref = [u for u in units if not inbound[u]]
    unreach = [u for u in units if inbound[u] and u not in seen]

    def uname(u):
        return '0x%X..0x%X %s %s [%s]' % (u[1], u[2], u[0], u[3], feat(min(units[u])))
    P('\n## (4) cave units: %d; with no inbound reference: %d' % (len(units), len(unref)))
    for u in sorted(unref, key=lambda u: u[1]):
        P('  ' + uname(u))
    P('units reached only from unreferenced/unreachable units: %d' % len(unreach))
    for u in sorted(unreach, key=lambda u: u[1]):
        P('  %s  <- %s' % (uname(u), [x[3] if len(x) > 3 else x for x in inbound[u]]))
    P('runtime hook roots (dusk_lan.cpp): %s' % [('0x%X->0x%X' % (s, t), tu[3] if tu else None)
                                                for (s, t, tu) in runtime_roots])
    # units whose words are not all written (holes inside a registry row are fine: report only)
    for u in sorted(units, key=lambda u: u[1]):
        if u[0] == 'reg':
            holes = [a for a in range(u[1], u[2], 4) if a not in owner]
            if holes and any(h < max(units[u]) for h in holes):
                P('  note: registry row %s has %d unwritten words inside its written span' % (u[3], sum(1 for h in holes if h < max(units[u]))))

    # (5) no-op hooks
    noops = [r for r in recs if r['oname'] and r['bytes'] == r['orig']]
    P('\n## (5) records with new == original: %d' % len(noops))
    for r in noops:
        P('  0x%X %s %s [%s]' % (r['off'], r['name'], r['bytes'].hex(), feat(r['off'])))

    # (6) data refs
    P('\n## (6) far-data / padding data references')
    fd_recs = [r for r in recs if r['region'] == 'fardata']
    P('records writing far data: %d %s' % (len(fd_recs), [('0x%X' % r['off'], len(r['bytes'])) for r in fd_recs]))
    addrs = {}
    for (r, pc, addr, mn) in data_refs:
        addrs.setdefault(addr, []).append((pc, mn, r['name']))
    regrows = [(o, t, lo, hi) for (o, t, lo, hi, _) in REG]
    lan_addrs = {'MAP_INBOX': (0xC50F000, 0xC50F1F8), 'MAP_FED': (0xC50F1F8, 0xC50F200),
                 'BB_BOX': (0xC50F210, 0xC50F21C)}
    for a in sorted(addrs):
        if region(a) != 'fardata':
            continue
        rows = ['%s/%s' % (o, t) for (o, t, lo, hi) in regrows if lo <= a < hi]
        lans = [k for k, (lo, hi) in lan_addrs.items() if lo <= a < hi]
        uses = addrs[a]
        P('  0x%X  rows=%s lan=%s  uses=%d e.g. %s' % (a, rows or 'UNCLAIMED', lans, len(uses),
                                                       ['0x%X %s' % (pc, mn) for pc, mn, _ in uses[:4]]))
    # registry overlaps
    rov = []
    rr = sorted(regrows, key=lambda x: x[2])
    for i in range(len(rr)):
        for j in range(i + 1, len(rr)):
            if rr[j][2] < rr[i][3] and rr[i][2] < rr[j][3]:
                rov.append('%s/%s 0x%X..0x%X vs %s/%s 0x%X..0x%X' % (rr[i][0], rr[i][1], rr[i][2], rr[i][3],
                                                                   rr[j][0], rr[j][1], rr[j][2], rr[j][3]))
    P('registry row overlaps: %d' % len(rov))
    out.extend('  ' + x for x in rov)
    # data refs into far CODE / near / pad (stores there?)
    odd = [(a, u) for a, u in addrs.items() if region(a) in ('far', 'near')]
    P('data refs into far code / near pool: %d' % len(odd))
    for a, u in sorted(odd)[:30]:
        P('  0x%X %s' % (a, ['0x%X %s %s' % x for x in u[:3]]))
    pad_refs = sorted(a for a in addrs if region(a) == 'pad')
    P('data refs into text padding: %s' % [hex(a) for a in pad_refs])
    # registry rows with no record and records in far not covered by registry
    uncovered = []
    for r in recs:
        if r['region'] in ('far', 'near'):
            for a in range(r['off'], r['end'], 4):
                if not any(lo <= a < hi for (_, _, lo, hi) in regrows):
                    uncovered.append(a)
    P('far/near written words outside any registry row: %d (first %s)' % (len(uncovered),
                                                                        [hex(x) for x in uncovered[:12]]))

    # (7) HEAD diff
    P('\n## (7) HEAD comparison')
    hmap = {}
    for r in hrecs:
        hmap.setdefault(r['off'], []).append(r)
    cmap = {}
    for r in recs:
        cmap.setdefault(r['off'], []).append(r)
    removed, changed = [], []
    for off, hl in sorted(hmap.items()):
        h = hl[0]
        if off not in cmap:
            # maybe covered by a bigger current record
            cov = owner.get(off)
            removed.append((h, cov))
            continue
        c = cmap[off][0]
        if c['bytes'] != h['bytes'] or c['orig'] != h['orig']:
            changed.append((h, c))
    P('HEAD records removed (offset no longer a record start): %d' % len(removed))
    for h, cov in removed:
        P('  0x%X %s (%d bytes) covered-by=%s [%s]' % (h['off'], h['name'], len(h['bytes'] or b''),
                                                       cov['name'] if cov else None, feat(h['off'])))
    P('HEAD records with changed bytes/orig: %d' % len(changed))
    for h, c in changed:
        P('  0x%X %s: %s -> %s %s [%s]' % (h['off'], h['name'], (h['bytes'] or b'').hex()[:32],
                                          (c['bytes'] or b'').hex()[:32],
                                          '(orig changed)' if c['orig'] != h['orig'] else '', feat(h['off'])))
    # HEAD words whose patched value differs now (covers merges)
    hp = {}
    for r in hrecs:
        for i, byte in enumerate(r['bytes'] or b''):
            hp[r['off'] + i] = byte
    diffw = sorted(set(a & ~3 for a in hp if pbyte(a) != hp[a]))
    P('HEAD patched words that differ in the current patched image: %d' % len(diffw))
    for a in diffw:
        P('  0x%X head=%08X now=%08X stock=%08X [%s]' % (
            a, struct.unpack('<I', bytes(hp.get(a + i, stock(a + i, 1)[0]) for i in range(4)))[0], pword(a),
            struct.unpack('<I', stock(a, 4))[0], feat(a)))
    # current records that came from no live file and not from HEAD
    new_offs = [r for r in recs if r['off'] not in hmap]
    nolive = [r for r in new_offs if not any(a in LIVE for a in range(r['off'], r['end'], 4))]
    P('new records: %d, of which with no *_live.py entry: %d %s' % (len(new_offs), len(nolive),
                                                                   [hex(r['off']) for r in nolive[:20]]))
    # live mismatches: record word != live new word for any live entry of that address
    mism = []
    for r in new_offs:
        for a in range(r['off'], r['end'], 4):
            ents = LIVE.get(a)
            if not ents:
                continue
            nw = struct.pack('<I', pword(a)).hex().upper()
            if not any(e[3].upper() == nw for e in ents):
                mism.append('0x%X now %s live %s' % (a, nw, sorted(set('%s:%s=%s' % (e[0], e[1], e[3]) for e in ents))[:3]))
    P('new-record words matching none of their *_live.py entries: %d' % len(mism))
    out.extend('  ' + x for x in mism[:60])

    # runtime words dusk_lan.cpp toggles: patched word must be one of its known values
    P('\n## dusk_lan.cpp runtime words')
    pairs = [('MAP_DISPATCH', 'MAP_DISPATCH_ORIGINAL', 'MAP_DISPATCH_CLOSE'),
             ('THIRD_WAIT', 'THIRD_WAIT_ORIGINAL', 'THIRD_WAIT_GO'),
             ('START_AREA_GATE', 'START_AREA_GATE_WAIT', None),
             ('START_LIST_READ', 'START_LIST_READ_ANY', None),
             ('COMMEND_EVAL_GATE', 'COMMEND_EVAL_NOP', None),
             ('RULE_KEEP_WORD', 'RULE_KEEP_NOP', None),
             ('BB_HOOK', 'BB_HOOK_STOCK', 'BB_HOOK_PATCHED')]

    def lconst(n):
        m = re.search(r'constexpr u(?:32|64) %s = (0x[0-9A-Fa-f]+)' % n, lan)
        return int(m.group(1), 16) if m else None
    for site, v1, v2 in pairs:
        a = lconst(site)
        if a is None:
            continue
        P('  %s 0x%X: stock=%08X patched=%08X rec=%s  %s=%s %s=%s' % (
            site, a, struct.unpack('<I', stock(a, 4))[0], pword(a), owner[a]['name'] if a in owner else None,
            v1, '%08X' % lconst(v1) if lconst(v1) is not None else None,
            v2, '%08X' % lconst(v2) if v2 and lconst(v2) is not None else None))
    print('\n'.join(out))


if __name__ == '__main__':
    main()
