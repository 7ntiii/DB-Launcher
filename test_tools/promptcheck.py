"""Why does a prompt not show? Read-only replay of the game's own prompt checks, in the game's order.
python diag/twin/promptcheck.py A circle GEOM_ADDR   kin circle (geom address from 'circles.py A')
python diag/twin/promptcheck.py A bell [N]           asset-access entry N (default 0 = Clock Tower bell, param 9005)
Only READS memory (world_lib / mem). Run it while standing where the prompt should show.
Every line: [PASS] / [FAIL] / [INFO] / [ ?? ] (not evaluable from memory), the code address of the test and the values.
The first FAIL is the check the game stops at. Design and addresses: diag/net/prompt_notes.md.
The range test is now the exact 0x1B6030C replay: button origin = dummy-poly world matrix (record x pose bone),
player facing = -(Z row of the chr model matrix [chr+0x68]+0x150). Geometry: diag/net/prompt_spot_notes.md.
[I] / [??] mark the cases that are not evaluable from memory (unknown pose type, uncached pose).
After the range test it replays the row-specific tests of the generic button system 0x1B5AB20 (invalid event flag
row+0x34 - 8332 uses flag 5809 -, chr state bit row+0x44, ray test row+0x2D). Bell notes: diag/net/bell_notes.md."""
import math
import struct
import sys

sys.path.insert(0, 'diag/twin')
from world_lib import W, fmt3, WCM_G, PAR_G, GEOM_G

PROCMGR_G = 0x5B3D620    # CSActionMenuAssetProcessor manager, processors at +8+k*8 (k 0..14)   [V 0x11A2528]
BTNMGR_G = 0x5B45728     # action-button manager (0x1B5DB10 / 0x1B5F6FC x0)                    [V 0x11A2764]
REPO_G = 0x5B3CE68       # param repository                                                    [V 0x15588C4]
DEFPLAYER_G = 0x5B583B0  # fallback player-game-data when [chr+0x20]+0x1D0 is null             [V 0x119EE68]
MISSION_G = 0x5B44E88    # mission object, +0xB8 mission id (0xD7F300)                          [V 0xD7F424]
GDM_G = 0x5B57EB8        # [x+0x68]+0x58..+0x60 = env-event history vector (last = current)    [V 0xD6A924, 0xEFDDF0]
AAE_G = 0x5B59B60        # CSAssetAccessEventMan                                                [V 0x182F2F0]
MGR3_G = 0x5B3CE08       # session manager (0xD685EC needs it)                                  [V]
BUDDY_PROC_VT = 0x56F96E0  # CSBuddySummonDoorActionMenuAssetProcessor                          [V]
ENV_COND_VT = 0x56D84D8    # asset-access env condition object (vptr), vt+0x50 = 0xD6A8F0       [V 0xD6657C]
SEQ_VT = 0x56D8608         # asset-access sequence (vptr), vt+0x60 = 0xD6E144 = ldr w0,[x0,#0x50] [V]
# param repository slots (count u32 at slot, resource ptr at slot+8)                            [V]
P_ACTIONBUTTON, P_AAE, P_ENVEVENT, P_ENEMYCOMMON, P_BUDDYSPECIES = 0xBB8, 0x4128, 0x32D0, 0x20D0, 0x3E58

first_fail = [None]


def out(state, addr, name, detail=''):
    tag = {True: 'PASS', False: 'FAIL', None: ' ?? ', 'i': 'INFO'}[state]
    mark = ''
    if state is False and first_fail[0] is None:
        first_fail[0] = (addr, name)
        mark = '   <-- first failing check'
    print('[%s] %-10s %-46s %s%s' % (tag, addr, name, detail, mark))


# ---------- params ----------
def pfile(w, slot):
    repo = w.g(REPO_G)
    if not repo or not w.d(repo + slot):
        return None
    res = w.q(repo + slot + 8)
    m = w.q(res + 0x70) if res else None
    return w.q(m + 0x78) if m else None


def prows(w, f):
    """(id, row address) of every row; layouts of 0x15588C4 [V]"""
    if not f:
        return []
    n, fmt, fl = w.h(f + 0xA) or 0, w.b(f + 0x2D) or 0, w.b(f + 0x2E) or 0
    t = (fmt & 0x7F) - 2
    if t == 0:                                   # 0x1558924
        start, size, wide = 0x30, 12, False
    elif t == 1 or (t == 3 and not fmt & 0x80):  # 0x1558958 / 0x1558950
        start, size, wide = 0x40, 12, False
    elif t in (2, 3):                            # 0x1558964: +0x2E bit 1 -> 0x18-byte entries, u64 offset
        start, size, wide = (0x40, 0x18, True) if fl & 2 else (0x40, 12, False)
    else:
        return []
    raw = w.big(f + start, n * size) if n else b''
    if raw is None:
        return []
    rows = []
    for k in range(n):
        rid = struct.unpack_from('<i', raw, k * size)[0]
        off = struct.unpack_from('<Q', raw, k * size + 8)[0] if wide else struct.unpack_from('<I', raw, k * size + 4)[0]
        rows.append((rid, f + off))
    return rows


def prow(w, slot, rid):
    for i, a in prows(w, pfile(w, slot)):
        if i == rid:
            return a
    return None


# ---------- small helpers ----------
def chain126(w, asset):
    """True if bits 0 and 1 of asset+0x126 are set on the asset and every parent [[a+0x10]+0x430] [V 0x11A2608]"""
    vals, a, guard = [], asset, 0
    while a and guard < 16:
        v = w.b(a + 0x126)
        vals.append(v)
        info = w.q(a + 0x10)
        a = w.q(info + 0x430) if info else None
        guard += 1
    ok = all(v is not None and (v & 3) == 3 for v in vals)
    return ok, ' '.join('%s' % ('%02x' % v if v is not None else '?') for v in vals)


