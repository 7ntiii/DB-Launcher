"""Sigil (sub quest) state of the twin games. READ ONLY: no writes, no button presses.
python diag/twin/sigils.py AB        (any set of games, e.g. A, AB, ABC)

Per game:
  1. the Bloodsworn / sigil choice (pgd+0x10C, pgd+0xEC8) of the local player;
  2. every input of the 0x88 producer 0x1195E40 for the local player, in code order, PASS / FAIL / INFO;
  2b. the producer / apply walk P1..P10, A0..A4 with live param lookups (sigil_why_notes.md);
  3. the sigil patches live in code;
  4. the RESULT: pgd+0x46E0 (quest) / +0x46E4 of every PlayerGameData. The apply 0x1195C40 looks the player up
     with the pgd mediator 0xCEA240 (kind 0x3F, functor 0xCEEB78 compares pgd+0xD0 and returns the pgd), so the
     fields are on the PGD, not on the chr [V]. -1 = ctor value (0xD134C0, never applied), 10/30/200/240 own, 20.. passive;
  5. the sub quest manager list; 5b. SQM key coverage per numbered pgd (PRESENT / MISSING = final for the match,
     stale keys, module+0x79), diag/net/sigil9_notes.md 3;
  6. per player: entry (pgd slots), each slot module (quest, state, steps, progress);
  7. under each module: the condition objects (class C holds the targets at +0xC8 / +0xCC, SELF! if a target is
     the player itself; class B holds its OWNER at +0xC8 and the wanted quest at +0xCC), completion (+0x60 dirty,
     B +0xD4 done), the authority word state (stage C2); "auth N" is the class's stock value, not the live word;
     per B/C condition a "listen" line (pairing listener root+0xA0, module+0x79, kill count) and one line per
     paired target handle (player, team bit in module+0x38: what the kill check needs; sigil6_notes.md);
     award line: pgd+0x46D8 win-point object, +0x11 guard (0 = the sub quest Virtue lands on this pgd), pgd+0x42C8;
  8. the counter ids of the award;
  9. sigil3 / sigil_nc group words (stock / PATCHED) and the 0xCF8F74 item gate; per module a "flow" line (built /
     active holder, state, team mask, writer masks + owner flag, reward counters) that names where it stops.
Notes: diag/net/sigil3_notes.md (stage C / D gates), diag/net/sigil_enable_notes.md, sigil_full_notes.md, sigil_stage_notes.md."""
import math
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, PGD_G, PAR_G, GAMEDATA_G

RULE_G = 0x5B65C70          # byte rule index for the +0x19 mask test                      [V 0x1195FEC]
PRODUCER_OBJ_G = 0x5B44E88  # producer needs it non-null and its +0xB8 row               [V 0x1195E68/0x1195E98]
SQM_G = 0x5B3CE18           # sub quest manager, x0 of 0x1181D80 / the apply             [V]
MGR3_G = 0x5B3CE08          # apply is skipped when null (0x11963FC)                     [V]
ROLE_B = 0x492AFD8          # role byte the shipped caves test (0 = host)                [V caves]

PRESET = {
    600000: ('Albert', 1010000), 600001: ('Albert', None),
    600010: ('Bloodhand Jan', 1010020), 600011: ('Bloodhand Jan', None),
    600020: ('Trang Lanh', 1010000), 600021: ('Trang Lanh', None),
    600030: ('Sniper Layla', 1010010), 600031: ('Sniper Layla', None),
    600040: ('Senator Samir Patres', 1010100), 600041: ('Senator Samir Patres', None),
    600050: ('Zork', 1010010), 600051: ('Zork', None),
}
SKILL = {1010000: 'Sigil of a Sworn Enemy', 1010010: 'Sigil of an Old Friend',
         1010020: 'Sigil of the Eye of Muralis', 1010100: 'Sigil of Love Ephemeral'}
SKILL_QUEST = {1010000: 10, 1010010: 30, 1010020: 200, 1010100: 240}         # SkillParam +0x64 [V]
QUEST = {10: 'Sworn Enemy', 20: 'Passive Sworn Enemy', 30: 'Old Friend', 40: 'Passive Old Friend',
         200: 'Eye of Muralis', 205: 'Passive Heretic', 240: 'Love Ephemeral', 250: 'Passive Love Ephemeral'}
QUEST_ROW = {10: (0x0E, 1, 10), 30: (0x02, 1, 30), 200: (0x1E, 0, -1), 240: (0x06, 1, 250)}  # +0x19, +0x50, +0 [V]
CODE = [('SUBQUEST gate 0x1181E48', 0x1181E48, '68000034', '4AF31215'),
        ('SUBQUEST send 0x1196404', 0x1196404, '0FFEFF97', 'E3A11295'),
        ('SUBQUEST reread 0x1140B10', 0x1140B10, '3629FB97', '34F81395'),
        ('SIGIL_OWN own id 0x11963CC', 0x11963CC, '7FC11EB8', 'BFA11295'),
        ('SIGIL_OWN guests produce 0x563EB7C', 0x563EB7C, '49000035', '1F2003D5'),
        ('SIGIL_OWN host rereads 0x563EC0C', 0x563EC0C, '49000034', '1F2003D5'),
        # stage A (diag/net/sigil_live.py, sigil_full_notes.md)
        ('SIGIL_A targets kind 0x26 0x11960B8', 0x11960B8, '81048052', 'C1048052'),
        ('SIGIL_A self filter 0x119610C', 0x119610C, 'F9DF40A9', 'BD676695'),
        ('SIGIL_A merge 0x1195D2C', 0x1195D2C, '68825FB8', 'F5686615'),
        ('SIGIL_A pre (shipped cave) 0x563EB80', 0x563EB80, 'B30CED16', '30C55314'),
        ('SIGIL_A frame (shipped cave) 0x563EC10', 0x563EC10, 'BC5BED96', '14C55394'),
        ('SIGIL_A cave region word 0x6B30000', 0x6B30000, '00000000', 'E8A740A9'),
        ('SIGIL_A_KEEP setter guard 0x1179788', 0x1179788, '080840B9', '6EDA6695')]
FLAG_OFF = 0x6B30FFC        # SIGIL_A per-match flag: 1 = producer already ran at UpdatePhase this match
# skill pair lists the collector 0xD45000 walks for mask 0x104411 (pairs {u32 id, u32 count}):
# bit 0 -> pgd+0x1C6C + 0..0xF0 (30 pairs) [V 0xD452D8]; other bits read more of the two 0x640 blocks
BLOCKS = [('pgd+0x1C6C block (bit 0 list = first 30 pairs)', 0x1C6C), ('pgd+0x22AC block', 0x22AC)]
EXCL = [(0x1C28, 0x1C30), (0x1C48, 0x1C50)]   # vectors {begin,end} of u32 ids the filter 0xD48160 rejects [V]


def code_state(w, off, orig, new):
    b = w.rd(w.base + off, 4)
    cur = b.hex().upper() if b else None
    return 'PATCHED' if cur == new else 'original' if cur == orig else 'other (%s)' % cur


def preset_txt(row):
    if row is None:
        return 'unreadable'
    p = PRESET.get(row)
    if not p:
        return 'row %d (not a Bloodsworn preset row)' % row
    return '%s, %s' % (p[0], ('SIGIL ON: ' + SKILL[p[1]]) if p[1] else 'No Sigil (sigil OFF)')


def sigil_pairs(w, pgd):
    """{offset: (id, count)} of sigil skill pairs in the two 0x640 blocks"""
    out = []
    for name, off in BLOCKS:
        b = w.big(pgd + off, 0x640)
        if b is None:
            out.append((name, None))
            continue
        for k in range(0, len(b) - 7, 8):
            i, c = struct.unpack_from('<iI', b, k)
            if i >= 0 and i // 10 * 10 in SKILL:
                out.append((name, (off + k, i, c, k < 0xF0)))
    return out


