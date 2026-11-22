"""Read-only dry run before baking live-patch groups into patch_manager.cpp:
python tools/bake_check.py [--brief] DATA_FILE GROUP [GROUP..] [-- DATA_FILE GROUP [GROUP..] ..]

DATA_FILE: a diag/net/*_live.py (path, or bare name looked up in diag/net). Groups are lists of
(offset_from_main, orig_hex, new_hex, is_code). All groups given are treated as ONE bake-in set.
Per record it prints NEW (no DUSK_W_<OFF> yet), SAME (record has these new bytes) or UPDATE (old -> new),
and flags problems that would make PatchNSO drop the WHOLE built-in patch or silently clobber bytes:
  P1 orig_hex != stock game bytes (main_text/ro/data.bin; far region = zeros), or an existing record's
     _ORIGINAL != stock / != the tuple's orig, or a record size mismatch
  P2 two given groups write different bytes to the same byte
  P3 far-region / near-pool (main+0x563EE00..0x563EFFF) byte written by two given groups, or by a group and
     an existing record with other bytes; any record byte-overlapping a DIFFERENT existing record
  P4 a record at or past main's image (0x6B30000) not fully inside the far region 0xC500000..0xC50FFFF,
     or a far record with non-zero orig
  P5 a branch (b/bl/b.cond/cbz/cbnz/tbz/tbnz, adrp x16+add x16+br/blr x16) in the given groups whose
     target is not stock text and not written by an existing record or a given group
Also self-checks the CURRENT built-in records against the stock bytes (a baseline PatchNSO simulation).
--brief collapses runs of plain NEW records of one group into one line (problems are always listed).
Exit code 1 on any problem. Writes nothing."""
import importlib.util
import os
import re
import sys

WS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPP = os.path.join(WS, r'src\lichii\src\core\file_sys\patch_manager.cpp')
NSO = os.path.join(WS, r'diag\net\nso')
TEXT_END = 0x492AD90
RO_BASE, DATA_BASE = 0x492B000, 0x563F000
IMAGE_SIZE = 0x6B30000          # Loader::kDuskMainImageSize
FAR_BEGIN, FAR_END = 0xC500000, 0xC510000
POOL_BEGIN, POOL_END = 0x563EE00, 0x563F000


def load_stock():
    t = open(os.path.join(NSO, 'main_text.bin'), 'rb').read()
    ro = open(os.path.join(NSO, 'main_ro.bin'), 'rb').read()
    da = open(os.path.join(NSO, 'main_data.bin'), 'rb').read()
    assert len(t) == TEXT_END, hex(len(t))
    img = bytearray(DATA_BASE + len(da))
    img[0:len(t)] = t
    img[RO_BASE:RO_BASE + len(ro)] = ro
    img[DATA_BASE:] = da
    return bytes(img)


STOCK = load_stock()


def stock(off, n):
    b = STOCK[off:off + n]
    return b + bytes(n - len(b))


def load_cpp():
    s = open(CPP, encoding='utf-8', errors='replace').read()
    arrays = {}
    for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\};', s):
        vals = bytes(int(x, 0) for x in re.findall(r'0[xX][0-9A-Fa-f]+|\d+', m.group(3)))
        if len(vals) != int(m.group(1)):
            vals = vals.ljust(int(m.group(1)), b'\0')   # std::array zero-fills the rest
        arrays[m.group(2)] = vals
    i = s.index('constexpr std::array DUSK_LAN_RECORDS{')
    j = s.index('\n};', i)
    body = '\n'.join(l.split('//')[0] for l in s[i:j].split('\n'))
    recs = []
    for m in re.finditer(r'BuiltinPatchRecord\{\s*(0[xX][0-9A-Fa-f]+)\s*,\s*(\w+)\s*,\s*(\{\}|\w+)\s*'
                         r'(?:,\s*(true|false)\s*)?\}', body):
        off, name, orig, pad = int(m.group(1), 16), m.group(2), m.group(3), m.group(4) == 'true'
        recs.append(dict(off=off, name=name, new=arrays.get(name),
                         orig=None if orig == '{}' else arrays.get(orig), orig_name=orig, pad=pad))
    comments = dict(re.findall(r'// (0x[0-9a-fA-F]+) \((\w+)\)', s))
    return arrays, recs, comments