def player_data(w, chr_):
    """p = [[chr+0x20]+0x1D0] or *(main+0x5B583B0); player no = p+0xD0, slot = p+0x104 (only from +0x1D0) [V]"""
    cd = w.q(chr_ + 0x20) if chr_ else None
    p = w.q(cd + 0x1D0) if cd else None
    pd = p or w.g(DEFPLAYER_G)
    return cd, p, (w.i(pd + 0xD0) if pd else None)


def busy(w, info, p):
    """0x11A2650..0x11A2690 / 0xD67034..0xD67074 [V]"""
    mask, busyb = w.q(info + 0x468) or 0, w.b(info + 0x470)
    if p:
        slot = w.b(p + 0x104)
        if slot is not None and slot <= 11:
            taken = (mask >> slot) & 1
            return (not taken and not busyb), 'slot %d mask %03x bit %d busy %s' % (slot, mask & 0xFFF, taken, busyb)
        return (not (mask & 0xFFF) and not busyb), 'slot %s (>11) mask %03x busy %s' % (slot, mask & 0xFFF, busyb)
    return (not (mask & 0xFFF) and not busyb), '[chr+0x20]+0x1D0 null -> any slot: mask %03x busy %s' % (mask & 0xFFF, busyb)


def std_list(w, anchor, limit=64):
    """libc++ list: anchor +8 = first; node +8 next, value at node+0x10"""
    out_, n = [], w.q(anchor + 8)
    while n and n != anchor and len(out_) < limit:
        out_.append(n)
        n = w.q(n + 8)
    return out_


# ---------- dummy-poly world transform, as 0x1B5D4C0 type 3 -> 0xF2B620 / 0xF2AD20 compute it [V] ----------
MODEL_VT = 0x57583C0     # model resource [[geom+0x40]+0x10]+0x130: vt+0x60 = 0x1BC7DAC ([+0x78]), vt+0x68 = 0x1BC7DB4 [V]
# pose objects [[model+0x60]] (vt+0x30 = bone matrix by index, called from 0x1BECA1C) [V per function]
POSE_VT = {0x5758200: '0x1BC5974 3x4 array [+0x98], count [[+0x80]+4]',
           0x5758538: '0x1BC9964 3x4 array [[+0x80]+0x18], count [[+0x80]+0x14]',
           0x5757D68: '0x1BC02A0 single 3x4 at +0x80 (index 0 only)',
           0x5757DD8: '0x1BC05B4 single 4x4 at +0x80 (index 0 only)',
           0x5758350: '0x1BC73BC T/Q/S array (+0x58 -> 0x37AF4A8 cache +0x18 when byte +0x90 set)',
           # asset pose (bell trigger AEG105_312): vt+0x30 = 0x1BBFF5C: idx < u32 +0x70 -> 3x4 at [+0x78]+idx*0x30,
           # transposed with D = bss 0x6B23960 (same zip as 0x1BC5974). World space [I strong]: vt+0x38 0x1BBFEE0
           # adds one offset to the translation of every bone (world-origin shift); vt+0x28 0x1BBFC9C copies a fresh
           # array from the anim job [+0x58] (vt+0x48 of the job). Dtors 0x1BBFD60/0x1BBFE00 [V].
           0x5757CF8: '0x1BBFF5C 3x4 array [+0x78], count u32 +0x70 (asset pose)'}
IDENT = [(1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)]  # ro 0x4ED6300 [V]


def rows4(w, a, n=4):
    raw = w.rd(a, 16 * n)
    return [struct.unpack_from('<4f', raw, 16 * k) for k in range(n)] if raw else None


def tr34(abc):
    """0x1BC5974 & co: rows A,B,C (3x4) -> 4x4 with out row i = (A[i], B[i], C[i], D[i]), D = (0,0,0,1) [I: D in bss]"""
    a, b_, c = abc
    d = (0.0, 0.0, 0.0, 1.0)
    return [(a[i], b_[i], c[i], d[i]) for i in range(4)]


def mmul(l, m):
    """0x1BECA1C: out_i = sum_j L_i[j] * M_j (row vectors, translation in row 3) [V]"""
    return [tuple(sum(l[i][j] * m[j][k] for j in range(4)) for k in range(4)) for i in range(4)]


def quat_mat(t_, q, s):
    """0x1BC73BC [V]: rows = standard rotation rows of q (x,y,z,w) scaled by s.x/s.y/s.z, row 3 = (t, 1)"""
    x, y, z, ww = q
    r0 = (1 - 2 * (y * y + z * z), 2 * (x * y + z * ww), 2 * (x * z - y * ww), 0.0)
    r1 = (2 * (x * y - z * ww), 1 - 2 * (x * x + z * z), 2 * (y * z + x * ww), 0.0)
    r2 = (2 * (x * z + y * ww), 2 * (y * z - x * ww), 1 - 2 * (x * x + y * y), 0.0)
    return [tuple(v * s[0] for v in r0), tuple(v * s[1] for v in r1), tuple(v * s[2] for v in r2),
            (t_[0], t_[1], t_[2], 1.0)]