def vec_u32(w, a_begin, a_end, limit=64):
    b0, b1 = w.q(a_begin), w.q(a_end)
    if not b0 or not b1 or b1 < b0:
        return []
    n = min((b1 - b0) // 4, limit)
    raw = w.rd(b0, 4 * n) if n else b''
    return list(struct.unpack('<%dI' % n, raw)) if raw else []


def pgd_list(w, gdm):
    """local [GDM+0x20], [GDM+0x28], [GDM+8] and the array [GDM+0x58][0..0x27] the mediator walks [V 0xCEA260..]"""
    seen, out = set(), []
    for lab, o in (('[GDM+0x20] local', 0x20), ('[GDM+0x28]', 0x28), ('[GDM+0x8]', 0x8)):
        p = w.q(gdm + o)
        if p and p not in seen:
            seen.add(p)
            out.append((lab, p))
    inl = w.q(gdm + 0x30)   # inline array of 12 pgds, stride 0x47F0 (kind bit 1, 0xCEA10C) [V]
    if inl:
        for k in range(12):
            p = inl + 0x47F0 * k
            no = w.i(p + 0xD0)
            if no is None or no == -1:
                continue
            out.append(('[GDM+0x30][%d]%s' % (k, ' (= local)' if p == w.q(gdm + 0x20) else ''), p))
            seen.add(p)
    arr = w.q(gdm + 0x58)
    if arr:
        raw = w.rd(arr, 8 * 0x28)
        if raw:
            for k, p in enumerate(struct.unpack('<40Q', raw)):
                if p and p not in seen:
                    seen.add(p)
                    out.append(('[GDM+0x58][%d]' % k, p))
                elif p:
                    out.append(('[GDM+0x58][%d] (= above)' % k, p))
    return out


def chk(ok, text):
    print('   %-5s %s' % ({True: 'PASS', False: 'FAIL', None: 'INFO'}[ok], text))


def producer_inputs(w, gdm, pgd):
    print(' 2. producer inputs (MatchPreprocess par+0x50 == 1 -> 0x1149714 -> 0x1181D80 -> 0x1181E48 -> 0x1195E40)')
    par = w.g(PAR_G)
    step = w.d(par + 0x50) if par else None
    chk(None, 'stage step par+0x50 = %s (the producer runs once, in step 1; later changes need a new match)' % step)
    chk(None, 'MatchPreprocess wait par+0x4718 = %s (mode 6: the step body, producer included, runs on the first '
        'frame where it is > 0; set to 1 by the match-info handlers 0x115CD58 / 0x11BF208)' % (
            w.i(par + 0x4718) if par else None))
    sqm = w.g(SQM_G)
    chk(bool(sqm), 'C1 sub quest manager *(main+0x%X) = %s (0x1149710)' % (SQM_G, w.rel(sqm)))
    s28 = w.q(sqm + 0x28) if sqm else None
    chk(bool(s28), 'C2 SQM+0x28 = %s (0x1181E3C: null -> neither producer nor reader)' % w.rel(s28))
    gd = w.g(GAMEDATA_G)
    off = w.b(gd + 0xBDA) if gd else None
    role = w.b(w.base + ROLE_B)
    gate = code_state(w, 0x1181E48, '68000034', '4AF31215')
    nop = code_state(w, 0x563EB7C, '49000035', '1F2003D5')
    runs = bool(off) or (gate == 'PATCHED' and (role == 0 or nop == 'PATCHED'))
    chk(runs, 'C3 path: offline +0xBDA = %s, gate %s, role %s, guests-produce %s -> %s' % (
        off, gate, role, nop, 'PRODUCER' if runs else 'one-shot reader only'))
    obj = w.g(PRODUCER_OBJ_G)
    chk(bool(obj), 'C4 *(main+0x%X) = %s (null -> return, no record)' % (PRODUCER_OBJ_G, w.rel(obj)))
    chk(None, '   its +0xB8 = %s (row looked up by 0x15647A0; missing row -> empty record; not checkable here)' % (
        w.i(obj + 0xB8) if obj else None))
    chk(bool(pgd), 'C5 local pgd [GDM+0x20] = %s' % w.rel(pgd))
    if not pgd:
        return
    pairs = sigil_pairs(w, pgd)
    found = [p for _, p in pairs if p]
    for name, p in pairs:
        if p is None:
            chk(None, '   %s unreadable' % name)
    excl = set()
    for a, b in EXCL:
        excl.update(vec_u32(w, pgd + a, pgd + b))
    good = [p for p in found if p[2] >= 1 and p[1] // 10 * 10 not in excl]
    chk(bool(good), 'C6 sigil skill pair {id, count>=1} in the pgd skill blocks (written only by the row apply 0xCE7280)')
    for o, i, c, first30 in found:
        chk(None, '   pgd+0x%X = {%d, %d} %s%s%s' % (o, i, c, SKILL[i // 10 * 10],
                                                  '' if first30 else ' (outside the bit-0 list)',
                                                  ' EXCLUDED by pgd+0x1C28/0x1C48 lists' if i // 10 * 10 in excl else ''))
    row = w.i(pgd + 0x10C)
    if not found and PRESET.get(row, (0, None))[1]:
        chk(None, '   pgd+0x10C says SIGIL ON but no skill pair: the row was never applied (pick it in the menu)')
    rule = w.b(w.base + RULE_G)
    q = SKILL_QUEST.get(good[0][1] // 10 * 10) if good else None
    if q is not None:
        mask, ntarg, _ = QUEST_ROW[q]
        ok = rule is not None and rule <= 2 and bool(mask & ((0x40402 >> (8 * rule)) & 0xFF) & 6)
        chk(ok, 'C7 rule byte main+0x%X = %s vs quest %d mask 0x%02X' % (RULE_G, rule, q, mask))
    else:
        ntarg = 0
        chk(None, 'C7 rule byte main+0x%X = %s (no quest to test)' % (RULE_G, rule))
    kind = code_state(w, 0x11960B8, '81048052', 'C1048052')   # mov w1,#0x24 -> mov w1,#0x26 (SIGIL_TARGETS)
    cands = []
    for lab, p in pgd_list(w, gdm):
        if '(= above)' in lab:
            continue
        s40, s46, no = w.b(p + 0x40D0), w.b(p + 0x46D0), w.i(p + 0xD0)
        if lab.startswith('[GDM+0x58]'):
            ok = s40 == 4 and s46 == 0                       # kind bit 2 (stock 0x24)
        elif lab.startswith('[GDM+0x30]'):
            ok = kind == 'PATCHED' and no != -1 and s46 == 0  # kind bit 1, only with the 0x26 patch
        else:
            continue
        cands.append((lab, p, no, s40, s46, ok))
    n = sum(1 for c in cands if c[5])
    chk(n >= ntarg if ntarg else None, 'C8 targets: %d usable, quest wants %d (target kind word 0x11960B8: %s; '
        'stock 0x24 = [GDM+0x58] type-4 pgds only, 0x26 adds the [GDM+0x30] player array)' % (n, ntarg, kind))
    for lab, p, no, s40, s46, ok in cands:
        chk(None, '   %s %s no %s +0x40D0 %s +0x46D0 %s %s%s' % (lab, w.rel(p), no, s40, s46, 'target' if ok else '',
                                                           ' SELF!' if p == pgd and ok else ''))
    if not any(lab.startswith('[GDM+0x30]') for lab, *_ in cands):
        chk(None, '   [GDM+0x30] player array: no entry with a player no (peers not known to this game yet)')
    m3 = w.g(MGR3_G)
    chk(bool(m3), 'C9 *(main+0x%X) = %s (null -> no apply, no send)' % (MGR3_G, w.rel(m3)))
    own = code_state(w, 0x11963CC, '7FC11EB8', 'BFA11295')
    chk(None, 'C10 own entry id = %s' % ('pgd+0xD0 = %s (SIGIL_OWN)' % w.i(pgd + 0xD0) if own == 'PATCHED' else '0 (stock)'))


# ---------- 2b. producer / apply walk (diag/net/sigil_why_notes.md) ----------
REPO_G = 0x5B3CE68          # param repository used by 0x15647A0 / 0x1566700 / 0x1D2C9A0       [V]
REPO_GOT = 0x59DFFF8        # GOT slot of the repository used by 0x15678C0 (row 0 +0x204)      [V]
SQM_GOT = 0x59DFF30         # GOT slot the apply derefs for the SQM (assert when null, 0x1195D38) [V]
MISSION_OBJ_G = 0x5B44E88   # mission object, +0xB8 = mission row id                           [V]
T_MISSION, T_QUEST, T_SKILL, T_COMMON = 0x3F30, 0x3E10, 0x2310, 0x2118   # repo +flag / +8 table [V]
SIGIL2_FLAG = 0xC50F200     # SIGIL2_LATE flag (1 = producer ran this match)                  [V sigil2_notes]
KEEP_WORD = (0x1179788, '080840B9')   # stock `ldr w8,[x0,#8]`; anything else = a KEEP hook is live


def param_row(w, repo, toff, pid, skill=False):
    """mirror of 0x1566700 / 0x15647A0 / 0x1D2C9A0: returns (row address or None, why)"""
    if pid is None or pid < 0:
        return None, 'id %s < 0 (lookup returns no row)' % pid
    if not repo:
        return None, 'repo null'
    if not w.d(repo + toff):
        return None, 'table flag repo+0x%X = 0' % toff
    tab = w.q(repo + toff + 8)
    p70 = w.q(tab + 0x70) if tab else None
    data = w.q(p70 + 0x78) if p70 else None
    if not data:
        return None, 'table repo+0x%X unreadable' % (toff + 8)
    n, hoff = w.i(data - 0xC), w.i(data - 0x10)
    if n is None or hoff is None or n < 1:
        return None, 'empty table'
    idx_base = data + ((hoff + 0xF) & ~0xF)
    lo, hi, idx = 0, n - 1, None
    while lo <= hi:
        mid = (lo + hi) >> 1
        e = w.rd(idx_base + 8 * mid, 8)
        if not e:
            return None, 'index unreadable'
        rid, ridx = struct.unpack('<Ii', e)
        if rid == pid:
            idx = ridx
            break
        if rid < pid:
            lo = mid + 1
        else:
            hi = mid - 1
    if idx is None or idx < 0:
        return None, 'no row %d (%d rows)' % (pid, n)
    if skill and idx >= (w.h(data + 0xA) or 0):
        return None, 'row index out of range'
    t = w.b(data + 0x2D) or 0
    k = (t & 0x7F) - 2
    f2e = w.b(data + 0x2E) or 0
    if k < 0 or k > 3:
        off = 0
    elif k == 0:
        off = w.d(data + idx * 0xC + 0x34)
    elif (k == 2 and f2e & 2) or (k == 3 and t & 0x80 and f2e & 2):
        off = w.q(data + idx * 0x18 + 0x48)
    else:
        off = w.d(data + idx * 0xC + 0x44)
    if off is None:
        return None, 'row offset unreadable'
    row = data + off
    if skill and (w.h(data + 8) or 0) < 0x10:
        row -= 4
    return row, 'row %d at %s' % (pid, w.rel(row))


def table_ids(w, repo, toff, limit=12):
    tab = w.q(repo + toff + 8) if repo else None
    p70 = w.q(tab + 0x70) if tab else None
    data = w.q(p70 + 0x78) if p70 else None
    if not data:
        return None, []
    n, hoff = w.i(data - 0xC) or 0, w.i(data - 0x10) or 0
    raw = w.rd(data + ((hoff + 0xF) & ~0xF), 8 * min(n, limit)) if n > 0 else b''
    return n, [struct.unpack_from('<I', raw, 8 * k)[0] for k in range(len(raw) // 8)] if raw else []


def mediator_find(w, gdm, pid):
    """mirror of 0xCEA240 kind 0x3F, flags (pid ? 3 : 1), functor 0xCEEB78 (pgd+0xD0 == pid): first pgd found"""
    flags = 3 if pid else 1
    order = []
    loc = w.q(gdm + 0x28) if flags & 2 else None
    order.append(('[GDM+0x28]', loc) if loc else ('[GDM+0x20]', w.q(gdm + 0x20)))
    p8 = w.q(gdm + 8)
    if p8 and w.i(p8 + 0xD0) != -1:
        order.append(('[GDM+0x8]', p8))
    inl = w.q(gdm + 0x30)
    if inl:
        for k in range(12):
            p = inl + 0x47F0 * k
            if w.i(p + 0xD0) not in (None, -1):
                order.append(('[GDM+0x30][%d]' % k, p))
    arr = w.q(gdm + 0x58)
    raw = w.rd(arr, 8 * 40) if arr else None
    if raw:
        for k, p in enumerate(struct.unpack('<40Q', raw)):
            if p:
                order.append(('[GDM+0x58][%d]' % k, p))
    for lab, p in order:
        if p and w.i(p + 0xD0) == pid:
            return lab, p
    return None, None


def producer_walk(w, gdm):
    print(' 2b. PRODUCER / APPLY WALK in code order (sigil_why_notes.md; first FAIL = where it stops)')
    repo = w.g(REPO_G)
    chk(None, 'SIGIL2 flag main+0x%X = %s (1 = producer ran this match); KEEP word 0x%X = %s' % (
        SIGIL2_FLAG, w.i(w.base + SIGIL2_FLAG), KEEP_WORD[0],
        (lambda b: 'stock (no KEEP: a later -1 write is possible)' if b and b.hex().upper() == KEEP_WORD[1]
         else 'HOOKED %s (KEEP live)' % b.hex().upper() if b else 'unreadable')(w.rd(w.base + KEEP_WORD[0], 4))))
    obj = w.g(MISSION_OBJ_G)
    chk(bool(obj), 'P1 0x1195E74 mission object *(main+0x%X) = %s (null = assert)' % (MISSION_OBJ_G, w.rel(obj)))
    if not obj:
        return
    mid = w.i(obj + 0xB8)
    row, why = param_row(w, repo, T_MISSION, mid)
    n, ids = table_ids(w, repo, T_MISSION)
    chk(row is not None, 'P2 0x1195EA0 mission id obj+0xB8 = %s in table repo+0x%X: %s  -> FAIL = EMPTY RECORD' % (
        mid, T_MISSION, why))
    chk(None, '   table repo+0x%X: %s rows, first ids %s' % (T_MISSION, n, ids))
    if row is None:
        chk(None, '   (the walk goes on to show the rest; the real producer stops here)')
    pgd = w.q(gdm + 0x20)
    chk(bool(pgd), 'P3 0x1195EB4 local pgd [GDM+0x20] = %s' % w.rel(pgd))
    if not pgd:
        return
    crepo = w.q(w.g(REPO_GOT) or 0)
    crow, _ = param_row(w, crepo, T_COMMON, 0)
    nslot = w.d(crow + 0x204) if crow else None
    slots = set()
    raw = w.rd(pgd + 0x28F0, 8 * nslot) if nslot and nslot < 0x11 else None
    if raw:
        slots = set(struct.unpack('<%dQ' % nslot, raw))
    ex1, ex2 = vec_u32(w, pgd + 0x1C28, pgd + 0x1C30), vec_u32(w, pgd + 0x1C48, pgd + 0x1C50)
    b = w.big(pgd + 0x1C6C, 0xF0)
    collected = []
    for k in range(30 if b else 0):
        pid, cnt = struct.unpack_from('<iI', b, 8 * k)
        if pid < 0 or cnt < 1:
            continue
        srow, _ = param_row(w, repo, T_SKILL, pid, skill=True)
        cat = w.b(srow + 0x7D) if srow else None
        if cat == 3 and pgd + 0x1C6C + 8 * k not in slots:
            chk(False, 'P5 pair %d {%d,%d}: SkillParam+0x7D == 3 and not in the %s equip slots pgd+0x28F0 -> dropped' % (
                k, pid, cnt, nslot))
            continue
        if pid in ex1 or pid in ex2:
            chk(False, 'P5 pair %d {%d,%d}: in exclusion vector pgd+0x%s -> dropped' % (
                k, pid, cnt, '1C28' if pid in ex1 else '1C48'))
            continue
        collected.append((k, pid, cnt, srow, cat))
    chk(bool(collected), 'P5 0xD45000 bit-0 pairs collected from pgd+0x1C6C: %s (only pairs with id >= 0, count >= 1; '
        'eff id = id for count 1; other mask bits not simulated)' % (
            ', '.join('%d:{%d,%d}' % c[:3] for c in collected) or 'none'))
    decided = None
    for k, pid, cnt, srow, cat in collected:
        if not srow:
            chk(None, '   pair %d id %d: no SkillParam row -> skipped' % (k, pid))
            continue
        q = w.i(srow + 0x64)
        qrow, why = param_row(w, repo, T_QUEST, q)
        chk(None, '   pair %d id %d: SkillParam %s +0x7D %s +0x64 quest %s -> quest table repo+0x%X: %s' % (
            k, pid, w.rel(srow), cat, q, T_QUEST, why))
        if qrow:
            decided = (k, pid, q, qrow)
            break
    chk(bool(decided), 'P6 first collected skill with a quest row: %s' % (
        'pair %d id %d quest %d' % decided[:3] if decided else 'NONE -> EMPTY RECORD'))
    if not decided:
        return
    k, pid, q, qrow = decided
    rule = w.b(w.base + RULE_G)
    mask = w.b(qrow + 0x19)
    ok = rule is not None and rule <= 2 and bool((mask or 0) & ((0x40402 >> (8 * rule)) & 0xFF) & 6)
    chk(ok, 'P6 0x1195FEC rule byte main+0x%X = %s, quest row +0x19 = %s -> %s' % (
        RULE_G, rule, None if mask is None else '0x%02X' % mask, 'record built' if ok else 'x21 = 0: EMPTY RECORD'))
    chk(None, '   quest row: +0 counterpart %s, +0x50 targets %s, +0x48 passive %s' % (
        w.i(qrow), w.b(qrow + 0x50), w.i(qrow + 0x48)))
    own_patched = code_state(w, 0x11963CC, '7FC11EB8', 'BFA11295') == 'PATCHED'
    own = w.i(pgd + 0xD0) if own_patched else 0
    chk(own not in (None, -1, 0), 'P9 0x11963CC own entry id = %s (%s; -1 is skipped by the apply, 0 matches no LAN '
        'player)' % (own, 'SIGIL_OWN = pgd+0xD0 now' if own_patched else 'stock 0'))
    m3 = w.g(MGR3_G)
    chk(bool(m3), 'P10 0x11963FC *(main+0x%X) = %s (null = assert); mode +0x1268 = %s (6 = 0x88 sent); send hook '
        '0x1196404 %s' % (MGR3_G, w.rel(m3), w.i(m3 + 0x1268) if m3 else None,
                           code_state(w, 0x1196404, '0FFEFF97', 'E3A11295')))
    sqm = w.q(w.g(SQM_GOT) or 0)
    chk(bool(sqm), 'A0 0x1195D38 SQM via GOT 0x%X = %s (null = assert)' % (SQM_GOT, w.rel(sqm)))
    keys = set()
    if sqm:
        v0, v1 = w.q(sqm + 8), w.q(sqm + 0x10)
        if v0 and v1 and v1 >= v0:
            keys = {w.i(v0 + 0x20 * j) for j in range(min((v1 - v0) // 0x20, 16))}
    print('   apply 0x1195C40 per entry (own entry; targets are the other numbers this game knows):')
    ids = [own] + [w.i(p + 0xD0) for lab, p in pgd_list(w, gdm) if '(= above)' not in lab and p != pgd]
    seen = set()
    for pid in ids:
        if pid in seen or pid is None:
            continue
        seen.add(pid)
        if pid == -1:
            # sigil5_notes 1: this id comes from a pgd this game lists with no -1 (unused / not yet numbered),
            # not from a record entry; a real entry with id -1 would be skipped at 0x1195CBC
            chk(None, 'A1 0x1195CBC a pgd with no -1 is listed here (not a record entry; an entry with id -1 '
                'would be skipped)')
            continue
        lab, p = mediator_find(w, gdm, pid)
        chk(bool(p), 'A2 0x1195D20 mediator 0xCEA240 kind 0x3F id %s -> %s %s%s' % (
            pid, lab, w.rel(p), ' (= local pgd)' if p == pgd else ''))
        sh = w.q(gdm + 0x28)
        if pid and sh and sh != w.q(gdm + 0x20):
            chk(None, '   [GDM+0x28] %s replaces [GDM+0x20] in the walk (0xCEA274)' % w.rel(sh))
        chk(pid in keys, 'A3 0x11825E0 SQM entry with key %s (missing = module part silent; the pgd write still happens)'
            % pid)
        if p:
            s0, s1 = w.i(p + 0x46E0), w.i(p + 0x46E4)
            chk(s0 not in (None, -1), 'A4 0x1195D30 result pgd+0x46E0 = %s, +0x46E4 = %s (-1/-1 = ctor value 0xD134C0: '
                'never written, or cleared by the setter 0x1179770)' % (s0, s1))


# ---------- 2c. the record per entry (diag/net/sigil5_notes.md) ----------
def _sqm_modules(w):
    """{key (player no): [slot 0..2 module ptrs]} of the sub quest manager"""
    sqm = w.g(SQM_G)
    v0, v1 = (w.q(sqm + 8), w.q(sqm + 0x10)) if sqm else (None, None)
    out = {}
    if v0 and v1 and v1 >= v0:
        for k in range(min((v1 - v0) // 0x20, 16)):
            e = v0 + 0x20 * k
            out[w.i(e)] = [w.q(e + o) for o in (8, 0x10, 0x18)]
    return out


def _cond_targets(w, m):
    """(+0xC8, +0xCC) of the first class-C (target) condition near the module's holder, else None"""
    holder = (w.q(m + 0x28) or w.q(m + 0x20)) if m else None
    if not holder:
        return None
    for o in (0x10, 0x18, 0x20, 0x28):
        obj = w.q(holder + o)
        if not obj:
            continue
        raw = w.rd(obj, 0x100)
        for c in [obj] + (list(struct.unpack('<32Q', raw)) if raw and len(raw) == 0x100 else []):
            if c and not c & 7 and COND_VT.get((w.q(c) or 0) - w.base, ('',))[0] == 'C target':
                return w.i(c + 0xC8), w.i(c + 0xCC)
    return None


def record_lines(w, gdm):
    """The producer record as this game's own producer built it (only on a bearer's game: own quest from the local
    skill pairs, targets from the own module's class-C condition), each entry's player id, and the pgd the apply
    0x1195C40 resolves it to (mediator 0xCEA240 by pgd+0xD0). Then every numbered pgd: its slots and which
    entry kind can have written them. Layout [V 0x11962D0..0x11963D4]: target entry {tgt, row+0 counterpart,
    -1, -1, other target or -1} (one per target, first), own entry {own, quest, -1, t1, t2} (last)."""
    print(' 2c. RECORD per entry (sigil5_notes.md): {id, slot0 quest, slot1, t1, t2} -> pgd resolved by pgd+0xD0')
    nop_rows = _live_groups('sigil2_live.py').get('SIGIL2_NOPASSIVE') or []
    nop = code_state(w, nop_rows[-1][0], nop_rows[-1][1].upper(), nop_rows[-1][2].upper()) if nop_rows else 'n/a'
    chk(None, 'SIGIL2_NOPASSIVE hook 0x11962C8: %s (PATCHED = no target entries: targets keep -1; stock = game '
        'layout: each target gets the counterpart quest)' % nop)
    pgd = w.q(gdm + 0x20)
    own = w.i(pgd + 0xD0) if pgd else None
    pairs = [p for _, p in sigil_pairs(w, pgd) if p and p[3] and p[2] >= 1] if pgd else []
    q = SKILL_QUEST.get(pairs[0][1] // 10 * 10) if pairs else None
    mods = _sqm_modules(w)
    entries = []
    if q is None:
        chk(None, '   local player %s has no sigil pair: this game builds no record (it only applies received ones)'
            % own)
    else:
        tg = _cond_targets(w, (mods.get(own) or [None])[0]) or (-1, -1)
        cp = QUEST_ROW[q][2]
        live_t = [t for t in tg if t not in (None, -1)]
        if nop != 'PATCHED':
            for k, t in enumerate(live_t):
                other = [x for x in live_t if x != t]
                entries.append(('target', t, cp, -1, -1, other[0] if other else -1))
        entries.append(('own', own, q, -1, tg[0], tg[1]))
        chk(None, '   local bearer %s quest %s, targets from its class-C condition %s (counterpart row+0 = %s)' % (
            own, q, tg, cp))
    for k, (kind, pid, s0, s1, t1, t2) in enumerate(entries):
        lab, p = mediator_find(w, gdm, pid) if pid not in (None, -1) else (None, None)
        got = w.i(p + 0x46E0) if p else None
        chk(got == s0 if p else False, 'entry %d (%s) id %s quest %s slot1 %s t %s/%s -> %s %s%s: +0x46E0 = %s' % (
            k, kind, pid, s0, s1, t1, t2, lab or 'NO PGD (skipped at 0x1195D20; late copy?)', w.rel(p),
            ' (= local)' if p and p == pgd else '', got))
    for lab, p in pgd_list(w, gdm):
        if '(= above)' in lab:
            continue
        no = w.i(p + 0xD0)
        if no in (None, -1):
            chk(None, '   %s %s no -1: unused / unnumbered pgd, no entry can reach it' % (lab, w.rel(p)))
            continue
        rl, rp = mediator_find(w, gdm, no)
        s0 = w.i(p + 0x46E0)
        src = ('none (-1)' if s0 == -1 else 'own entry' if q is not None and no == own and s0 == q else
               'own entry or counterpart (%s %s)' % (s0, QUEST.get(s0, '')))
        chk(None, '   %s %s no %s resolves to %s%s | +0x46E0 %s +0x46E4 %s | written by: %s' % (
            lab, w.rel(p), no, rl, '' if rp == p else ' = ANOTHER pgd (this copy never gets entries)',
            s0, w.i(p + 0x46E4), src))


def game(w):
    gdm = w.g(PGD_G)
    print('%s: GDM *(main+0x%X) = %s' % (w.who, PGD_G, w.rel(gdm)))
    if not gdm:
        w.null('GDM')
        return
    pgd = w.q(gdm + 0x20)
    print(' 1. Bloodsworn / sigil choice (local pgd %s)' % w.rel(pgd))
    if pgd:
        print('      +0x10C chosen row       = %s -> %s' % (w.i(pgd + 0x10C), preset_txt(w.i(pgd + 0x10C))))
        print('      +0xEC8 last applied row = %s -> %s' % (w.i(pgd + 0xEC8), preset_txt(w.i(pgd + 0xEC8))))
    producer_inputs(w, gdm, pgd)
    producer_walk(w, gdm)
    record_lines(w, gdm)
    print(' 3. sigil patches in code')
    for name, off, orig, new in CODE:
        print('   %-36s %s' % (name, code_state(w, off, orig, new)))
    print('   SIGIL_A flag main+0x%X = %s (1 = produced this match; reset at MatchPreprocess)' % (
        FLAG_OFF, w.i(w.base + FLAG_OFF)))
    sigil3_words(w)
    print(' 4. RESULT per PlayerGameData: +0x46E0 quest / +0x46E4 (-1 = ctor value: no entry applied)')
    for lab, p in pgd_list(w, gdm):
        if '(= above)' in lab:
            continue
        q0 = w.i(p + 0x46E0)
        print('   %-20s %s no %s row %s +0x40D0 %s | +0x46E0 = %s %s | +0x46E4 = %s' % (
            lab, w.rel(p), w.i(p + 0xD0), w.i(p + 0x10C), w.b(p + 0x40D0), q0, QUEST.get(q0, ''), w.i(p + 0x46E4)))
    for k, e in enumerate(w.players(12)):
        data = w.q(e[0] + 0x20)
        cp = w.q(data + 0x1D0) if data else None
        print('   player chr [%d] %s -> pgd %s (no %s)' % (k, w.rel(e[0]), w.rel(cp), w.i(cp + 0xD0) if cp else None))
    print(' 5. sub quest manager *(main+0x%X) (0x20 entries: key, 3 module ptrs; module+0x4C = quest) [I layout]' % SQM_G)
    sqm = w.g(SQM_G)
    if not sqm:
        print('   null')
        return
    v0, v1 = w.q(sqm + 8), w.q(sqm + 0x10)
    if not v0 or not v1 or v1 < v0:
        print('   %s: vector [+8, +0x10) = %s..%s' % (w.rel(sqm), w.rel(v0), w.rel(v1)))
        return
    n = (v1 - v0) // 0x20
    print('   %s: %d entries, +0x28 = %s' % (w.rel(sqm), n, w.rel(w.q(sqm + 0x28))))
    for k in range(min(n, 16)):
        e = v0 + 0x20 * k
        mods = [w.q(e + o) for o in (8, 0x10, 0x18)]
        qs = [w.i(m + 0x4C) if m else None for m in mods]
        print('   [%d] key %s | modules %s | quests %s' % (
            k, w.i(e), ' '.join(w.rel(m) for m in mods), ' '.join(str(q) for q in qs)))
    sqm_coverage(w, gdm, v0, n)
    summary(w, gdm, sqm, v0, n)
    eye_overview(w, gdm, v0, n)
    eye_ident(w)


def sqm_coverage(w, gdm, v0, n):
    """5b (diag/net/sigil9_notes.md 3): SQM entries are made ONLY in MatchPreprocess 0x1181D80 (enumerator 0xCE9F40
    kind 0x27 -> functor 0x11889E0: local pgd, [GDM+0x30] copies with +0xD0 != -1 and +0x46D0 == 0, type-4 bots;
    skipped when team byte pgd+0x104 > 0xB; key = pgd+0xD0 at that moment) and removed only by the SQM dtor
    0x1180060 [V]. A missing key is final for the match: records for that player write only his pgd slots
    (0x11825E0 returns at 0x11826E4) and a bearer whose target has no module pairs with nobody (module+0x79 = 1)."""
    keys = {}
    for k in range(min(n, 16)):
        e = v0 + 0x20 * k
        keys[w.i(e)] = [w.q(e + o) for o in (8, 0x10, 0x18)]
    par = w.g(PAR_G)
    print(' 5b. SQM ENTRY COVERAGE (made only at MatchPreprocess, never later; sigil9_notes 3) | match step '
          'par+0x50 = %s' % (w.d(par + 0x50) if par else None))
    numbered = set()
    for lab, p in pgd_list(w, gdm):
        if '(= above)' in lab:
            continue
        no = w.i(p + 0xD0)
        if no in (None, -1):
            continue
        numbered.add(no)
        mods = keys.get(no)
        m79 = [w.b(m + 0x79) if m else None for m in mods] if mods else []
        print('   player %s %-20s key %s | team +0x104 %s +0x46D0 %s +0x40D0 %s | module+0x79 per slot %s%s' % (
            no, lab, 'PRESENT' if mods else 'MISSING', w.b(p + 0x104), w.b(p + 0x46D0), w.b(p + 0x40D0),
            m79 or '-',
            '' if mods else ' -> FINAL for this match on this game: no module for him (not listed / numbered / '
            'team byte 0xFF at MatchPreprocess, or joined later); a sigil injected now cannot pair or pay'))
        if mods and any(m79):
            print('      module+0x79 = 1 on a slot: that listener gave up pairing (no open partner on its first frame); '
                  'only a rebuild of the module (0x117A500, a new record for this player) clears it')
    for key in keys:
        if key not in numbered:
            print('   SQM key %s: no numbered pgd has this number now (stale key: the player was renumbered or left '
                  'after MatchPreprocess; his entries go nowhere)' % key)
    # SIGIL13_JOIN (diag/net/sigil13_notes.md): per-frame catch-up of late SQM entries before the flush 0x1180440
    st = w.rd(w.base + 0xC50F300, 8)
    print('   SIGIL13_JOIN hook 0x182F2E8 %s, tramp 0x563EFF8 %s | state main+0xC50F300: re-arm frames left %s, '
          'late entries made %s' % (
              code_state(w, 0x182F2E8, '5644E597', '443FF894'), code_state(w, 0x563EFF8, '00000000', '30760390'),
              int.from_bytes(st[0:4], 'little') if st else None,
              int.from_bytes(st[4:8], 'little') if st else None))


def module_txt(w, m):
    """module fields [V writers in 0x11792E0 / 0x1179770, I meaning]: +0x4C quest, +0x18 state (event 0, 1..3),
    +0x38 step bit mask (event 1), +0x7C value < 100 (event 2: progress), +0x48 u16 (0x101 after an event)"""
    if not m:
        return '-'
    ev = w.d(m + 0x48)
    return 'q %s st %s steps 0x%X prog %s ev 0x%X' % (
        w.i(m + 0x4C), w.i(m + 0x18), w.q(m + 0x38) or 0, w.i(m + 0x7C), (ev or 0) & 0xFFFF)


def summary(w, gdm, sqm, v0, n):
    """6. one line per player: entry (slots 0/1/2), target, progress, completion, award"""
    print(' 6. PER PLAYER (entry = pgd slots +0x46E0/+0x46E4/+0x46E8; module = SQM entry by key = player no)')
    keyed = {}
    for k in range(min(n, 16)):
        e = v0 + 0x20 * k
        keyed[w.i(e)] = [w.q(e + o) for o in (8, 0x10, 0x18)]
    local = w.q(gdm + 0x20)
    for lab, p in pgd_list(w, gdm):
        if '(= above)' in lab:
            continue
        no = w.i(p + 0xD0)
        if no is None or no == -1:
            continue
        s = [w.i(p + 0x46E0 + 4 * k) for k in range(3)]
        mods = keyed.get(no, [None, None, None])
        print('   player %s%s: entry %s | %s' % (no, ' (LOCAL)' if p == local else '',
                                                 ' / '.join('%s %s' % (q, QUEST.get(q, '')) for q in s),
                                                 'NO SQM ENTRY for this key (module apply returns silently)'
                                                 if no not in keyed else ''))
        for k, m in enumerate(mods):
            if m:
                print('      slot %d module %s: %s' % (k, w.rel(m), module_txt(w, m)))
                flow(w, m)
                friend(w, gdm, m, no)
                eye(w, m, no)
                conditions(w, m, no)
        wp = w.q(p + 0x46D8)
        print('      award: wp pgd+0x46D8 = %s, wp+0x11 = %s (%s), Virtue base s16 pgd+0x42C8 = %s' % (
            w.rel(wp), w.b(wp + 0x11) if wp else None,
            'awards land HERE' if wp and w.b(wp + 0x11) == 0 else 'award skipped here (0x1194F70)' if wp else 'no wp',
            s16(w.h(p + 0x42C8))))
    print(' 8. award counters: sub quest reward pushes into counter 150005 (reward types 0..5, 12, 13), 150010 '
          '(6..11) or 150000 (14) of pgd+0x46D8 via 0xF72F90 (0x1194FB0); only where wp+0x11 == 0 [V]')


# condition classes built by the factory 0x118915C (vtable offsets from main) [V vtables, I names]
COND_VT = {0x56F8DD8: ('A', 1), 0x56F8E88: ('B quest-match', 2), 0x56F8F40: ('C target', 2),
           0x56F90A8: ('D', 0), 0x56F9158: ('helper', 0), 0x56F9260: ('E', 0), 0x56F9310: ('F', 0),
           0x56F9378: ('G', 1), 0x56F93E0: ('H', 1)}
AUTH_WORD = {'B quest-match': 0x1198738, 'C target': 0x1198744}   # mov w0,#2 (40008052) -> #1 (20008052) = C2


def s16(v):
    return None if v is None else v - 0x10000 if v & 0x8000 else v


def conditions(w, m, own_no):
    """7. condition objects reachable from a module: holder module+0x28 (+0x10/+0x18/+0x20/+0x28 objects,
    0x117A84C) and one level of pointers inside each (root+0x90 condition, +0xA8 helper, 0x11895F4) [V stores,
    I that this reaches every condition]. Prints class, authority, list count, dirty, pending, targets."""
    print('         built +0x30 = %s, started +0x80 = %s' % (w.b(m + 0x30), w.b(m + 0x80)))
    # sigil3_notes 2: the apply builds the holder at +0x28; 0x11771A0 moves it to +0x20 (active) and clears +0x28
    holder = w.q(m + 0x28) or w.q(m + 0x20)
    if not holder:
        print('         holder module+0x28 / +0x20 = null (module never set by the apply 0x11825E0)')
        return
    objs = [w.q(holder + o) for o in (0x10, 0x18, 0x20, 0x28)]
    print('         holder %s: objects %s' % (w.rel(holder), ' '.join(w.rel(o) for o in objs)))
    seen, found = set(), []
    for o in objs:
        if not o:
            continue
        raw = w.rd(o, 0x100)
        cand = [o] + (list(struct.unpack('<32Q', raw)) if raw and len(raw) == 0x100 else [])
        for c in cand:
            if not c or c in seen or c & 7:
                continue
            vt = w.q(c)
            if not vt:
                continue
            hit = COND_VT.get(vt - w.base)      # object +0 = main + (GOT value + 0x10), as the keys above
            if hit:
                seen.add(c)
                found.append((c, hit))
    if not found:
        print('         no condition object found near the holder')
    for c, (name, auth) in found:
        # "auth N" = the class's STOCK authority (COND_VT table), not the live word; see "authority word"
        line = '         cond %-14s %s auth %d | handles %s dirty %s pending %s' % (
            name, w.rel(c), auth, w.q(c + 0x58), w.b(c + 0x60), w.b(c + 0xB8))
        if name in AUTH_WORD:
            cur = w.rd(w.base + AUTH_WORD[name], 4)
            line += ' | authority word %s' % ('PATCHED (1)' if cur == bytes.fromhex('20008052') else
                                              'stock (2: evaluated offline only)' if cur == bytes.fromhex('40008052')
                                              else (cur.hex() if cur else None))
            t1, t2 = w.i(c + 0xC8), w.i(c + 0xCC)
            if name.startswith('B'):
                # class B [V factory 0x118A4EC, match 0x11979C0]: +0xC8 = the module's OWN player (only used to skip
                # its alliance partner when rule byte == 2), +0xCC = the quest the partner's slot must hold
                line += ' | +0xC8 owner %s%s +0xCC wants quest %s | need +0xD0 %s done +0xD4 %s' % (
                    t1, '' if t1 == own_no else ' (NOT the module player!)', t2, w.i(c + 0xD0), w.b(c + 0xD4))
            else:
                line += ' | +0xC8 %s +0xCC %s%s' % (t1, t2, ' SELF!' if own_no in (t1, t2) and own_no != -1 else '')
        print(line)
        if name in AUTH_WORD:
            listen_lines(w, m, c, holder)
            pair_line(w, m, c, name)


def _chr_by_handle(w):
    """{chr handle (chrdata+0x78 u16): (player no, pgd team byte +0x104)} for the WCM player list"""
    out = {}
    for e in w.players(12):
        data = w.q(e[0] + 0x20)
        if not data:
            continue
        hd, pg = w.h(data + 0x78), w.q(data + 0x1D0)
        out[hd] = (w.i(pg + 0xD0) if pg else None, w.b(pg + 0x104) if pg else None)
    return out


def listen_lines(w, m, c, holder):
    """sigil6_notes.md: the kill path. Target pairing (0x1180440, every frame) only sees conditions whose
    participants root (holder+0x18) +0xA0 = cond+0xC0 (wired offline only; SIGIL3_LISTEN); the add 0x1197C80 /
    0x11982E0 puts the partner's chr handle into cond+0x10 (u32: handle | slot<<24 | 0x10000, count +0x58);
    unpaired -> module+0x79 = 1 for good. Kill: 0x175EBE0 (killer local) -> 0x11822E0 killer's modules ->
    0x117B5B0: victim handle in that list (0x119B2A0) AND victim team bit in module+0x38 (0x117B83C, set by the
    step event 1) -> state 1 (0x118D094), module+0x50 += 1 if module chr local, reward type 1 (0x117AF0C)."""
    root = w.q(holder + 0x18)
    lst = w.q(root + 0xA0) if root else None
    m79 = w.b(m + 0x79)
    st = ('WIRED (pairing sees it)' if lst == c + 0xC0 else
          'NULL: no target pairing in LAN (SIGIL3_LISTEN not live when the module was built)' if not lst else
          'OTHER object (not this cond)')
    print('         listen: root %s +0xA0 %s %s | root+0xB0 %s | module+0x79 %s%s | kills module+0x50 %s' % (
        w.rel(root), w.rel(lst), st, w.b(root + 0xB0) if root else None, m79,
        ' (pairing gave up: no partner on the first frame)' if m79 else '', w.i(m + 0x50)))
    n = w.q(c + 0x58) or 0
    hmap = _chr_by_handle(w)
    mask = w.q(m + 0x38) or 0
    # sigil6_notes 9: module+0x38 is ORed only by event 1; for players nothing raises it in LAN except SIGIL3_STEP
    # (hook 0x117B770 -> 0x1179C40(module, 0) at the first kill check, sent by the owner game only)
    hook = w.rd(w.base + 0x117B770, 4)
    hk = 'stock (no step event for players in LAN)' if hook == bytes.fromhex('33000094') else \
        'HOOKED (SIGIL3_STEP)' if hook == bytes.fromhex('E00D1395') else \
        'HOOKED (SIGIL3_STEP_T)' if hook == bytes.fromhex('EF0D1395') else (hook.hex() if hook else None)
    wr = w.q(holder + 0x28)
    print('         step: team mask module+0x38 = 0x%X | done +0xD4 %s = pairing found its partner (not a kill) | '
          'kill hook 0x117B770 %s | sender gate writer+0xA8 %s +0xA9 %s (1/0 = this game sends event 1)' % (
              mask & 0xFFF, w.b(c + 0xD4), hk, w.b(wr + 0xA8) if wr else None, w.b(wr + 0xA9) if wr else None))
    for k in range(min(n, 16)):
        hd = (w.d(c + 0x10 + 4 * k) or 0) & 0xFFFF
        no, team = hmap.get(hd, (None, None))
        bit = team is not None and team <= 0xB and (mask >> team) & 1
        print('         target %d: handle 0x%X -> player %s team %s | module+0x38 bit %s -> a kill %s' % (
            k, hd, no if no is not None else '? (no chr with that handle)', team, 'SET' if bit else 'missing',
            'COUNTS (when the killer is local here)' if bit else
            'is refused at 0x117B83C (step event 1 with this team not seen yet)'))
    if not n:
        print('         target list EMPTY: a kill finds no victim at 0x119B2A0 (nothing counts)')


# ---------------------------------------------------------------- SIGIL3_PAIR (diag/net/sigil8_notes.md)
PAIR_Q = (10, 30, 240, 250)      # cond+0xCC values the match wrapper filters (sigil3_gen.py PAIR_Q)
PAIR_TAB_DEFAULT = 0xC50F280     # registry row sigil3_gen/SIGIL3_PAIR_TAB (read from cave_registry.md when present)
PAIR_MATCH_SITE = 0x1197C70      # class-B listener match thunk tail: stock `b 0x11979c0` = 54FFFF17


def _pair_tab_addr():
    import os
    import re
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'net', 'cave_registry.md')
    try:
        for ln in open(p, encoding='utf-8', errors='ignore'):
            m = re.match(r'\|\s*sigil3_gen\s*\|\s*SIGIL3_PAIR_TAB\s*\|\s*0x([0-9A-Fa-f]+)', ln)
            if m:
                return int(m.group(1), 16)
    except OSError:
        pass
    return PAIR_TAB_DEFAULT


def pair_rows(w):
    """SIGIL3_PAIR table: [(row, hunter, t1, t2)] of the valid rows; None if unreadable"""
    raw = w.rd(w.base + _pair_tab_addr(), 0x80)
    if not raw or len(raw) != 0x80:
        return None
    out = []
    for k in range(8):
        v, h, t1, t2 = struct.unpack_from('<4i', raw, 16 * k)
        if v:
            out.append((k, h, t1, t2))
    return out


def pair_line(w, m, c, name):
    """review10 S2: one line per B/C condition: designated partner(s) from the SIGIL3_PAIR table (my row's t1/t2, and
    every hunter whose row names me) vs the players whose handles pairing put into the list -> MATCH / MISMATCH."""
    me = w.i(c + 0xC8) if name.startswith('B') else None
    q = w.i(c + 0xCC)
    hook = w.rd(w.base + PAIR_MATCH_SITE, 4)
    hk = 'stock' if hook == bytes.fromhex('54FFFF17') else 'HOOKED' if hook else 'unreadable'
    rows = pair_rows(w)
    n = w.q(c + 0x58) or 0
    hmap = _chr_by_handle(w)
    paired = []
    for k in range(min(n, 16)):
        paired.append(hmap.get((w.d(c + 0x10 + 4 * k) or 0) & 0xFFFF, (None, None))[0])
    head = '         pair: match hook 0x%X %s | table %s' % (
        PAIR_MATCH_SITE, hk, 'unreadable' if rows is None else
        ' '.join('[%d] %s->%s/%s' % r for r in rows) or 'EMPTY')
    if not name.startswith('B'):
        print(head + ' | class C (slot-1 module, explicit record targets +0xC8 %s +0xCC %s): not filtered' % (
            w.i(c + 0xC8), q))
        return
    if q not in PAIR_Q:
        print(head + ' | wants quest %s: not a target-pairing quest, stock pairing' % q)
        return
    rows = rows or []
    des = sorted({t for _, h, t1, t2 in rows if h == me for t in (t1, t2) if t != -1} |
                 {h for _, h, t1, t2 in rows if me in (t1, t2)})
    known = bool(des) or any(me in (h, t1, t2) for _, h, t1, t2 in rows)
    if not des:
        verdict = 'no designation for %s (%s)' % (me, 'listed without a partner: pairing refused' if known else
                                                  'not in the table: stock pairing')
    elif not paired:
        verdict = 'NONE (designated %s, list empty%s)' % (
            des, '; module+0x79 = 1: pairing gave up' if w.b(m + 0x79) else '')
    elif all(p in des for p in paired):
        verdict = 'MATCH'
    else:
        verdict = 'MISMATCH'
    print(head + ' | owner %s designated %s paired %s -> %s' % (me, des or '-', paired or '-', verdict))


# ---------------------------------------------------------------- section 9: sigil3 (diag/net/sigil3_notes.md)
def _live_groups(fn):
    """groups of a diag/net/*_live.py (read as data, nothing applied): {name: [(off, orig, new, code)]}"""
    import importlib.util
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'net', fn)
    if not os.path.exists(p):
        return {}
    spec = importlib.util.spec_from_file_location(fn[:-3], p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {k: v for k, v in vars(mod).items() if k.isupper() and isinstance(v, list) and
            all(isinstance(r, tuple) and len(r) == 4 for r in v)}


S3_FILES = (('sigil3_live.py', ('SIGIL3_P2', 'SIGIL3_LISTEN', 'SIGIL3_STEP', 'SIGIL3_STEP_T', 'SIGIL3_ACTIVATE',
                                'SIGIL3_PROGRESS', 'SIGIL3_COMPLETE', 'SIGIL3_STATE', 'SIGIL3_PAIR',
                                'SIGIL3_FRIEND', 'SIGIL3_HERETIC_RECV', 'SIGIL3_HERETIC_ASSIGN',
                                'SIGIL3_HERETIC_SELECT')),
            ('sigil_nc_live.py', ('SIGIL_NC_TARGET', 'SIGIL_NC_EVAL', 'SIGIL_NC_REPORT', 'SIGIL_NC_PHASE')))
WHITELIST_LR = (0x1179AB0, 0x117A17C)   # perfume gives that 0xCF8F74 must let through (W1, sigil3_notes 4)


def sigil3_words(w):
    print(' 9. sigil3 / sigil_nc words (stock / PATCHED / other); first group not PATCHED = next to test')
    for fn, names in S3_FILES:
        gr = _live_groups(fn)
        for g in names:
            rows = gr.get(g)
            if rows is None:
                print('   %-20s (not in %s)' % (g, fn))
                continue
            st = [code_state(w, off, o.upper(), n.upper()) for off, o, n, c in rows]
            print('   %-20s %s' % (g, ' '.join('%X=%s' % (r[0], s) for r, s in zip(rows, st)) or '(no word)'))
    nr, s3 = (_live_groups('sigil_nc_live.py').get('SIGIL_NC_REPORT') or [None])[0], \
        (_live_groups('sigil3_live.py').get('SIGIL3_PROGRESS') or [None])[0]
    if nr and s3 and code_state(w, nr[0], nr[1], nr[2]) == 'PATCHED' and code_state(w, s3[0], s3[1], s3[2]) == 'PATCHED':
        print('   WARNING: SIGIL_NC_REPORT and SIGIL3_PROGRESS both live (report runs on every game)')
    cur = w.rd(w.base + 0xCF8F74, 4)
    print('   item gate 0xCF8F74 = %s (stock 88030034 = LAN refuses every sigil give; whitelist must pass LR %s '
          'for the local player only)' % (cur.hex().upper() if cur else None, ' / '.join('%X' % a for a in WHITELIST_LR)))


def flow(w, m):
    """per module: where the sigil flow stops (sigil3_notes 2). Layout [V stores]: +0x28 built holder, +0x20 active
    holder (0x117725C), +0x30 built, +0x78 enabled, +0x80 started, +0x18 state (event 0: 1..3, one-shot), +0x38
    team bit mask (event 1), +0x7C progress (event 3). Holder: +0x10 logic, +0x18 participants, +0x20 reward set,
    +0x28 writer {+0x98 server mask, +0xA0 client mask (bit n = event n may be sent by a client), +0xA8 = this
    game owns the module player's chr (0x1178A10), +0xA9}. Reward set: +0x90 n, {u32 id, i32 count} at +0x38."""
    built, act = w.q(m + 0x28), w.q(m + 0x20)
    st = w.i(m + 0x18)
    print('         flow: built holder %s active %s | +0x30 %s +0x78 %s +0x80 %s | state %s mask 0x%X prog %s' % (
        w.rel(built), w.rel(act), w.b(m + 0x30), w.b(m + 0x78), w.b(m + 0x80), st, w.q(m + 0x38) or 0,
        w.i(m + 0x7C)))
    h = act or built
    if not h:
        print('         STOP: no holder (apply 0x11825E0 never ran for this key, or quest -1)')
        return
    if not act:
        print('         STOP: holder built but not active (0x11771A0 has not run: no 0x8B flush / EndPhase yet)')
    wr, rs = w.q(h + 0x28), w.q(h + 0x20)
    if wr:
        sm, cm, own, a9 = w.q(wr + 0x98), w.q(wr + 0xA0), w.b(wr + 0xA8), w.b(wr + 0xA9)
        print('         writer %s: server mask 0x%X client mask 0x%X | owned here (+0xA8) %s +0xA9 %s%s' % (
            w.rel(wr), sm or 0, cm or 0, own, a9,
            ' (state needs SIGIL3_STATE)' if cm is not None and not cm & 1 else ''))
    else:
        print('         writer: null')
    if rs:
        n = w.q(rs + 0x90) or 0
        pairs = [(w.i(rs + 0x38 + 8 * k), w.i(rs + 0x3C + 8 * k)) for k in range(min(n, 10))]
        print('         rewards %s: %d ids %s' % (w.rel(rs), n, ' '.join('%s x%s' % p for p in pairs) or '-'))


# ---------------------------------------------------------------- Old Friend / alliance (diag/net/sigil10_notes.md)
VT_FRIEND = 0x56F8A28        # Old Friend logic (quest 30/40, type 5, GOT 0x59E3490 + 0x10)             [V]
VT_LOVE = (0x56F79C8, 0x56F7B38, 0x56F7CA8)   # Love Ephemeral logics (240/250); not alliance-driven    [V]
VT_COND_B = 0x56F8E88        # class-B quest-match condition                                             [V]
AM_G = 0x5B3CDD0             # alliance manager: deque map +0x10/+0x18, start +0x30, count +0x38, 0x20 entries
FRIEND_SITE = (0x117AD18, '26000094')   # stock `bl 0x117adb0` in the alliance hook 0x117ABE4; SIGIL3_FRIEND hooks it


def alliances(w):
    """[(a, b)] player numbers of the alliance deque (entry +0 / +4; 128 entries per 0x1000 block) [V 0x11979C0]"""
    am = w.g(AM_G)
    if not am:
        return None
    mp, start, cnt = w.q(am + 0x10), w.q(am + 0x30) or 0, w.q(am + 0x38) or 0
    out = []
    for i in range(min(cnt, 16)):
        k = start + i
        blk = w.q(mp + 8 * (k >> 7)) if mp else None
        if not blk:
            break
        e = blk + (k & 0x7F) * 0x20
        out.append((w.i(e), w.i(e + 4)))
    return out


def friend(w, gdm, m, own_no):
    """sigil10: where the Old Friend chain stops. Alliance -> 0x10AB800 -> 0x1182880 -> 0x117ABE4(module, ally) ->
    0x117AD18 0x117ADB0: ally team bit not in module+0x38 -> ally chr handle in the class-B list (cond +0x90,
    0x1199D00, entry +2 != 0, +3 != 0xFF) -> writer +0xA8 1 / +0xA9 0 -> step event 1 (mask bit). The same list is
    what the completion (vt+0x68 -> vt+0x138) and the Virtue (row 301 type 13 at a struggle end, 0x117B300) read."""
    holder = w.q(m + 0x20) or w.q(m + 0x28)
    logic = w.q(holder + 0x10) if holder else None
    vt = (w.q(logic) - w.base) if logic and w.q(logic) else None
    if vt in VT_LOVE:
        love(w, m, own_no, holder, logic, vt)
        return
    if vt != VT_FRIEND:
        return
    root = w.q(holder + 0x18)
    c = w.q(root + 0x90) if root else None
    cvt = (w.q(c) - w.base) if c and w.q(c) else None
    n = (w.q(c + 0x58) or 0) if c else 0
    hmap = _chr_by_handle(w)
    ents = []
    for k in range(min(n, 16)):
        e = w.d(c + 0x10 + 4 * k) or 0
        ents.append((e & 0xFFFF, (e >> 16) & 0xFF, (e >> 24) & 0xFF, hmap.get(e & 0xFFFF, (None, None))))
    want = w.i(c + 0xCC) if c else None
    site = w.rd(w.base + FRIEND_SITE[0], 4)
    hk = ('stock (no late pairing)' if site and site.hex().upper() == FRIEND_SITE[1] else
          'HOOKED (SIGIL3_FRIEND)' if site else 'unreadable')
    comp = w.rd(w.base + 0x117AC08, 4)
    print('         friend: Old Friend logic | COMPLETE 0x117AC08 %s | hook 0x117AD18 %s | cond +0x90 %s %s wants %s '
          '+0xC8 %s | list %d: %s | done +0xD4 %s +0xB8 %s module+0x79 %s' % (
              'nop (alliance hook runs)' if comp == bytes.fromhex('1F2003D5') else
              'stock (alliance hook returns in LAN)' if comp == bytes.fromhex('680B0034') else comp,
              hk, w.rel(c), 'class B' if cvt == VT_COND_B else 'NOT class B (0x%X)' % (cvt or 0), want,
              w.i(c + 0xC8) if c else None, n,
              ' '.join('0x%X->p%s(+2 %d +3 %d)' % (h, p[0], f2, f3) for h, f2, f3, p in ents) or 'EMPTY',
              w.b(c + 0xD4) if c else None, w.b(c + 0xB8) if c else None, w.b(m + 0x79)))
    # who holds the wanted quest in slot 0 (stock pairing rule; the record's target got it from the apply)
    cand = []
    for lab, p in pgd_list(w, gdm):
        if '(= above)' in lab:
            continue
        no = w.i(p + 0xD0)
        if no not in (None, -1, own_no) and w.i(p + 0x46E0) == want:
            cand.append(no)
    al = alliances(w)
    allies = sorted({b if a == own_no else a for a, b in (al or []) if own_no in (a, b)})
    wr = w.q(holder + 0x28) if holder else None
    own, a9 = (w.b(wr + 0xA8), w.b(wr + 0xA9)) if wr else (None, None)
    mask = w.q(m + 0x38) or 0
    team = {p[0]: p[1] for p in hmap.values()}
    listed = {p[0] for h, f2, f3, p in ents if f2 and f3 != 0xFF}
    rule = w.b(w.base + RULE_G)
    print('         friend: holders of quest %s in slot 0 (designated by the record): %s | alliance deque %s -> allied '
          'with %s | writer +0xA8 %s +0xA9 %s | mask 0x%X | rule byte %s%s' % (
              want, cand or '-', 'unreadable' if al is None else al or 'EMPTY', allies or '-', own, a9, mask & 0xFFF,
              rule, ' (Bloodbound: stock match refuses the current ally -> no late pairing, stock)' if rule == 2
              else ''))
    if not allies:
        print('         friend: WAIT: no alliance for player %s yet (the step comes at the alliance; Virtue only from '
              'row 301: 3 per struggle won together)' % own_no)
        return
    for a in allies:
        t = team.get(a)
        bit = t is not None and t <= 0xB and (mask >> t) & 1
        if bit:
            v = 'STEP DONE (team %s bit set: event 1 seen here)' % t
        elif a in listed:
            v = ('listed and owner here, mask still 0: the hook did not run here after the list was filled '
                 '(alliance applied before pairing, or 0x10AB800 not reached)' if own == 1 and a9 == 0 else
                 'listed; this game is not the owner: waits for the owner\'s event 1 (0x8B)')
        elif n:
            v = 'STOP 0x1199D00: list holds someone else -> ally %s is NOT the designated friend (nothing due)' % a
        elif a in cand and rule == 2:
            v = ('STOP 0x1199D00: list EMPTY, ally %s holds quest %s but rule byte 2 (Bloodbound): the stock match '
                 '0x1197C6C refuses the current ally, so SIGIL3_FRIEND stays stock (correct, review13 B1)' % (a, want))
        elif a in cand:
            v = ('STOP 0x1199D00: class-B list EMPTY (pairing never paired); ally %s is the designated holder -> '
                 'SIGIL3_FRIEND pairs at the next alliance (%s; if HOOKED and the alliance already formed: '
                 'either the pre-run20 cave (needed the ally\'s SQM key, MISSING in 5b -> stock) or the stock '
                 'match 0x1197C6C refused, e.g. SIGIL3_PAIR says another target)' % (a, hk))
        else:
            v = 'STOP: ally %s does not hold quest %s (not the Once-bonded)' % (a, want)
        print('         friend: ally %s team %s -> %s' % (a, t, v))


# ---------------------------------------------------------------- Love Ephemeral (diag/net/sigil14_notes.md)
LOVE_ACTIVE, LOVE_PASSIVE = 0x56F7B38, 0x56F7CA8   # 240 bearer / 250 Long-lost Love logic vtables           [V]
LOVE_RADIUS = 20.0       # SubQuestTypeParam row 0 +0x34 (getter 0x156686C, repo +0x3EF0), squared 3D test   [V data]
FINAL_G = 0x5B3CDF8      # completion 0x118DA54 needs *(main+0x5B3CDF8)+0xC0 bit 4 [V code, I "final phase"]
FOCUS_G = 0x5B82490      # active vt+0x120 0x118E0CC: [[*FOCUS_G+0x28]+0xA8]+0xA4 == partner chr+8 [V code, I name]


def _chr_flags(w, chr_):
    """[[chr+0x2470]+0]: +0x143 bit 3 (bearer: 'accepted', read by active vt+0x20 0x118DDF4) and +0x144 bit 2
    (partner: 'offering flowers', read by passive vt+0x20 0x118E3A8) [V reads, I names]"""
    st = w.q(w.q(chr_ + 0x2470) or 0) if chr_ else None
    if not st:
        return None, None
    return (w.b(st + 0x143) or 0) >> 3 & 1, (w.b(st + 0x144) or 0) >> 2 & 1


def _chr_pos(w, chr_):
    ph = w.q((w.q(chr_ + 0x2470) or 0) + 0xE8) if chr_ else None
    raw = w.rd(ph + 0x70, 12) if ph else None
    return struct.unpack('<3f', raw) if raw and len(raw) == 12 else None


def _love_logic_of(w, no, want_vt):
    """the logic with vtable want_vt in player no's SQM entry on THIS game (passive vt+0x20 looks the bearer's
    240 module up the same way: SQM +8 vector, 0x20 per entry, key = player no) -> (module, logic) or (None, None)"""
    sqm = w.g(SQM_G)
    v0, v1 = (w.q(sqm + 8), w.q(sqm + 0x10)) if sqm else (None, None)
    n = (v1 - v0) // 0x20 if v0 and v1 and v1 >= v0 else 0
    for k in range(min(n, 16)):
        e = v0 + 0x20 * k
        if w.i(e) != no:
            continue
        for o in (8, 0x10, 0x18):
            mm = w.q(e + o)
            hd = (w.q(mm + 0x20) or w.q(mm + 0x28)) if mm else None
            lg = w.q(hd + 0x10) if hd else None
            if lg and w.q(lg) and w.q(lg) - w.base == want_vt:
                return mm, lg
    return None, None


def love(w, m, own_no, holder, logic, vt):
    """sigil14: Love Ephemeral. Bearer 240 (active) pairs (class B, stock pairing + SIGIL13_JOIN re-arm) with the
    record target, who holds 250 (passive). On the TARGET's game the passive vt+0x20 (0x118E3A8) sends step event 1
    {bearer team} when the bearer chr shows +0x144 bit 2 within 20 m. On the BEARER's game the active vt+0x20
    (0x118DDF4) sees its own chr +0x143 bit 3 -> forward event 4 (0x1196938: reunited logic+0x48 on every game) +
    reward type 4 (0x117AF0C) = row 2401 +4 once. The passive mirrors the bearer's reunited flag (same vt+0x20) ->
    its own event 4 + row 2501 +4 once on the target's game. Final phase: 0x118DA54 state 1 (reunited) / 2."""
    act = vt == LOVE_ACTIVE
    root = w.q(holder + 0x18)
    cond = (w.q(root + 0x90) or w.q(root + 0x98)) if root else None
    n = (w.q(cond + 0x58) or 0) if cond else 0
    hmap = _chr_by_handle(w)
    ents = []
    for k in range(min(n, 4)):
        e = w.d(cond + 0x10 + 4 * k) or 0
        ents.append((e & 0xFFFF, hmap.get(e & 0xFFFF, (None, None))))
    wr = w.q(holder + 0x28)
    own, a9 = (w.b(wr + 0xA8), w.b(wr + 0xA9)) if wr else (None, None)
    reun, note = w.b(logic + 0x48), w.b(logic + 0x49)
    mask = w.q(m + 0x38) or 0
    print('         love: %s logic %s | reunited logic+0x48 %s notice +0x49 %s | owner here +0xA8 %s +0xA9 %s | '
          'cond %s wants %s list %d: %s | mask 0x%X | module state %s' % (
              'ACTIVE 240 (bearer)' if act else 'PASSIVE 250 (Long-lost Love)' if vt == LOVE_PASSIVE else
              'base 0x%X' % vt, w.rel(logic), reun, note, own, a9, w.rel(cond), w.i(cond + 0xCC) if cond else None,
              n, ' '.join('0x%X->p%s(team %s)' % (h, p[0], p[1]) for h, p in ents) or 'EMPTY', mask & 0xFFF,
              w.i(m + 0x18)))
    rs = w.q(holder + 0x20)
    rw = []
    for k in range(10):
        rid = w.i(rs + 0x38 + 8 * k) if rs else None
        if rid in (None, 0, -1):
            break
        rw.append('%s x%s' % (rid, w.i(rs + 0x3C + 8 * k)))
    fin = w.g(FINAL_G)
    fb = ((w.b(fin + 0xC0) or 0) >> 4 & 1) if fin else None
    print('         love: rewards %s (2400/2500 = resolved, no Virtue; 2401/2501 = +4 once, type 4, paid where '
          'wp+0x11 == 0) | final-phase bit (+0xC0 bit 4) %s' % (' '.join(rw) or 'unreadable', fb))
    me = _module_chr(w, own_no)
    pno = ents[0][1][0] if ents else None
    pt = ents[0][1][1] if ents else None
    pc = _module_chr(w, pno) if pno is not None else None
    a, b = _chr_pos(w, me), _chr_pos(w, pc)
    dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))) if a and b else None
    mf, pf = _chr_flags(w, me), _chr_flags(w, pc)
    foc = w.g(FOCUS_G)
    foc = w.q(foc + 0x28) if foc else None
    foc = w.q(foc + 0xA8) if foc else None
    fh = w.d(foc + 0xA4) if foc else None
    fmt = lambda p: '-' if not p else '%.2f %.2f %.2f' % p
    print('         love: own pos %s | partner pos %s (goto / approach targets)' % (fmt(a), fmt(b)))
    print('         love: partner p%s team %s | 3D distance %s m (radius %.1f) | own chr +0x143b3 accepted %s '
          '+0x144b2 offering %s | partner +0x143b3 %s +0x144b2 %s | focus [[0x%X+0x28]+0xA8]+0xA4 %s vs partner '
          'chr+8 %s' % (pno, pt, None if dist is None else round(dist, 2), LOVE_RADIUS, mf[0], mf[1], pf[0], pf[1],
                        FOCUS_G, None if fh is None else '0x%X' % fh,
                        None if pc is None else '0x%X' % (w.d(pc + 8) or 0)))
    if not ents:
        v = ('STOP: class-B list EMPTY: not paired (5b: partner key MISSING, or module+0x79 1 and SIGIL13_JOIN '
             're-arm did not help, or nobody holds quest %s in slot 0)' % (w.i(cond + 0xCC) if cond else '?'))
    elif reun:
        v = ('REUNITED: event 4 done here; reward %s should read x1 (Virtue +4 only on the %s game); completion at the '
             'final phase -> state 1' % ('2401' if act else '2501', 'bearer\'s' if act else 'target\'s'))
    elif act:
        v = ('accept flag set on the bearer: event 4 + reward type 4 due now (owner game only: +0xA8 %s)' % own
             if mf[0] else
             'WAIT: bearer must play emote 22130 "Flowers for You" within %.0f m of p%s, then p%s accepts '
             '("Accept flowers"); this flag (+0x143 bit 3 on the bearer chr) is what ends it here' % (
                 LOVE_RADIUS, pno, pno))
    else:
        bm, bl = _love_logic_of(w, pno, LOVE_ACTIVE)
        br = w.b(bl + 0x48) if bl else None
        armed = pt is not None and pt <= 0xB and (mask >> pt) & 1
        if br:
            v = 'bearer p%s module HERE says reunited: mirror (event 4 + row 2501) due on the owner game' % pno
        elif armed:
            v = ('FLOWERS RECEIVED (step event 1, bearer team %s bit set): the "Accept flowers" prompt is for this '
                 'player now; bearer module here reunited=%s' % (pt, br))
        elif pf[1] and dist is not None and dist < LOVE_RADIUS:
            v = 'bearer OFFERING in range: step event 1 due from this game (owner +0xA8 %s)' % own
        elif pf[1]:
            v = 'bearer OFFERING but %s m away (> %.0f m): no step' % (None if dist is None else round(dist, 1),
                                                                        LOVE_RADIUS)
        else:
            v = ('WAIT: no offering seen on the bearer chr here (+0x144 bit 2 = 0); bearer 240 module on this game: '
                 '%s' % ('NOT FOUND (bearer SQM key missing here)' if not bl else 'reunited %s' % br))
    print('         love: -> %s' % v)


# ---------------------------------------------------------------- Eye of Muralis / Heretic (diag/net/sigil11_notes.md)
VT_EYE = 0x56F7FD0       # type-11 logic (quest 200), GOT 0x59E3458 + 0x10                                  [V]
VT_HERETIC = 0x56F7E60   # type-15 logic (quest 205), GOT 0x59E3450 + 0x10                                  [V]
EYE_FX = 0x1FD           # chr effect state the Eye step needs (vt+0xE8 0x118F9C0): the emote's "third eye" [V code, I name]
# sigil12_notes.md: identification = lock-on 0x16FF530 -> 0x11835C0 (lock tracker = SQM +0xB8 locked player no,
# +0xBC seconds; fires at T_COMMON row 0 +0x140) -> 0x117ADB0 on the LOCAL player's modules whose logic vt+0xE8 is
# true (Eye: third eye on) -> event 1 {target team} = the Eye mask bit. The participants "spot" (+8 / kind 3) route
# never fires for the Eye: SubQuestParam 200 +0x14 spot range = 0.0 [V param]. SIGIL12_EYE (sigil12_live.py) makes
# the Heretic's game raise event 1 {Inquisitor team} on its 205 module when that Eye event 1 lands there.
T_SUBQUEST = 0x3EA0      # SubQuestParam table of 0x15665A0 (repo REPO_G +0x3EA0 / +0x3EA8)                 [V]
# SIGIL12_EYE site words (memory byte order, as code_state reads them): (offset, stock, patched)       [V gen]
S12_SITE = ((0x11793E4, '681240F9', '509C0590'), (0x11793E8, 'A80000B4', '10622691'),
            (0x11793EC, '001140F9', '00021FD6'))


def _s12_state(w):
    st = [code_state(w, o, a, b) for o, a, b in S12_SITE]
    return 'PATCHED' if all(s == 'PATCHED' for s in st) else 'original' if all(s == 'original' for s in st) else \
        'MIXED %s (half-applied: do not fight here)' % '/'.join(st)


def _eye_masks(w):
    """{player no: Eye module team mask +0x38} for every Eye (VT_EYE) module in the SQM entries of this game"""
    out = {}
    sqm = w.g(SQM_G)
    v0, v1 = (w.q(sqm + 8), w.q(sqm + 0x10)) if sqm else (None, None)
    n = (v1 - v0) // 0x20 if v0 and v1 and v1 >= v0 else 0
    for k in range(min(n, 16)):
        e = v0 + 0x20 * k
        for o in (8, 0x10, 0x18):
            mm = w.q(e + o)
            hd = (w.q(mm + 0x20) or w.q(mm + 0x28)) if mm else None
            lg = w.q(hd + 0x10) if hd else None
            if lg and w.q(lg) and w.q(lg) - w.base == VT_EYE:
                out[w.i(e)] = w.q(mm + 0x38) or 0
    return out


def eye_ident(w):
    """sigil12 1: the identification inputs on THIS game (lock tracker, threshold, dead spot range)"""
    sqm = w.g(SQM_G)
    repo, crepo = w.g(REPO_G), w.q(w.g(REPO_GOT) or 0)
    crow, _ = param_row(w, crepo, T_COMMON, 0)
    r200, _ = param_row(w, repo, T_SUBQUEST, 200)
    r205, _ = param_row(w, repo, T_SUBQUEST, 205)
    print('   identification = LOCK-ON (sigil12 1): lock tracker SQM+0xB8 player %s held %s s | needs >= %s s '
          '(common row 0 +0x140) | spot range SubQuestParam 200 +0x14 %s, 205 +0x14 %s (0.0 = participants spot '
          'route never fires; ignore SPOTTED +8) | SIGIL12_EYE %s' % (
              w.i(sqm + 0xB8) if sqm else None, _f32(w, sqm + 0xBC) if sqm else None,
              _f32(w, crow + 0x140) if crow else None, _f32(w, r200 + 0x14) if r200 else None,
              _f32(w, r205 + 0x14) if r205 else None, _s12_state(w)))


def _f32(w, a):
    b = w.rd(a, 4)
    return struct.unpack('<f', b)[0] if b and len(b) == 4 else None


def _var_handles(w, var):
    """SQM var (vt 0x56F9490, add 0x119C160): count u64 +0xA8 (max 16), u32 entries at +0x60, low 16 bits = chr handle"""
    if not var:
        return None
    n = w.q(var + 0xA8) or 0
    return [(w.d(var + 0x60 + 4 * k) or 0) & 0xFFFF for k in range(min(n, 16))]


def _third_eye(w, chr_):
    """mirror of 0x118F9C0: effect list [[chr+0x20]+0x90]: gate byte +0x2CA & 0x1C, entries (+0x20 flags & 0x800C0003
    == 0, [+0x80]+0x146 == 0x1FD), chain +0x88, outer chain +0x18. Returns True / False / None (unreadable)"""
    data = w.q(chr_ + 0x20) if chr_ else None
    mgr = w.q(data + 0x90) if data else None
    if not mgr:
        return None
    if not (w.b(mgr + 0x2CA) or 0) & 0x1C:
        return False
    node, outer = w.q(mgr + 8), mgr + 8
    for _ in range(256):
        while node:
            fl = w.d(node + 0x20) or 0
            row = w.q(node + 0x80)
            if not fl & 0x800C0003 and row and w.h(row + 0x146) == EYE_FX:
                return True
            node = w.q(node + 0x88)
        outer = w.q(outer + 0x18) if outer else None
        if not outer:
            return False
        node = w.q(outer)
    return False


def _module_chr(w, no):
    for e in w.players(12):
        data = w.q(e[0] + 0x20)
        pg = w.q(data + 0x1D0) if data else None
        if pg and w.i(pg + 0xD0) == no:
            return e[0]
    return None


def eye(w, m, own_no):
    """per module: Eye (type 11) or Heretic (type 15) state. Eye flow [V]: host picks (0x118F260) -> every game builds
    the Heretic's 205 slot-2 module (kind 1) -> Eye condition (class D, root+0x90) lists players with a type-15 module
    -> bearer's game identifies him by LOCK-ON (sigil12 1: 0x11835C0 -> 0x117ADB0, needs third eye 0x1FD; the
    participants +8 spot route is dead, range 0.0) -> event 1 = Heretic team bit in module+0x38 -> each kill of a
    listed victim with the bit (0x117B5B0) pays row 2000 type 1 (+5, repeats) on the bearer's game."""
    holder = w.q(m + 0x20) or w.q(m + 0x28)
    logic = w.q(holder + 0x10) if holder else None
    vt = (w.q(logic) - w.base) if logic and w.q(logic) else None
    if vt not in (VT_EYE, VT_HERETIC):
        return
    hmap = _chr_by_handle(w)
    mask = w.q(m + 0x38) or 0
    root = w.q(holder + 0x18)
    cond = (w.q(root + 0x90) or w.q(root + 0x98)) if root else None
    n = (w.q(cond + 0x58) or 0) if cond else 0
    listed = []
    for k in range(min(n, 16)):
        e = w.d(cond + 0x10 + 4 * k) or 0
        p = hmap.get(e & 0xFFFF, (None, None))
        listed.append((e & 0xFFFF, p[0], p[1], (e >> 16) & 0xFF))
    wr = w.q(holder + 0x28)
    own, a9 = (w.b(wr + 0xA8), w.b(wr + 0xA9)) if wr else (None, None)
    name = 'EYE (Inquisitor, 200)' if vt == VT_EYE else 'HERETIC (205)'
    print('         eye: %s logic %s | owner here +0xA8 %s +0xA9 %s | team mask 0x%X | cond %s lists %s' % (
        name, w.rel(logic), own, a9, mask & 0xFFF, w.rel(cond),
        ' '.join('0x%X->p%s(team %s, +2 %d)' % x for x in listed) or 'EMPTY'))
    part = w.q(root + 0x40) if root else None
    if part:
        b0, b1 = w.q(part + 0x40), w.q(part + 0x48)
        cnt = (b1 - b0) // 0x14 if b0 and b1 and b1 >= b0 else 0
        print('         eye: participants %s row id +0x10 %s (+0x14 %s) key +0x18 %s +0x60 %s | %d entries' % (
            w.rel(part), w.i(part + 0x10), w.i(part + 0x14), w.i(part + 0x18), w.b(part + 0x60), cnt))
        for k in range(min(cnt, 12)):
            e = b0 + 0x14 * k
            hd = w.h(e) or 0
            p = hmap.get(hd, (None, None))
            print('            entry 0x%X p%s team %s: SPOTTED +8 %s shown +9 %s pending +0xC %s done +0x10 %s felt '
                  '+0x11 %s | LOS timer %s | team bit %s' % (
                      hd, p[0], p[1], w.b(e + 8), w.b(e + 9), w.i(e + 0xC), w.b(e + 0x10), w.b(e + 0x11),
                      _f32(w, e + 4), 'SET' if p[1] is not None and p[1] <= 0xB and (mask >> p[1]) & 1 else '-'))
    if vt == VT_EYE:
        picked, purged = _var_handles(w, w.q(logic + 0x40)), _var_handles(w, w.q(logic + 0x48))
        tx = lambda hs: 'unreadable' if hs is None else ' '.join(
            '0x%X->p%s' % (h, hmap.get(h, (None,))[0]) for h in hs) or '-'
        fx = _third_eye(w, _module_chr(w, own_no))
        print('         eye: ended +0x58 %s | picked (logic+0x40, host only) %s | purged (logic+0x48) %s | third eye '
              '0x%X on bearer %s | kills module+0x50 %s' % (
                  w.b(logic + 0x58), tx(picked), tx(purged), EYE_FX,
                  {True: 'ACTIVE', False: 'off', None: 'unreadable'}[fx], w.i(m + 0x50)))
        if not listed:
            v = 'WAIT: no Heretic listed (no type-15 module on this game: selector / kind 1 not done)'
        elif not any(p is not None and p <= 0xB and (mask >> p) & 1 for _, _, p, _ in listed):
            v = ('WAIT: Heretic listed, not identified yet (bearer: emote for the third eye, then LOCK ON to him for '
                 'the threshold time - lock tracker line above; kills pay NOTHING now)')
        else:
            v = ('IDENTIFIED: Heretic team bit set (lock-on, sigil12 1); a kill of him by the bearer pays row 2000 (+5) '
                 'on the bearer game; after the first one his 205 module is cleared [I] so he drops off the list')
        print('         eye: -> %s' % v)
    else:
        # sigil12 2: SIGIL12_EYE raises THIS mask (Inquisitor team bit) on the Heretic's game when the Eye event 1
        # for the Heretic's team lands there; event 1 then reaches every game (0x8B)
        own_team = _chr_by_handle(w)
        own_team = next((t for no, t in own_team.values() if no == own_no), None)
        emasks = _eye_masks(w)
        parts = []
        for hd, pno, pt, _ in listed:
            em = emasks.get(pno)
            ident = em is not None and own_team is not None and own_team <= 0xB and (em >> own_team) & 1
            armed = pt is not None and pt <= 0xB and (mask >> pt) & 1
            if armed and ident:
                st = 'ARMED (identified -> armed: his kill of p%s pays row 2050 +5 once)' % pno
            elif armed:
                st = 'ARMED without identification here (Eye event 1 not on this game yet, or not stock-made) [check]'
            elif ident:
                st = ('MISSING: p%s identified him but his mask lacks team %s (SIGIL12_EYE not applied on the '
                      'Heretic\'s game, or event 1 not arrived yet)' % (pno, pt))
            else:
                st = 'WAIT (not identified by p%s yet; his kills of p%s pay nothing)' % (pno, pno)
            parts.append('p%s team %s: %s' % (pno, pt, st))
        print('         eye: HERETIC p%s team %s | mask 0x%X | SIGIL12_EYE %s | %s' % (
            own_no, own_team, mask & 0xFFF, _s12_state(w), ' ; '.join(parts) or 'no Inquisitor listed'))
        print('         eye: module state (module_txt above): 1 = Heretic won (row 2050 paid), 2 = Heretic killed '
              '(then the 205 module is cleared by event 5 [I])')


def eye_overview(w, gdm, v0, n):
    """E. one line per game: who holds 205 (the Heretic) / 200 (bearers), host byte, Virtue base per player"""
    print(' E. EYE OF MURALIS overview (sigil11_notes.md): host byte main+0x%X = %s (0 = host: selector runs here)' % (
        ROLE_B, w.b(w.base + ROLE_B)))
    keyed = {}
    for k in range(min(n, 16)):
        e = v0 + 0x20 * k
        keyed[w.i(e)] = [w.q(e + o) for o in (8, 0x10, 0x18)]
    for lab, p in pgd_list(w, gdm):
        if '(= above)' in lab:
            continue
        no = w.i(p + 0xD0)
        if no in (None, -1):
            continue
        qs = [w.i(mm + 0x4C) if mm else None for mm in keyed.get(no, [None] * 3)]
        role = 'HERETIC' if 205 in qs else 'BEARER' if 200 in qs else '-'
        print('   player %s: %s | module quests %s | pgd slots %s/%s/%s | +0x46A0 %s (selector wants != 0 [I]) | '
              'Virtue base +0x42C8 %s' % (no, role, qs, w.i(p + 0x46E0), w.i(p + 0x46E4), w.i(p + 0x46E8),
                                         w.b(p + 0x46A0), s16(w.h(p + 0x42C8))))


def main():
    games = sys.argv[1] if len(sys.argv) > 1 else 'AB'
    for g in games:
        w = W(g)
        game(w)
        w.report_missing()
        print()


if __name__ == '__main__':
    main()