def hx(b):
    return b.hex().upper()


def load_data(path):
    if not os.path.exists(path):
        alt = os.path.join(WS, 'diag', 'net', path)
        path = alt if os.path.exists(alt) else alt + '.py'
    spec = importlib.util.spec_from_file_location('bake_' + os.path.basename(path).split('.')[0], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return path, mod


def sx(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def branch_target(w, a):
    if (w & 0x7C000000) == 0x14000000:
        return a + sx(w & 0x3FFFFFF, 26) * 4, 'bl' if w >> 31 else 'b'
    if (w & 0xFF000010) == 0x54000000:
        return a + sx((w >> 5) & 0x7FFFF, 19) * 4, 'b.cond'
    if (w & 0x7E000000) == 0x34000000:
        return a + sx((w >> 5) & 0x7FFFF, 19) * 4, 'cbz/cbnz'
    if (w & 0x7E000000) == 0x36000000:
        return a + sx((w >> 5) & 0x3FFF, 14) * 4, 'tbz/tbnz'
    return None


def main(argv):
    brief = '--brief' in argv
    argv = [a for a in argv if a != '--brief']
    sets, cur = [], []
    for a in argv:
        if a == '--':
            if cur:
                sets.append(cur)
            cur = []
        else:
            cur.append(a)
    if cur:
        sets.append(cur)
    if not sets or any(len(x) < 2 for x in sets):
        print(__doc__)
        return 2

    arrays, recs, comments = load_cpp()
    problems = []

    def prob(code, msg):
        if '%s %s' % (code, msg) in problems:
            return
        problems.append('%s %s' % (code, msg))
        print('  !! %s %s' % (code, msg))

    # ---- baseline: current built-in records against the stock game
    print('== baseline: %d DUSK_LAN_RECORDS rows in patch_manager.cpp' % len(recs))
    by_name, cover = {}, {}
    base_bad = 0
    for r in recs:
        if r['new'] is None or (r['orig_name'] != '{}' and r['orig'] is None):
            prob('P1', 'baseline row %s at 0x%X: array not found in source' % (r['name'], r['off']))
            base_bad += 1
            continue
        by_name.setdefault(r['name'], r)
        n = len(r['new'])
        if r['off'] >= IMAGE_SIZE:
            if not r['pad'] or r['orig'] is not None or r['off'] < FAR_BEGIN or r['off'] + n > FAR_END:
                prob('P4', 'baseline row %s at 0x%X is past the image but not a valid far record' % (r['name'], r['off']))
                base_bad += 1
        elif r['orig'] is not None and r['orig'] != stock(r['off'], len(r['orig'])):
            prob('P1', 'baseline row %s at 0x%X: _ORIGINAL %s != stock %s' % (
                r['name'], r['off'], hx(r['orig']), hx(stock(r['off'], len(r['orig'])))))
            base_bad += 1
        elif r['pad'] and stock(r['off'], n) != bytes(n):
            prob('P1', 'baseline cave %s at 0x%X is not zero in the stock game' % (r['name'], r['off']))
            base_bad += 1
        for k in range(n):
            cover.setdefault(r['off'] + k, []).append((r['name'], r['new'][k]))
    over = sorted({tuple(sorted({x[0] for x in v})) for v in cover.values() if len({x[0] for x in v}) > 1})
    for names in over:
        print('  note: existing records overlap each other: %s' % ', '.join(names))
    far_n = sum(1 for r in recs if r['off'] >= FAR_BEGIN)
    print('  stock-original check: %s; far-region rows: %d' % ('all match' if not base_bad else '%d BAD' % base_bad, far_n))

    # ---- load the groups
    items = []   # (file, group, off, orig, new, is_code)
    per_file = []
    for st in sets:
        path, mod = load_data(st[0])
        per_file.append((os.path.relpath(path, WS), st[1:]))
        for g in st[1:]:
            if not hasattr(mod, g):
                prob('P0', '%s has no group %s' % (path, g))
                continue
            for t in getattr(mod, g):
                off, o, n, c = t
                items.append((os.path.basename(path), g, off, bytes.fromhex(o), bytes.fromhex(n), bool(c)))

    writes = {}   # byte addr -> list of (group, value)
    for f, g, off, o, n, c in items:
        for k in range(len(n)):
            writes.setdefault(off + k, []).append((g, n[k]))

    # ---- per record
    status = {}   # (file, group) -> counts
    for idx, (f, g, off, o, n, c) in enumerate(items):
        key = (f, g)
        if key not in status:
            status[key] = dict(NEW=0, SAME=0, UPDATE=0, run=[])
            print('== %s %s' % (f, g))
        cnt = status[key]
        name = 'DUSK_W_%X' % off
        far = off >= IMAGE_SIZE
        pool = POOL_BEGIN <= off < POOL_END

        def flush_run():
            if cnt['run']:
                a, b = cnt['run'][0], cnt['run'][-1]
                print('  NEW     x%-4d 0x%X..0x%X' % (len(cnt['run']), a, b))
                cnt['run'] = []

        local = []

        def lp(code, msg):
            local.append((code, msg))

        if len(o) != len(n):
            lp('P1', '0x%X: orig/new lengths differ (%d/%d)' % (off, len(o), len(n)))
        st_b = stock(off, len(o))
        if far:
            if off < FAR_BEGIN or off + len(n) > FAR_END:
                lp('P4', '0x%X..0x%X is past main\'s image (0x%X) but not inside the far region 0x%X..0x%X: '
                   'PatchNSO would drop the whole patch' % (off, off + len(n), IMAGE_SIZE, FAR_BEGIN, FAR_END))
            if o != bytes(len(o)):
                lp('P4', '0x%X far record orig %s is not zero' % (off, hx(o)))
        elif o != st_b:
            hint = ''
            ex = by_name.get(name)
            if ex and ex['new'] == o:
                hint = ' (= built-in %s new bytes: a LIVE form, written on top of the shipped patch)' % name
            else:
                for g2, v in ((x[1], x[4]) for x in items if x[2] == off and x[1] != g):
                    if v == o:
                        hint = ' (= group %s new bytes: written on top of it)' % g2
            lp('P1', '0x%X orig_hex %s != stock %s%s' % (off, hx(o), hx(st_b), hint))
        ex = by_name.get(name)
        if ex is None and name in arrays:
            lp('P1', '0x%X: %s is declared but has no DUSK_LAN_RECORDS row (add tool would skip it)' % (off, name))
        if ex is not None:
            if ex['off'] != off:
                lp('P1', '%s row offset 0x%X != 0x%X' % (name, ex['off'], off))
            if len(ex['new']) != len(n):
                lp('P1', '%s size %d != %d (update tool prints SIZE MISMATCH and skips)' % (name, len(ex['new']), len(n)))
            if ex['orig'] is not None and not far:
                if ex['orig'] != stock(off, len(ex['orig'])):
                    lp('P1', '%s_ORIGINAL %s != stock' % (name, hx(ex['orig'])))
                if ex['orig'] != o and o == st_b:
                    lp('P1', '%s_ORIGINAL %s != tuple orig %s' % (name, hx(ex['orig']), hx(o)))
            if far and (ex['orig'] is not None or not ex['pad']):
                lp('P4', '%s exists as a non-cave row in the far region' % name)
            if ex['new'] == n:
                kind = 'SAME'
            else:
                kind = 'UPDATE'
                if far or pool:
                    lp('P3', '0x%X %s region word already built in with other bytes (%s, from %s)' % (
                        off, 'far' if far else 'near-pool', hx(ex['new']), comments.get('0x%x' % off, '?')))
        else:
            kind = 'NEW'
        # byte overlaps with other existing records
        others = sorted({nm for k in range(len(n)) for nm, _ in cover.get(off + k, []) if nm != name})
        if others:
            lp('P3', '0x%X..0x%X overlaps existing record(s) %s (PatchNSO copies both; later row wins)' % (
                off, off + len(n), ', '.join(others)))
        # cross-group
        for k in range(len(n)):
            ws = writes[off + k]
            gs = {x[0] for x in ws}
            if len(ws) > 1:
                vals = {x[1] for x in ws}
                if len(vals) > 1:
                    lp('P2', '0x%X written with different bytes by %s' % (off, ', '.join(sorted(gs))))
                    break
                if far or pool:
                    lp('P3', '0x%X %s word shared by %s' % (off, 'far' if far else 'near-pool', ', '.join(sorted(gs)) if len(gs) > 1 else g + ' (twice)'))
                    break
                if len(gs) == 1:
                    lp('P2', '0x%X written twice in %s' % (off, g))
                    break
        cnt[kind] += 1
        if kind == 'NEW' and not local and brief:
            if cnt['run'] and not (cnt['run'][-1] < off <= cnt['run'][-1] + 0x40):
                flush_run()
            cnt['run'].append(off)
        else:
            flush_run()
            if kind == 'UPDATE':
                print('  UPDATE  0x%-8X %s -> %s   (was %s)' % (off, hx(ex['new']), hx(n), comments.get('0x%x' % off, '?')))
            else:
                print('  %-7s 0x%-8X %s%s' % (kind, off, hx(n), '' if kind == 'NEW' else ''))
        for code, msg in local:
            prob(code, msg)
        if idx + 1 == len(items) or items[idx + 1][:2] != key:
            flush_run()

    # ---- branch targets (P5)
    print('== branch targets')

    def word_at(a):
        if a in writes:
            ws = writes[a]
            if all(a + k in writes for k in range(4)):
                return int.from_bytes(bytes(writes[a + k][-1][1] for k in range(4)), 'little')
        if all(a + k in cover for k in range(4)):
            return int.from_bytes(bytes(cover[a + k][-1][1] for k in range(4)), 'little')
        return int.from_bytes(stock(a, 4), 'little')

    def known(t):
        if 0 <= t < TEXT_END:
            return 'stock text'
        if all(t + k in writes for k in range(4)):
            return 'given group ' + writes[t][0][0]
        if all(t + k in cover for k in range(4)):
            return 'built-in ' + cover[t][0][0]
        return None

    nbr = 0
    for f, g, off, o, n, c in items:
        if not c or len(n) % 4 or off % 4:
            continue
        for k in range(0, len(n), 4):
            a = off + k
            w = int.from_bytes(n[k:k + 4], 'little')
            bt = branch_target(w, a)
            how = None
            if bt:
                t, how = bt
            elif (w & 0x9F00001F) == 0x90000010:   # adrp x16
                imm = sx((((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3), 21) << 12
                w2, w3 = word_at(a + 4), word_at(a + 8)
                if (w2 & 0xFF8003FF) == 0x91000210 and w3 in (0xD61F0200, 0xD63F0200):
                    t = (a & ~0xFFF) + imm + (((w2 >> 10) & 0xFFF) << (12 if (w2 >> 22) & 1 else 0))
                    how = 'adrp/add/%s x16' % ('br' if w3 == 0xD61F0200 else 'blr')
            if not how:
                continue
            nbr += 1
            src = known(t)
            if src is None:
                prob('P5', '%s 0x%X %s -> 0x%X: target is not stock text and not written by a built-in record '
                     'or a given group' % (g, a, how, t))
            elif not brief:
                print('  0x%X %-16s -> 0x%X (%s)' % (a, how, t, src))
    print('  %d branch words checked' % nbr)

    # ---- per-file commands
    print('== bake commands (run from %s, in this order; update_dusk_records.py also adds the NEW ones)' % WS)
    for path, groups in per_file:
        fn = os.path.basename(path)
        tot = {k: sum(status.get((fn, g), {}).get(k, 0) for g in groups) for k in ('NEW', 'SAME', 'UPDATE')}
        tool = 'update_dusk_records.py' if tot['UPDATE'] else 'add_dusk_records.py'
        if not tot['NEW'] and not tot['UPDATE']:
            print('  (nothing to do) %s %s' % (path, ' '.join(groups)))
        else:
            print('  python tools/%s %s %s    # NEW %d UPDATE %d SAME %d' % (
                tool, path.replace('\\', '/'), ' '.join(groups), tot['NEW'], tot['UPDATE'], tot['SAME']))
    t = {k: sum(v[k] for v in status.values()) for k in ('NEW', 'SAME', 'UPDATE')}
    print('SUMMARY: %d records (NEW %d, SAME %d, UPDATE %d), %d problem(s)%s' % (
        len(items), t['NEW'], t['SAME'], t['UPDATE'], len(problems),
        '' if not problems else ': ' + ', '.join('%s x%d' % (c, sum(1 for p in problems if p.startswith(c)))
                                                  for c in sorted({p[:2] for p in problems}))))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