def pose_matrix(w, obj2, idx):
    """obj2 vt+0x30(obj2, out, idx). Returns (4x4 or None, text)."""
    vp = w.q(obj2)
    rv = vp - w.base if vp else None
    tag = 'pose %s vt %s' % (w.rel(obj2), w.rel(vp))
    if rv == 0x5757CF8:
        cnt, arr = w.d(obj2 + 0x70), w.q(obj2 + 0x78)
        if cnt is None or idx >= cnt or not arr:
            return None, '%s: bone %d >= count %s (or array %s null) -> vt+0x30 returns 0' % (tag, idx, cnt, w.rel(arr))
        abc = rows4(w, arr + idx * 0x30, 3)
        return (tr34(abc) if abc else None), '%s %s bone %d/%s' % (tag, POSE_VT[rv], idx, cnt)
    if rv in (0x5758200, 0x5758538):
        x80 = w.q(obj2 + 0x80)
        if rv == 0x5758200:
            cnt, arr = w.d(x80 + 4) if x80 else None, w.q(obj2 + 0x98)
        else:
            cnt, arr = w.d(x80 + 0x14) if x80 else None, w.q(x80 + 0x18) if x80 else None
        if cnt is None or idx >= cnt or not arr:
            return None, '%s: bone %d >= count %s -> vt+0x30 returns 0' % (tag, idx, cnt)
        abc = rows4(w, arr + idx * 0x30, 3)
        return (tr34(abc) if abc else None), '%s %s bone %d/%s' % (tag, POSE_VT[rv], idx, cnt)
    if rv in (0x5757D68, 0x5757DD8):
        if idx != 0:
            return None, '%s: bone %d != 0 -> vt+0x30 returns 0' % (tag, idx)
        m = rows4(w, obj2 + 0x80, 3 if rv == 0x5757D68 else 4)
        if m and rv == 0x5757D68:
            m = tr34(m)
        return m, '%s %s' % (tag, POSE_VT[rv])
    if rv == 0x5758350:
        s = obj2 + 0x58
        if not w.b(s + 0x38):
            return None, '%s: pose cache byte +0x90 is 0 (0x37AF4A8 would rebuild it; not evaluable) [??]' % tag
        arr, cnt = w.q(s + 0x18), w.d(s + 0x20)
        if cnt is None or idx >= cnt or not arr:
            return None, '%s: bone %d >= count %s -> vt+0x30 returns 0' % (tag, idx, cnt)
        e = rows4(w, arr + idx * 0x30, 3)
        return (quat_mat(e[0], e[1], e[2]) if e else None), '%s %s bone %d/%s' % (tag, POSE_VT[rv], idx, cnt)
    fn = w.q(vp + 0x30) if vp else None
    return None, '%s: UNKNOWN pose type (vt+0x30 = %s), not evaluable [??]' % (tag, w.rel(fn))


def geom_matrix(w, g):
    """CSWorldGeomIns world matrix rows +0xE0 X, +0xF0 Y, +0x100 Z, +0x110 T (0xF2AB2C normalises X/Y/Z) [V]"""
    m = rows4(w, g + 0xE0)
    if not m:
        return None
    out = []
    for k in range(3):
        v = m[k][:3]
        n = math.sqrt(sum(c * c for c in v)) or 1.0
        out.append((v[0] / n, v[1] / n, v[2] / n, 0.0))
    out.append(m[3])
    return out


def dummy_world(w, g, dmy):
    """Exact 0x1B5D4C0 (type 3 = geom target). Returns (pos, zaxis, how, lines).
    pos/zaxis = what 0x1B6030C uses as the button origin / button forward."""
    lines = []
    gm = geom_matrix(w, g)
    gpos, gz = (gm[3][:3], gm[2][:3]) if gm else (None, None)
    fallback = (gpos, gz)
    if dmy is None or dmy == -1:
        return gpos, gz, 'row+4 = -1: geom origin and geom Z (0x1B603CC)', lines
    m = w.q(g + 0x40)
    if not m:
        return gpos, gz, 'geom+0x40 null -> 0xF2B620 = 0 -> geom origin (0x1B603CC)', lines
    if w.q(m + 0x28):
        return gpos, gz, '[geom+0x40]+0x28 != 0 -> 0xF2B620 = 0 -> geom origin', lines
    m10 = w.q(m + 0x10)
    mdl = w.q(m10 + 0x130) if m10 else None
    if not mdl:
        return gpos, gz, 'model [[geom+0x40]+0x10]+0x130 null (game would crash or skip) [??]', lines
    mvt = w.q(mdl)
    if mvt != w.base + MODEL_VT:
        lines.append('model vt %s is not main+0x%X: table/transform slots not verified for this type [??]' % (
            w.rel(mvt), MODEL_VT))
    d = w.q(mdl + 0x78)
    if not d:
        return gpos, gz, 'dummy table [model+0x78] null [??]', lines
    nmap, recs, mp = w.i(d + 4), w.q(d + 8), w.q(d + 0x10)
    nrec = w.d(d)
    # binary search exactly as 0xF2B680 / 0xF2ADAC (unsigned id compare)
    lo, hi, ent = 0, (nmap or 0) - 1, None
    while mp and lo <= hi:
        mid = (lo + hi) >> 1
        k = w.d(mp + mid * 8)
        if k is None:
            break
        if k == dmy:
            ent = mp + mid * 8
            break
        if k < dmy:
            lo = mid + 1
        else:
            hi = mid - 1
    if ent is None:
        return gpos, gz, 'dummy poly %d not in the id map (%s ids) -> 0xF2B620 = 0 -> geom origin' % (dmy, nmap), lines
    first, nxt = w.i(ent + 4), w.i(ent + 0xC)
    cnt = (nxt - first) if None not in (first, nxt) else None
    lines.append('dummy table %s: %s records at %s, %s ids; id %d -> first %s count %s' % (
        w.rel(d), nrec, w.rel(recs), nmap, dmy, first, cnt))
    if not recs or cnt != 1:
        return gpos, gz, 'dummy poly %d count %s != 1 -> 0xF2B620 != 1 -> geom origin and geom Z (0x1B5D5F8)' % (
            dmy, cnt), lines
    rec = recs + first * 0x50
    parent = w.d(rec + 4)
    loc = rows4(w, rec + 0x10)
    lines.append('record %s: parent/bone index +4 = %s, local rows +0x10 X %s Y %s Z %s T %s' % (
        w.rel(rec), parent, fmt3(loc[0][:3]) if loc else '?', fmt3(loc[1][:3]) if loc else '?',
        fmt3(loc[2][:3]) if loc else '?', fmt3(loc[3][:3]) if loc else '?'))
    p60 = w.q(mdl + 0x60)
    obj2 = w.q(p60) if p60 else None
    if not obj2:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), ('[[model+0x60]] null: vt+0x68 0x1BC7DB4 returns 0, out stays IDENTITY '
                                                  '-> the game tests against WORLD ORIGIN (prompt impossible)'), lines
    mtx, why = pose_matrix(w, obj2, parent)
    lines.append(why)
    if mtx is None:
        if 'not evaluable' in why:
            if gm and loc:
                alt = mmul(loc, gm)
                lines.append('[I] if the bone were the geom matrix: pos %s Z %s' % (fmt3(alt[3][:3]), fmt3(alt[2][:3])))
                return alt[3][:3], alt[2][:3], 'APPROXIMATION [I]: pose not readable, bone = geom matrix', lines
            return fallback[0], fallback[1], 'APPROXIMATION [I]: pose not readable, geom origin', lines
        return (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), ('bone matrix fails -> out stays IDENTITY -> the game tests against '
                                                  'WORLD ORIGIN (prompt impossible)'), lines
    if not loc:
        return fallback[0], fallback[1], 'record unreadable [??]', lines
    wm = mmul(loc, mtx)
    pos, z = wm[3][:3], wm[2][:3]
    if gpos and math.dist(pos, gpos) > 15.0 and gm:
        alt = mmul(wm, gm)
        lines.append('WARNING: dummy point %s is %.1f m from the geom origin; if the pose were model-space the point '
                     'would be %s. The game uses the first value [V], so the prompt would sit far away.' % (
                         fmt3(pos), math.dist(pos, gpos), fmt3(alt[3][:3])))
    return pos, z, 'dummy poly %d world = record x bone %s (exact [V])' % (dmy, parent), lines


def player_facing(w, chr_):
    """What 0x11A24D8 / 0x1B5D21C store at src+0x20: -( [chr+0x68]+0x170 ) = minus the Z row of the chr model
    world matrix at [chr+0x68]+0x150 (+0x150 X, +0x160 Y, +0x170 Z, +0x180 T). Only x and z are used [V]."""
    m68 = w.q(chr_ + 0x68)
    m = rows4(w, m68 + 0x150) if m68 else None
    if not m:
        return None, None, m68
    return (-m[2][0], -m[2][1], -m[2][2]), m, m68


def unit_xz(v):
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 0 else None


def range_test(w, row, tgt, chr_):
    """Exact replay of 0x1B5DB10 -> shape 0 = 0x1B6030C (cylinder) [V]. tgt = the geom (target type 3)."""
    shape, dmy = w.b(row), w.i(row + 4)
    r, ang, hgt, bot = w.f(row + 0xC), w.i(row + 0x10), w.f(row + 0x1C), w.f(row + 0x20)
    f24, ang2 = w.b(row + 0x24), w.i(row + 0x28)
    head = 'shape %s dmypoly %s radius %s cone %s height %s bottom %s +0x24 %s face %s' % (
        shape, dmy, r, ang, hgt, bot, f24, ang2)
    print('       %s' % head)
    if shape != 0:
        return None, head + ' (shape %s is not the cylinder 0x1B6030C: not evaluated)' % shape
    pp = w.chr_pos(chr_)                                     # src+0x10 = [[chr+0x2470]+0xE8]+0x70 [V 0x11A240C]
    fw, cm, m68 = player_facing(w, chr_)
    tp, tz, how, lines = dummy_world(w, tgt, dmy)
    print('       button origin: %s' % how)
    for ln in lines:
        print('         %s' % ln)
    if None in (pp, tp, tz, r, hgt, bot, ang, ang2, f24) or fw is None:
        return None, 'data missing (player %s target %s facing %s)' % (fmt3(pp), fmt3(tp), fw)
    gpos = w.geom_pos(tgt)
    print('       player %s  button %s  button Z %s  geom origin %s' % (fmt3(pp), fmt3(tp), fmt3(tz), fmt3(gpos)))
    # 1 max horizontal distance: s4 = -1.0 from 0x1B5DB68 -> skipped
    hd2 = (tp[0] - pp[0]) ** 2 + (tp[2] - pp[2]) ** 2
    # 2 height window, strict (0x1B60400)
    lo, hi = tp[1] + bot, tp[1] + bot + hgt
    ok_y = lo < pp[1] < hi
    # 3 radius (+ extra 0.0 from the caller's s0), strict (0x1B60414)
    ok_r = hd2 < r * r
    # 4 cone at the BUTTON: angle between button Z (xz) and button->player (xz) (0x1B60450..0x1B605B8)
    ok_c, cone = True, 'cone off (180)'
    zh = unit_xz((tz[0], tz[2]))
    if ang != 180:
        h = unit_xz((pp[0] - tp[0], pp[2] - tp[2]))
        if h is None or zh is None:
            ok_c, cone = None, 'cone: zero-length vector -> bss default 0x6B23850 used [??]'
        else:
            dot = h[0] * zh[0] + h[1] * zh[1]
            ok_c = not (dot < math.cos(math.radians(ang)))
            cone = 'player is %.0f deg off the button Z (max %d)' % (math.degrees(math.acos(max(-1, min(1, dot)))), ang)
    # 5 facing (0x1B605BC): +0x24 == 0: player fwd vs player->button; == 1: player fwd vs -button Z; else fail
    fh = unit_xz((fw[0], fw[2]))
    if f24 == 0:
        dv = unit_xz((tp[0] - pp[0], tp[2] - pp[2]))
        if dv is None or fh is None:
            ok_f, face = None, 'facing: zero-length vector [??]'
        else:
            dot = dv[0] * fh[0] + dv[1] * fh[1]
            ok_f = dot >= math.cos(math.radians(ang2))
            face = 'player faces %.0f deg away from the button (max %d)' % (
                math.degrees(math.acos(max(-1, min(1, dot)))), ang2)
    elif f24 == 1:
        if zh is None or fh is None:
            ok_f, face = None, 'facing: zero-length vector [??]'
        else:
            dot = -(fh[0] * zh[0] + fh[1] * zh[1])
            ok_f = dot >= math.cos(math.radians(ang2))
            face = 'player fwd vs -button Z %.0f deg (max %d)' % (math.degrees(math.acos(max(-1, min(1, dot)))), ang2)
    else:
        ok_f, face = False, '+0x24 = %s: neither 0 nor 1 -> always fails (0x1B605C4)' % f24
    print('       [%s] y %.2f in (%.2f, %.2f)   [%s] horiz %.2f < %.2f   [%s] %s   [%s] %s' % (
        ok_y, pp[1], lo, hi, ok_r, math.sqrt(hd2), r, ok_c, cone, ok_f, face))
    # player facing as the game reads it, and the fields a teleport writes
    phys = w.q((w.q(chr_ + 0x2470) or 0) + 0xE8)
    _, ephys, _ = w.me()
    yaw64 = w.f(ephys + 0x64) if ephys else None
    print('       player fwd (game) = -([chr+0x68]+0x170) = (%.3f, %.3f, %.3f), yaw atan2(x,z) = %.3f rad; '
          'chr+0x68 = %s, model T +0x180 %s' % (fw[0], fw[1], fw[2], math.atan2(fw[0], fw[2]), w.rel(m68),
                                                fmt3(cm[3][:3])))
    print('       teleport fields: phys entry0+0x28 = %s (chr+0x2470 -> +0xE8 = %s), yaw phys+0x64 = %s; '
          'if this yaw does not match the game fwd yaw after a teleport, the facing comes from the model matrix only' % (
              w.rel(ephys), w.rel(phys), '%.3f' % yaw64 if yaw64 is not None else None))
    # suggested spot: 1.5 m from the button origin on its Z axis (xz), facing the button
    if zh is not None:
        sx, sz = tp[0] + 1.5 * zh[0], tp[2] + 1.5 * zh[1]
    else:
        sx, sz = tp[0] + 1.5, tp[2]
    gy = gpos[1] if gpos else tp[1]
    sy = gy if lo < gy + 0.1 < hi else lo + 0.2
    fx, fz = tp[0] - sx, tp[2] - sz
    yaw = math.atan2(fx, fz)
    if gpos:
        ox, oz = sx - gpos[0], sz - gpos[2]
        od = math.hypot(ox, oz)
        rel = '%.2f m from the geom origin toward (%.2f, %.2f)' % (od, ox / od if od else 0, oz / od if od else 0)
    else:
        rel = 'geom origin unknown'
    print('       STAND AT (%.2f, %.2f, %.2f) FACING yaw=%.3f (dir %.2f, %.2f; world_lib.goto convention), i.e. %s' % (
        sx, sy, sz, yaw, fx / 1.5, fz / 1.5, rel))
    ok = bool(ok_y and ok_r and ok_c and ok_f)
    if None in (ok_c, ok_f):
        return None, 'a vector was zero-length: see above'
    return ok, 'exact [V]' if 'APPROX' not in how else 'button origin approximated [I]'


# ---------- generic button system 0x1B5F6FC -> 0x1B5AB20 (per button row) ----------
FLAGMAN_G = 0x5B44EB8    # CSEventFlagMan (GOT 0x59E0B48), byte +0x228 = flags usable, +0x218 = group table [V 0x1B5AD6C]


def event_flag(w, fid):
    """Exact 0xC1BF60(mgr, id, 0) + the bit test of 0x1B5ADA0 for ids < 100,000,000 (group digit 0) [V].
    Returns (state, text): state True/False, or None when the game would not test (no mgr, +0x228 = 0, block null)."""
    mgr = w.g(FLAGMAN_G)
    if not mgr:
        return None, 'flag manager *(main+0x%X) null -> not tested' % FLAGMAN_G
    if not w.b(mgr + 0x228):
        return None, 'flag manager +0x228 = 0 -> not tested (0x1B5AD80)'
    if fid < 0 or fid >= 100000000:
        return None, 'id %d outside the decoded range (group digit != 0 path 0xC1C05C not replayed) [??]' % fid
    area = (fid // 10000) % 100
    if area >= 10:
        return None, 'id %d: area %d >= 10 -> 0xC1C020 returns null -> not tested' % (fid, area)
    tbl = w.q(mgr + 0x218)
    ent = w.q(tbl) if tbl else None                   # group 0 -> [+0x218] + 0*0x18
    if not ent:
        return None, 'group 0 table [mgr+0x218] null -> not tested'
    blk = ent + area * 0xA8 + ((fid // 1000) % 10) * 0x10
    bits = w.q(blk)
    r = fid % 1000
    wd = w.d(bits + (r >> 5) * 4) if bits else None
    if wd is None:
        return None, 'block %s bits %s unreadable [??]' % (w.rel(blk), w.rel(bits))
    on = bool((wd >> (31 - (r & 31))) & 1)
    return on, 'flag %d = %s (block %s word +0x%X bit %d)' % (fid, 'ON' if on else 'OFF', w.rel(blk), (r >> 5) * 4,
                                                              31 - (r & 31))


def generic_button(w, row, chr_):
    """The row-specific tests of 0x1B5AB20 (called by 0x1B5F6FC for every prompt) [V]. The par-state / menu / ride
    tests in the same function are the same for every button (the kin circle and pillar prompts pass them)."""
    inv, gray = w.i(row + 0x34), w.i(row + 0x38)
    if inv is not None and inv != -1:
        st, txt = event_flag(w, inv)
        out(None if st is None else (not st), '0x1B5ADC8', 'ActionButtonParam +0x34 invalid flag must be OFF', txt)
    else:
        out(True, '0x1B5ADC8', 'ActionButtonParam +0x34 invalid flag', 'none (%s)' % inv)
    idx = w.b(row + 0x44)
    m0 = w.q((w.q(chr_ + 0x2470) or 0)) if chr_ else None
    if m0 and idx is not None:
        v = w.q(m0 + ((idx >> 3) & 0x18) + 0x38)
        ok = None if v is None else bool((v >> (idx & 63)) & 1)
        out(ok, '0x1B5AE08', 'chr state bit row+0x44 set in [[chr+0x2470]]+0x38',
            'bit %d of %s = %s' % (idx, '%016x' % v if v is not None else None, ok))
    else:
        out(True, '0x1B5ADE4', 'chr state bit row+0x44', '[[chr+0x2470]] null -> not tested')
    b2d = w.b(row + 0x2D)
    out(True if b2d != 1 else None, '0x1B5AE58', 'row+0x2D == 1 -> extra ray test 0x15F0B40',
        '+0x2D = %s (%s)' % (b2d, 'no ray test' if b2d != 1 else 'line-of-sight ray from the camera, not replayed [??]'))
    st, txt = event_flag(w, gray) if gray is not None and gray != -1 else (False, 'none')
    out('i', '0x1B5AFD4', 'grayout flag +0x38 (only greys the prompt)', txt)
    offs = (w.f(row + 0x60), w.f(row + 0x64), w.f(row + 0x68))
    out('i', '0x1B5B1A0', 'on screen', 'a NEW prompt is dropped when 0x1B5F6FC found its point off screen (req+0x34): '
        'look at the button point (dummy poly world + row+0x60..0x68 %s)' % fmt3(None if None in offs else offs))


# ---------- (A) kin circle: 0x11A22E0 ----------
def circle(w, asset):
    par, wcm = w.g(PAR_G), w.g(WCM_G)
    chr_ = w.q(wcm + 0x1A8) if wcm else None
    out(bool(par), '0x11A231C', 'par *(main+0x5B3CDF8) non-null', w.rel(par))
    out(bool(chr_), '0x11A2334', 'local player chr [WCM+0x1A8]', w.rel(chr_))
    info = w.q(asset + 0x10)
    if not info or not chr_:
        out(False, '-', 'asset info [geom+0x10]', w.rel(info))
        return
    param = w.q(info + 0x20)
    aid = w.i(info + 0x18)
    k304 = w.b(info + 0x304)
    kind = k304 if k304 else (w.b(param + 0x128) if param else None)
    out('i', '-', 'asset', 'id %s type +0x306 %s holder +0x460 %s pos %s' % (
        aid % 10000000 if aid is not None else None, w.b(info + 0x306), w.i(info + 0x460), fmt3(w.geom_pos(asset))))
    pm = w.g(PROCMGR_G)
    proc = w.q(pm + 8 + kind * 8) if pm and kind is not None and kind <= 14 else None
    pvt = w.q(proc) if proc else None
    out(bool(proc) and pvt == w.base + BUDDY_PROC_VT, '0x11A259C', 'kind -> processor [*(main+0x5B3D620)+8+k*8]',
        'kind %s (info+0x304 %s) proc %s vt %s (want main+0x%X)' % (kind, k304, w.rel(proc), w.rel(pvt), BUDDY_PROC_VT))
    # registration: asset must be in a loaded block's list block+0x388+kind*0x20
    found = None
    gm = w.g(GEOM_G)
    if gm and kind is not None and kind <= 14:
        for bid, bg in w.map_items(gm + 0x18, 512):
            if not bg or not w.b(bg + 0xB8):
                continue
            beg, end = w.q(bg + 0x388 + kind * 0x20), w.q(bg + 0x390 + kind * 0x20)
            if beg and end and beg < end <= beg + 8 * 65536:
                raw = w.big(beg, end - beg) or b''
                if struct.pack('<Q', asset) in [raw[j:j + 8] for j in range(0, len(raw), 8)]:
                    found = (bid, (end - beg) // 8)
                    break
    out(found is not None, '0x11A25E4', 'asset listed in block+0x388+kind*0x20',
        'block %s (%s assets of this kind)' % found if found else 'not in any loaded block list -> driver never sees it')
    out(bool(param) and w.b(param + 0xD) != 1, '0x11A25FC', 'enabled: [info+0x20] non-null, +0xD != 1',
        'param %s +0xD %s' % (w.rel(param), w.b(param + 0xD) if param else None))
    ok, vals = chain126(w, asset)
    out(ok, '0x11A2624', 'asset+0x126 bits 0|1 set (asset + parents)', vals)
    cd, p, pno = player_data(w, chr_)
    ok, det = busy(w, info, p)
    out(ok, '0x11A2690', 'not busy: info+0x468 slot bit / info+0x470', det)
    # slot 0 = 0x119EE00
    typ = w.b(info + 0x306)
    out(bool(typ), '0x119EE20', 'slot0: circle type info+0x306 != 0', 'type %s' % typ)
    bsf = pfile(w, P_BUDDYSPECIES)
    rows = [(i, a) for i, a in prows(w, bsf) if (w.b(a + 0xC) or 0) & 1 and w.b(a + 0xD) == typ]
    mis = w.g(MISSION_G)
    ecr = prows(w, pfile(w, P_ENEMYCOMMON))
    ec = ecr[0][1] if ecr else None              # single-row param (0x155A140 reads row 0)
    lim = w._u(ec + 0x18C, '<b', 1) if ec else None
    out(bool(rows) if bsf else None, '0xD7F554', 'slot0 (a): BuddySpeciesParam rows +0xC bit0, +0xD == type',
        'rows %s; mission id %s (fixed species not evaluated); max holders EnemyCommonParam+0x18C = %s; '
        'held-kin exclusion not evaluated [I]' % ([i for i, _ in rows], w.i(mis + 0xB8) if mis else None, lim))
    bm0 = w.q(wcm + 0x5B8)
    bm = w.q(bm0 + 0x10) if bm0 else None
    out('i', '0x119EE88', 'player no [[chr+0x20]+0x1D0 or default]+0xD0',
        'pno %s (+0x1D0 %s, default %s) BM %s count +0x20 %s' % (pno, w.rel(p), w.rel(w.g(DEFPLAYER_G)), w.rel(bm),
                                                                w.d(bm + 0x20) if bm else None))
    if not bm:
        out(False, '0x119EE6C', 'BM [[WCM+0x5B8]+0x10] readable', 'null')
        return
    l30 = std_list(w, bm + 0x30)
    hit30 = [n for n in l30 if w.i((w.q((w.q(n + 0x10) or 0) + 0x20) or 0) + 0xB8) == pno]
    out(not hit30, '0x119EEAC', 'slot0 (b): no BM+0x30 entry with [[e]+0x20]+0xB8 == pno',
        '%d entries, %d match' % (len(l30), len(hit30)))
    l10 = std_list(w, bm + 0x10)
    node = None
    for n in l10:
        if w.i((w.q((w.q(n + 0x10) or 0) + 0x20) or 0) + 0xB8) == pno:
            node = n
    drama = w.q(node + 0x38) if node else None
    out(not node or not drama, '0x119EF14', 'slot0 (c): own BM+0x10 node absent or its +0x28 null',
        '%d nodes, own node %s, contract drama [node+0x38] %s' % (len(l10), w.rel(node), w.rel(drama)))
    # slot 0x10 = 0x119F440: button row
    use338 = bool(node and w.q(node + 0x10))
    row = w.q(info + 0x340) if use338 else None
    src = 'info+0x338/+0x340 (has kin)' if use338 else 'info+0x320/+0x328'
    if not row:
        row = w.q(info + 0x328)
        btn = w.i(info + 0x324)
        if use338:
            src += ' -> null, fallback info+0x328'
    else:
        btn = w.i(info + 0x33C)
    out(bool(row), '0x11A26FC', 'button row non-null (slot 0x10)', '%s: button %s row %s' % (src, btn, w.rel(row)))
    if not row:
        return
    ctype = w.i(cd + 0x18) if cd else None
    b47 = w.b(row + 0x47)
    out(not (ctype is not None and 0x14 <= ctype <= 0x18 and b47 > 1), '0x11A271C',
        'chr type 0x14..0x18 needs button row+0x47 <= 1', 'chr type [[chr+0x20]+0x18] %s row+0x47 %s' % (ctype, b47))
    out(bool(w.g(BTNMGR_G)), '0x11A2768', 'action-button manager *(main+0x5B45728)', w.rel(w.g(BTNMGR_G)))
    ok, det = range_test(w, row, asset, chr_)
    out(ok, '0x11A2838', 'range 0x1B5DB10 (0x1B5DCB8 result is ignored)', det)
    generic_button(w, row, chr_)
    out(None, '0x11A28E8', '0x1B5F6FC shows the button, 1 on press', 'generic button system (works for pillars)')


# ---------- (B) asset-access entry (bell): 0xD685C0 -> 0xD66EC0 ----------
def bell(w, n):
    import levers
    mgr, m3, par = w.g(AAE_G), w.g(MGR3_G), w.g(PAR_G)
    out(bool(mgr), '0x182F2F8', 'CSAssetAccessEventMan *(main+0x5B59B60)', w.rel(mgr))
    out(bool(m3), '0xD685EC', 'session manager *(main+0x5B3CE08)', w.rel(m3))
    out(bool(par), '0xD687AC', 'par non-null', w.rel(par))
    c3388 = w.q(par + 0x3388) if par else None
    out(not c3388, '0xD687B8', 'par+0x3388 == 0 (else no prompt loop at all)', w.rel(c3388))
    rows = levers.entries(w)
    r = next((x for x in rows if x['n'] == n), None)
    if not r:
        out(False, '-', 'entry %d exists' % n, '%d entries' % len(rows))
        return
    e = r['e']
    out('i', '-', 'entry', '#%d at %s param %s idx %s h %s h2 %s mediated %s +0x10 %s +0x11 %s' % (
        n, w.rel(e), r['param'], r['index'], '%x' % r['h'] if r['h'] is not None else None,
        '%x' % r['h2'] if r['h2'] is not None else None, r['mediated'], w.b(e + 0x10), w.b(e + 0x11)))
    wcm = w.g(WCM_G)
    chr_ = w.q(wcm + 0x1A8) if wcm else None
    out(bool(chr_), '0xD66F2C', 'local player chr [WCM+0x1A8]', w.rel(chr_))
    g = r['geom']
    out(bool(g), '0xD66F10', 'trigger geom from entry+0x18 handle (0xFEC520)', '%s pos %s' % (w.rel(g), fmt3(r['pos'])))
    if not g or not chr_:
        return
    info = w.q(g + 0x10)
    prm = w.q(info + 0x20) if info else None
    out(bool(prm) and w.b(prm + 0xD) != 1, '0xD66F2C', 'enabled: [info+0x20] non-null, +0xD != 1',
        'param %s +0xD %s' % (w.rel(prm), w.b(prm + 0xD) if prm else None))
    ok1, v1 = chain126(w, g)
    g2 = r['geom2']
    if r['h2'] is not None and r['h2'] != 0xFFFFFFFF and g2:
        ok2, v2 = chain126(w, g2)
        out(ok1 and ok2, '0xD66FA8', 'geom+0x126 and geom2+0x126 bits 0|1 set',
            'trigger %s | geom2 %s %s pos %s' % (v1, w.rel(g2), v2, fmt3(r['pos2'])))
    else:
        out(ok1, '0xD66FB0', 'geom+0x126 bits 0|1 set (geom2 absent: ignored)',
            'trigger %s | h2 %s -> %s' % (v1, r['h2'], w.rel(g2)))
    # usable 0xD67A00: every condition vt+0x50 must return false
    cb, ce = w.q(e + 0x48), w.q(e + 0x50)
    conds = []
    if cb and ce and cb <= ce <= cb + 8 * 64:
        raw = w.rd(cb, ce - cb) if ce > cb else b''
        conds = [struct.unpack_from('<Q', raw, j)[0] for j in range(0, len(raw or b''), 8)]
    usable = True
    if not conds:
        out(True, '0xD66FC4', 'usable 0xD67A00: no condition objects', 'entry+0x48 vector empty -> always usable')
    for c in conds:
        vt = w.q(c)
        if vt == w.base + ENV_COND_VT:
            gdm = w.g(GDM_G)
            o = w.q(gdm + 0x68) if gdm else None
            vb, ve = (w.q(o + 0x58), w.q(o + 0x60)) if o else (None, None)
            hist = []
            if vb and ve and vb <= ve <= vb + 4 * 64:
                raw = w.rd(vb, ve - vb) if ve > vb else b''
                hist = list(struct.unpack('<%di' % ((ve - vb) // 4), raw)) if raw else []
            cur = hist[-1] if hist else None
            erow = prow(w, P_ENVEVENT, cur) if cur is not None and cur >= 0 else None
            et = w.b(erow + 0xF) if erow else None
            blocked = et != 0x26
            usable = usable and not blocked
            out(not blocked, '0xD6A954', 'env condition: current env event type == 0x26',
                'history [*(main+0x5B57EB8)+0x68]+0x58 = %s, current %s, EnvEventParam row %s type %s' % (
                    hist, cur, w.rel(erow), '0x%X' % et if et is not None else None))
        else:
            fn = w.q(vt + 0x50) if vt else None
            usable = False
            out(None, '0xD67A2C', 'unknown condition object', 'obj %s vt %s vt+0x50 %s' % (w.rel(c), w.rel(vt), w.rel(fn)))
    seq = w.q(e + 0x40)
    svt = w.q(seq) if seq else None
    st = w.i(seq + 0x50) if seq else None
    out(not seq or (st is not None and st != 1 and st <= 1), '0xD66FE0', 'sequence state [entry+0x40]+0x50 not 1 and <= 1',
        'seq %s vt %s (want main+0x%X) state %s next +0x54 %s' % (w.rel(seq), w.rel(svt), SEQ_VT, st,
                                                                 w.i(seq + 0x54) if seq else None))
    hold = w.i(info + 0x460)
    out(hold == -1, '0xD66FF0', 'holder info+0x460 == -1', str(hold))
    cd, p, pno = player_data(w, chr_)
    ok, det = busy(w, info, p)
    out(ok, '0xD67074', 'not busy: info+0x468 slot bit / info+0x470', det + ' (pno %s)' % pno)
    arow = prow(w, P_AAE, r['param'])
    btn = w.i(arow) if arow else -1
    out(bool(arow), '0xD67098', 'AssetAccessEventParam row (entry+0xC)', '%s: row %s button +0x0 = %s' % (
        r['param'], w.rel(arow), btn))
    brow = prow(w, P_ACTIONBUTTON, btn) if btn is not None and btn >= 0 else None
    out(bool(brow), '0xD670D0', 'ActionButtonParam row exists', '%s -> %s' % (btn, w.rel(brow)))
    if not brow:
        return
    ctype = w.i(cd + 0x18) if cd else None
    b47 = w.b(brow + 0x47)
    out(not (ctype is not None and 0x14 <= ctype <= 0x18 and b47 >= 2), '0xD670E0',
        '0x1B5CB94: chr type 0x14..0x18 needs row+0x47 < 2', 'chr type %s row+0x47 %s' % (ctype, b47))
    out('i', '-', 'map data (m10_00_00_00.msb event 614, type 30)',
        'record {9005, +8 part 1804 AEG105_310 = the bell (142.5, 171.7, 92.9) -> entry+0x14, +0xC part 1805 '
        'AEG105_312 = trigger (147.5, 133.7, 101.6) -> entry+0x18, +0x30 = 1 env condition}; AEG105_312.flver dummy 170 '
        '= (0, 1.0, 0) on bone 3 "DummyPoly" (root, identity) -> button point 1 m above the trigger origin')
    ok, det = range_test(w, brow, g, chr_)
    out(ok, '0xD67150', 'range 0x1B5F2B4 -> 0x1B5DB10', det)
    generic_button(w, brow, chr_)
    out(None, '0xD671DC', '0x1B5F6FC shows the button, 1 on press', 'generic button system')
    out('i', '0xD6722C', 'after a press', 'mediated %s -> %s' % (
        r['mediated'], 'send 0x97 via 0xD68E80 (kind 0)' if r['mediated'] else 'local 0xD672E0 kind 1'))
    # reward state: entry vt+0x48 0xD67A80 -> cond vt+0x28 (cond+8 = holder, pending {pno, timer}) ; vt+0x18 0xD6A464
    # (gate +0xBDA @0xD6A48C) -> par+0x2C0 0xF0EA78 (gate mode 6 @0xF0EAAC) -> 0xF0EBC0: Virtue counter 120000 when
    # AS+8 == 0x26; 0xD6A0A0 SpEffect 102130 + notice 10011302 after EnvEventTypeParam+0x138 s [V]
    for c in conds:
        if w.q(c) == w.base + ENV_COND_VT:
            pb, pe = w.q(c + 0x10), w.q(c + 0x18)
            n = (pe - pb) // 0x20 if pb and pe and pe >= pb else None
            out('i', '0xD6A6C0', 'reward state (condition object)', 'cond+8 pending grant pno %s, %s SpEffect records' % (
                w.i(c + 8), n))
    asup = w.q(par + 0x2C0) if par else None
    out('i', '0xD6A5C4', 'support object par+0x2C0 (bell Virtue needs +8 == 0x26)', '%s +8 = %s' % (
        w.rel(asup), '0x%X' % w.b(asup + 8) if asup and w.b(asup + 8) is not None else None))


def main():
    w = W(sys.argv[1])
    what = sys.argv[2] if len(sys.argv) > 2 else ''
    print('%s: base 0x%x, offline flag +0xBDA = %s' % (w.who, w.base, w.b((w.g(0x5B65C20) or 0) + 0xBDA)))
    if what == 'circle' and len(sys.argv) > 3:
        circle(w, int(sys.argv[3], 16))
    elif what == 'bell':
        bell(w, int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    else:
        print(__doc__)
        return
    print('first failing check: %s' % ('%s %s' % first_fail[0] if first_fail[0] else 'none (see ?? lines)'))
    w.report_missing()


if __name__ == '__main__':
    main()
