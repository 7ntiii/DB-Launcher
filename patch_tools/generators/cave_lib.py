"""cave_lib: shared helpers for patch generators (*_gen.py -> *_live.py). Static only: reads nso/*.bin,
patch_manager.cpp, every *_live.py under diag/, and cave_registry.md; writes cave_registry.md (claims) and,
when asked, your *_live.py. Usage notes and a worked example: cave_lib_notes.md.

    python cave_lib.py      -> self-test of every encoder against capstone, registry + pool report,
                               and a scan for old references into the NEAR_TRAMP pool.

Memory map (offsets from main):
  text            0x0000000..0x492AD90
  ro              0x492B000..  (file ends 0x563E45C, zero padding up to 0x563EFFF)
  NEAR_TRAMP pool 0x563EE00..0x563F000  ro padding, 128 words, b/bl reach it from ALL text. Trampolines only.
  data/bss        0x563F000..0x6B30000
  FAR_CODE pool   0xC500000..0xC50F000  cave region (read-only pages the JIT executes). b/bl reach it only from
                                        text >= 0x4510000, so most hooks go through a NEAR_TRAMP trampoline.
  FAR_DATA pool   0xC50F000..0xC510000  cave region data page (assist-written data; 0x000..0x200 = MAP inbox).

Records are tuples (offset_from_main, orig_hex, new_hex, is_code), bytes little-endian as in memory.
Cave records (near or far) have orig "00000000". FAR records (offset >= 0xC500000) are cave records that
patch_manager.cpp only accepts as BuiltinPatchRecord{off, NAME, {}, true} (executable_padding, EMPTY original):
tools/add_dusk_records.py does NOT emit that form yet - see cpp_rows() and the notes.

Registers are ints (0..30, 31 = sp/zr depending on the instruction) or names 'x16', 'w8', 'sp', 'xzr', 'wzr'.
"""
import glob
import os
import re
import struct

import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
NSO = os.path.join(HERE, 'nso')
REGISTRY = os.path.join(HERE, 'cave_registry.md')
PM = os.path.join(HERE, '..', '..', 'src', 'lichii', 'src', 'core', 'file_sys', 'patch_manager.cpp')

TXT = open(os.path.join(NSO, 'main_text.bin'), 'rb').read()
RO = open(os.path.join(NSO, 'main_ro.bin'), 'rb').read()
DATA = open(os.path.join(NSO, 'main_data.bin'), 'rb').read()
TEXT_END = 0x492AD90
RO_BASE = 0x492B000
RO_FILE_END = 0x563E45C
DATA_BASE = 0x563F000
FAR_LO, FAR_HI = 0xC500000, 0xC510000

# name -> (lo, hi exclusive, kind). 'code' pools get cave() words, 'data' pools get data only.
POOLS = {
    'NEAR_TRAMP': (0x563EE00, 0x563F000, 'code'),
    'FAR_CODE': (0xC500000, 0xC50F000, 'code'),
    'FAR_DATA': (0xC50F000, 0xC510000, 'data'),
}

md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)


def is_far(off):
    """True for an address in the cave region (records there need the far C++ form)."""
    return FAR_LO <= off < FAR_HI


# ====================================================================== registers
def R(r):
    """'x16' / 'w8' / 'sp' / 'xzr' / 'wzr' / 16 -> register number."""
    if isinstance(r, int):
        assert 0 <= r <= 31, r
        return r
    r = r.lower()
    if r in ('sp', 'xzr', 'wzr'):
        return 31
    assert r[0] in 'xw' and r[1:].isdigit() and int(r[1:]) <= 30, 'bad register %r' % r
    return int(r[1:])


# ====================================================================== encoders (range-checked)
def _rel(pc, t, bits):
    d = t - pc
    assert d % 4 == 0, 'unaligned branch %x -> %x' % (pc, t)
    d //= 4
    assert -(1 << (bits - 1)) <= d < (1 << (bits - 1)), 'branch out of range %x -> %x (%d bits)' % (pc, t, bits)
    return d & ((1 << bits) - 1)


def _imm(v, bits, what):
    assert 0 <= v < (1 << bits), '%s immediate %#x out of range' % (what, v)
    return v


def _scaled(off, size, what):
    assert off % size == 0, '%s offset %#x not a multiple of %d' % (what, off, size)
    return _imm(off // size, 12, what)


COND = {'eq': 0, 'ne': 1, 'hs': 2, 'cs': 2, 'lo': 3, 'cc': 3, 'mi': 4, 'pl': 5, 'vs': 6, 'vc': 7,
        'hi': 8, 'ls': 9, 'ge': 10, 'lt': 11, 'gt': 12, 'le': 13, 'al': 14}
NOP = 0xD503201F
RET = 0xD65F03C0


def reach(pc, t, bits=26):
    """True if a branch with a `bits`-bit word offset at pc reaches t."""
    d = (t - pc) // 4
    return -(1 << (bits - 1)) <= d < (1 << (bits - 1))


def b(pc, t): return 0x14000000 | _rel(pc, t, 26)
def bl(pc, t): return 0x94000000 | _rel(pc, t, 26)
def bcond(pc, cond, t): return 0x54000000 | (_rel(pc, t, 19) << 5) | (COND[cond] if isinstance(cond, str) else cond)
def beq(pc, t): return bcond(pc, 'eq', t)
def bne(pc, t): return bcond(pc, 'ne', t)
def bhs(pc, t): return bcond(pc, 'hs', t)
def blo(pc, t): return bcond(pc, 'lo', t)
def cbz_w(pc, rt, t): return 0x34000000 | (_rel(pc, t, 19) << 5) | R(rt)
def cbnz_w(pc, rt, t): return 0x35000000 | (_rel(pc, t, 19) << 5) | R(rt)
def cbz_x(pc, rt, t): return 0xB4000000 | (_rel(pc, t, 19) << 5) | R(rt)
def cbnz_x(pc, rt, t): return 0xB5000000 | (_rel(pc, t, 19) << 5) | R(rt)


def tbz(pc, rt, bit, t):
    assert 0 <= bit < 64
    return 0x36000000 | ((bit >> 5) << 31) | ((bit & 31) << 19) | (_rel(pc, t, 14) << 5) | R(rt)


def tbnz(pc, rt, bit, t): return tbz(pc, rt, bit, t) | 0x01000000


def br(rn): return 0xD61F0000 | (R(rn) << 5)
def blr(rn): return 0xD63F0000 | (R(rn) << 5)


def adrp(pc, rd, t):
    p = (t >> 12) - (pc >> 12)
    assert -(1 << 20) <= p < (1 << 20), 'adrp out of range'
    return 0x90000000 | ((p & 3) << 29) | (((p >> 2) & 0x7FFFF) << 5) | R(rd)


def adr(pc, rd, t):
    d = t - pc
    assert -(1 << 20) <= d < (1 << 20), 'adr out of range'
    d &= 0x1FFFFF
    return 0x10000000 | ((d & 3) << 29) | ((d >> 2) << 5) | R(rd)


def lo12(t): return t & 0xFFF


def add_xi(rd, rn, imm, lsl12=False): return 0x91000000 | (lsl12 << 22) | (_imm(imm, 12, 'add') << 10) | (R(rn) << 5) | R(rd)
def sub_xi(rd, rn, imm, lsl12=False): return 0xD1000000 | (lsl12 << 22) | (_imm(imm, 12, 'sub') << 10) | (R(rn) << 5) | R(rd)
def add_wi(rd, rn, imm): return 0x11000000 | (_imm(imm, 12, 'add') << 10) | (R(rn) << 5) | R(rd)
def sub_wi(rd, rn, imm): return 0x51000000 | (_imm(imm, 12, 'sub') << 10) | (R(rn) << 5) | R(rd)
def add_xr(rd, rn, rm): return 0x8B000000 | (R(rm) << 16) | (R(rn) << 5) | R(rd)
def add_wr(rd, rn, rm): return 0x0B000000 | (R(rm) << 16) | (R(rn) << 5) | R(rd)
def cmp_wi(rn, imm): return 0x7100001F | (_imm(imm, 12, 'cmp') << 10) | (R(rn) << 5)
def cmp_xi(rn, imm): return 0xF100001F | (_imm(imm, 12, 'cmp') << 10) | (R(rn) << 5)
def cmp_wr(rn, rm): return 0x6B00001F | (R(rm) << 16) | (R(rn) << 5)
def cmp_xr(rn, rm): return 0xEB00001F | (R(rm) << 16) | (R(rn) << 5)
def mov_x(rd, rm): return 0xAA0003E0 | (R(rm) << 16) | R(rd)          # orr xd, xzr, xm (not for sp)
def mov_w(rd, rm): return 0x2A0003E0 | (R(rm) << 16) | R(rd)
def mov_sp(rd, rn): return add_xi(rd, rn, 0)                          # mov to/from sp
def movz_w(rd, imm, hw=0): return 0x52800000 | (hw << 21) | (_imm(imm, 16, 'movz') << 5) | R(rd)
def movz_x(rd, imm, hw=0): return 0xD2800000 | (hw << 21) | (_imm(imm, 16, 'movz') << 5) | R(rd)
def movk_w(rd, imm, hw=0): return 0x72800000 | (hw << 21) | (_imm(imm, 16, 'movk') << 5) | R(rd)
def movk_x(rd, imm, hw=0): return 0xF2800000 | (hw << 21) | (_imm(imm, 16, 'movk') << 5) | R(rd)
def and_ff(rd, rn): return 0x12001C00 | (R(rn) << 5) | R(rd)          # and wd, wn, #0xff

# loads / stores, unsigned scaled offset
def ldr_x(rt, rn, off=0): return 0xF9400000 | (_scaled(off, 8, 'ldr x') << 10) | (R(rn) << 5) | R(rt)
def str_x(rt, rn, off=0): return 0xF9000000 | (_scaled(off, 8, 'str x') << 10) | (R(rn) << 5) | R(rt)
def ldr_w(rt, rn, off=0): return 0xB9400000 | (_scaled(off, 4, 'ldr w') << 10) | (R(rn) << 5) | R(rt)
def str_w(rt, rn, off=0): return 0xB9000000 | (_scaled(off, 4, 'str w') << 10) | (R(rn) << 5) | R(rt)
def ldrh(rt, rn, off=0): return 0x79400000 | (_scaled(off, 2, 'ldrh') << 10) | (R(rn) << 5) | R(rt)
def strh(rt, rn, off=0): return 0x79000000 | (_scaled(off, 2, 'strh') << 10) | (R(rn) << 5) | R(rt)
def ldrb(rt, rn, off=0): return 0x39400000 | (_imm(off, 12, 'ldrb') << 10) | (R(rn) << 5) | R(rt)
def strb(rt, rn, off=0): return 0x39000000 | (_imm(off, 12, 'strb') << 10) | (R(rn) << 5) | R(rt)


def _simm9(off):
    assert -256 <= off < 256, 'unscaled offset %d out of range' % off
    return off & 0x1FF


def ldur_w(rt, rn, off): return 0xB8400000 | (_simm9(off) << 12) | (R(rn) << 5) | R(rt)
def stur_w(rt, rn, off): return 0xB8000000 | (_simm9(off) << 12) | (R(rn) << 5) | R(rt)
def ldur_x(rt, rn, off): return 0xF8400000 | (_simm9(off) << 12) | (R(rn) << 5) | R(rt)
def stur_x(rt, rn, off): return 0xF8000000 | (_simm9(off) << 12) | (R(rn) << 5) | R(rt)


def _simm7x(off):
    assert off % 8 == 0 and -512 <= off < 512, 'pair offset %d out of range' % off
    return (off // 8) & 0x7F


# 64-bit pairs: off = signed offset; pre = [rn, #off]!, post = [rn], #off
def stp_x(rt, rt2, rn, off=0): return 0xA9000000 | (_simm7x(off) << 15) | (R(rt2) << 10) | (R(rn) << 5) | R(rt)
def ldp_x(rt, rt2, rn, off=0): return 0xA9400000 | (_simm7x(off) << 15) | (R(rt2) << 10) | (R(rn) << 5) | R(rt)
def stp_pre(rt, rt2, rn, off): return 0xA9800000 | (_simm7x(off) << 15) | (R(rt2) << 10) | (R(rn) << 5) | R(rt)
def ldp_pre(rt, rt2, rn, off): return 0xA9C00000 | (_simm7x(off) << 15) | (R(rt2) << 10) | (R(rn) << 5) | R(rt)
def ldp_post(rt, rt2, rn, off): return 0xA8C00000 | (_simm7x(off) << 15) | (R(rt2) << 10) | (R(rn) << 5) | R(rt)
stp_off = stp_x   # names used by older generators


# ====================================================================== words / text
def hexw(w):
    return struct.pack('<I', w).hex().upper()


def text_word(off):
    assert 0 <= off < TEXT_END, 'not in text: %x' % off
    return struct.unpack_from('<I', TXT, off)[0]


def dis1(addr, w):
    """Capstone text of one word ('mnemonic op_str'); asserts it decodes."""
    ins = list(md.disasm(struct.pack('<I', w), addr))
    assert len(ins) == 1, 'undecodable %08x at %x' % (w, addr)
    return ins[0].mnemonic + (' ' + ins[0].op_str if ins[0].op_str else '')


def image_is_zero(a, n=4):
    """True if main's file image has zero bytes at a..a+n (ro tail padding and the cave region count as zero)."""
    if is_far(a):
        return True
    if RO_BASE <= a < DATA_BASE:
        return RO[a - RO_BASE:a - RO_BASE + n].strip(b'\0') == b''
    return False


# ====================================================================== shipped + other live records
def _shipped():
    src = open(PM, encoding='utf-8', errors='ignore').read()
    arrays = {}
    for m in re.finditer(r'constexpr\s+std::array<u8,\s*(\d+)>\s+(\w+)\s*\{([^}]*)\}', src):
        n, name, body = int(m.group(1)), m.group(2), m.group(3)
        vals = [int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{1,2})\b', body)]
        arrays[name] = bytes(vals) + b'\0' * (n - len(vals))
    out = {}
    for m in re.finditer(r'BuiltinPatchRecord\{\s*0x([0-9A-Fa-f]+),\s*(\w+)', src):
        a, name = int(m.group(1), 16), m.group(2)
        for i, bt in enumerate(arrays.get(name, b'')):
            out[a + i] = bt
    return out


SHIPPED = _shipped()   # byte address -> byte, every BuiltinPatchRecord in patch_manager.cpp


def live_records(exclude=()):
    """byte address -> file name, for every record in diag/**/*_live.py except the given basenames."""
    out = {}
    for f in glob.glob(os.path.join(HERE, '..', '**', '*_live.py'), recursive=True):
        if os.path.basename(f) in exclude:
            continue
        txt = open(f, encoding='utf-8', errors='ignore').read()
        for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"([0-9A-Fa-f]*)"\s*,\s*"([0-9A-Fa-f]*)"', txt):
            a, new = int(m.group(1), 16), m.group(3)
            for i in range(max(len(new) // 2, 4)):
                out[a + i] = os.path.basename(f)
    return out


def shipped_word(a):
    assert all(a + i in SHIPPED for i in range(4)), 'no shipped word at %x' % a
    return struct.unpack('<I', bytes(SHIPPED[a + i] for i in range(4)))[0]


# ====================================================================== registry (cave_registry.md)
# Row format (end EXCLUSIVE):  | owner | tag | 0xLO..0xHI | purpose |
_ROW = re.compile(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*0x([0-9A-Fa-f]+)\s*\.\.\s*0x([0-9A-Fa-f]+)\s*\|\s*(.*?)\s*\|\s*$')


def read_registry():
    """List of dicts {owner, tag, lo, hi, purpose} from cave_registry.md."""
    rows = []
    if os.path.exists(REGISTRY):
        for line in open(REGISTRY, encoding='utf-8'):
            m = _ROW.match(line.strip())
            if m:
                rows.append(dict(owner=m.group(1), tag=m.group(2), lo=int(m.group(3), 16),
                                 hi=int(m.group(4), 16), purpose=m.group(5)))
    for i, r in enumerate(rows):   # the file itself must be consistent
        assert r['lo'] < r['hi'], 'registry row empty: %r' % r
        assert pool_of(r['lo'], r['hi'] - r['lo']), 'registry row outside every pool: %r' % r
        for s in rows[i + 1:]:
            assert r['hi'] <= s['lo'] or s['hi'] <= r['lo'], 'registry overlap: %r / %r' % (r, s)
            assert (r['owner'], r['tag']) != (s['owner'], s['tag']), 'duplicate owner/tag: %r' % r
    return rows


def pool_of(lo, size):
    """Pool name that holds [lo, lo+size) completely, or None."""
    for name, (plo, phi, _) in POOLS.items():
        if plo <= lo and lo + size <= phi:
            return name
    return None


def _append_row(owner, tag, lo, hi, purpose):
    assert '|' not in owner + tag + purpose
    line = '| %s | %s | 0x%X..0x%X | %s |\n' % (owner, tag, lo, hi, purpose)
    with open(REGISTRY, 'a', encoding='utf-8') as f:
        f.write(line)


# ====================================================================== the generator object
class Gen:
    """One per generator run.
    owner : your generator's name (registry 'owner' column), e.g. 'kin_far_gen'.
    out   : basename of the *_live.py you write (excluded from the collision check, it holds your old output).
    dry   : True = allocate without writing cave_registry.md (for experiments / the notes' example)."""

    def __init__(self, owner, out, dry=False):
        self.owner, self.out, self.dry = owner, out, dry
        self.others = live_records(exclude=(out,))
        self.listing = []
        self._dry_rows = []
        refs = pool_refs()
        if refs:   # old MAP caves in patch_manager.cpp still read the NEAR_TRAMP pool as their inbox
            print('WARNING: NEAR_TRAMP pool still referenced (lead: run update_dusk_records.py for mapsys):')
            for h in refs:
                print('  ' + h)

    # ------------------------------------------------------------ collision checks
    def free_bytes(self, a, n=4, what='word'):
        """Assert no shipped record and no other *_live.py record touches a..a+n."""
        for i in range(n):
            assert a + i not in SHIPPED, '%s %x collides with a shipped record (patch_manager.cpp)' % (what, a)
            assert a + i not in self.others, '%s %x collides with %s' % (what, a, self.others[a + i])

    # ------------------------------------------------------------ registry
    def _rows(self):
        return read_registry() + self._dry_rows

    def claim(self, tag, lo, size, purpose):
        """Claim [lo, lo+size) for (owner, tag). Idempotent for the same row; refuses any overlap."""
        hi = lo + size
        pool = pool_of(lo, size)
        assert pool, 'claim %x..%x is not inside one pool' % (lo, hi)
        for r in self._rows():
            if (r['owner'], r['tag']) == (self.owner, tag):
                assert (r['lo'], r['hi']) == (lo, hi), 'tag %s already claims %x..%x' % (tag, r['lo'], r['hi'])
                return lo
            assert hi <= r['lo'] or r['hi'] <= lo, 'claim %x..%x overlaps %s/%s %x..%x' % (
                lo, hi, r['owner'], r['tag'], r['lo'], r['hi'])
        for a in range(lo, hi, 4):
            self.free_bytes(a, 4, 'claim')
            assert image_is_zero(a), 'claim %x: image not zero' % a
        if self.dry:
            self._dry_rows.append(dict(owner=self.owner, tag=tag, lo=lo, hi=hi, purpose=purpose))
        else:
            _append_row(self.owner, tag, lo, hi, purpose)
            print('cave_registry.md: claimed %s/%s 0x%X..0x%X (%s)' % (self.owner, tag, lo, hi, pool))
        return lo

    def alloc(self, tag, pool, size, purpose, align=4):
        """First-fit allocation of `size` bytes in `pool` for (owner, tag). STABLE across re-runs: if the
        registry already has this owner/tag, that range is returned (it must be big enough - to grow it,
        delete your row by hand and re-run). New claims are appended to cave_registry.md."""
        assert size > 0 and size % 4 == 0 and align % 4 == 0
        rows = self._rows()
        for r in rows:
            if (r['owner'], r['tag']) == (self.owner, tag):
                assert r['hi'] - r['lo'] >= size, '%s/%s holds %#x bytes, needs %#x: delete the row and re-run' % (
                    self.owner, tag, r['hi'] - r['lo'], size)
                return r['lo']
        plo, phi, _ = POOLS[pool]
        a = (plo + align - 1) // align * align
        while a + size <= phi:
            clash = [r for r in rows if not (a + size <= r['lo'] or r['hi'] <= a)]
            if clash:
                a = (max(r['hi'] for r in clash) + align - 1) // align * align
                continue
            busy = [x for x in range(a, a + size) if x in SHIPPED or x in self.others or not image_is_zero(x, 1)]
            if busy:
                a = (busy[-1] + 1 + align - 1) // align * align
                continue
            return self.claim(tag, a, size, purpose)
        raise AssertionError('pool %s has no %#x free bytes' % (pool, size))

    def owned(self, a):
        return any(r['owner'] == self.owner and r['lo'] <= a < r['hi'] for r in self._rows())

    # ------------------------------------------------------------ record makers
    def text_patch(self, addr, expect, new, note='', replaces_shipped=False):
        """Word in main text: asserts the stock instruction text (capstone), collision-checked.
        replaces_shipped=True: the word IS a shipped record you are re-pointing (porting a shipped cave);
        orig stays the stock word, the listing shows the shipped word it replaces (lead: update_dusk_records)."""
        old = text_word(addr)
        got = dis1(addr, old)
        assert got == expect, 'at %x: %s, expected %s' % (addr, got, expect)
        if replaces_shipped:
            assert all(addr + i in SHIPPED for i in range(4)), 'replaces_shipped: no shipped word at %x' % addr
            assert all(addr + i not in self.others for i in range(4)), 'text word %x in %s' % (addr, self.others.get(addr))
            note += ' (replaces shipped %s)' % dis1(addr, shipped_word(addr))
        else:
            self.free_bytes(addr, 4, 'text word')
        self.listing.append('  0x%x  %s  ->  %s   %s' % (addr, got, dis1(addr, new), note))
        return (addr, hexw(old), hexw(new), True)

    def cave(self, name, start, words):
        """Cave words at start (must lie in a CODE pool range this owner claimed). words = list of ints or an
        Asm. Returns cave records (orig "00000000"); every word is listed with capstone."""
        if isinstance(words, Asm):
            assert words.pc0 == start
            words = words.words()
        self.listing.append('--- %s cave at 0x%X (%d words)%s' % (name, start, len(words), ' FAR' if is_far(start) else ''))
        recs = []
        for i, w in enumerate(words):
            a = start + i * 4
            pool = pool_of(a, 4)
            assert pool and POOLS[pool][2] == 'code', 'cave word %x not in a code pool' % a
            assert self.owned(a), 'cave word %x not claimed by %s in cave_registry.md' % (a, self.owner)
            assert image_is_zero(a), 'cave not zero at %x' % a
            self.free_bytes(a, 4, 'cave word')
            self.listing.append('  0x%x %s' % (a, dis1(a, w)))
            recs.append((a, '00000000', hexw(w), True))
        return recs

    # ------------------------------------------------------------ far hooks
    def far_hook(self, site, orig_word_text, target, scratch='x16', why=None, link=False, note='',
                 replaces_shipped=False):
        """Hook the text word at `site` (stock text asserted) so it goes to `target` in the cave region.
        link=False: site becomes `b`  (target code must re-run the replaced instruction - see relocate()
                    - and come back with far_return(site + 4)).
        link=True : site becomes `bl` (x30 = site+4 is CLOBBERED; target code ends with `ret`).
        If `target` is in plain-branch reach of `site` (site >= ~0x4510000) the site branches directly and no
        trampoline / scratch is used. Otherwise a 3-word trampoline is allocated in NEAR_TRAMP:
            adrp <scratch>, target ; add <scratch>, <scratch>, #lo12 ; br <scratch>
        `why` is REQUIRED when a trampoline is used: why `scratch` is dead at `site` (written before read on
        every path from the site, or the site is a function entry / right after a bl). It goes into the listing.
        Returns records [trampoline words..., site hook] (hook LAST: apply the far target cave before these)."""
        assert is_far(target) and pool_of(target, 4) == 'FAR_CODE', 'far_hook target %x not in FAR_CODE' % target
        enc = bl if link else b
        if reach(site, target):
            self.listing.append('--- far_hook 0x%X -> 0x%X direct (in reach, no trampoline)' % (site, target))
            return [self.text_patch(site, orig_word_text, enc(site, target), note, replaces_shipped)]
        assert why, 'far_hook %x: say why %s is dead at the site (why=...)' % (site, scratch)
        s = R(scratch)
        if s not in (16, 17):
            self.listing.append('  NOTE scratch %s is not x16/x17' % scratch)
        t = self.alloc('tramp_%X' % site, 'NEAR_TRAMP', 12, 'trampoline %X -> %X via %s' % (site, target, scratch))
        tw = [adrp(t, s, target), add_xi(s, s, lo12(target)), br(s)]
        self.listing.append('  scratch %s at 0x%X: %s' % (scratch, site, why))
        recs = self.cave('tramp_%X' % site, t, tw)
        recs.append(self.text_patch(site, orig_word_text, enc(site, t), note or 'far hook via 0x%X' % t,
                                    replaces_shipped))
        return recs


# ====================================================================== far-code helpers (word lists)
def far_jump(pc, target, scratch='x16'):
    """3 words at pc: adrp/add/br scratch -> target (+-4 GB). Clobbers scratch."""
    s = R(scratch)
    return [adrp(pc, s, target), add_xi(s, s, lo12(target)), br(s)]


def far_return(pc, target, scratch='x16'):
    """Back from far code to text `target`; always 3 words (fixed layout). scratch must be dead at target."""
    return far_jump(pc, target, scratch)


def far_call(pc, target, scratch='x16'):
    """3 words at pc: adrp/add/blr scratch -> call `target` (a text function). Clobbers scratch AND x30:
    save x30 (stp x29, x30, [sp, #-16]!) first if your far code must return through it."""
    s = R(scratch)
    return [adrp(pc, s, target), add_xi(s, s, lo12(target)), blr(s)]


def relocate(site, pc, scratch='x16'):
    """Re-encode the stock text word at `site` so it runs at `pc` (far code) with the same effect.
    Returns a word list: 1 word for position-independent words, adrp re-encoded, b -> far_jump (3 words),
    bl -> far_call (3 words: scratch + x30), b.cond/cbz/cbnz/tbz/tbnz -> inverted short skip over far_jump
    (4 words). adr / ldr literal / prfm literal are refused (do it by hand)."""
    w = text_word(site)
    s = R(scratch)
    if (w & 0x9F000000) == 0x90000000:                    # adrp
        immlo, immhi = (w >> 29) & 3, (w >> 5) & 0x7FFFF
        p = (immhi << 2) | immlo
        if p & (1 << 20):
            p -= 1 << 21
        return [adrp(pc, w & 31, ((site >> 12) + p) << 12)]
    if (w & 0x9F000000) == 0x10000000 or (w & 0x3B000000) == 0x18000000:
        raise AssertionError('relocate %x: adr / literal load %s - do it by hand' % (site, dis1(site, w)))
    if (w & 0x7C000000) == 0x14000000:                    # b / bl
        imm = w & 0x3FFFFFF
        t = site + ((imm - (1 << 26)) if imm & (1 << 25) else imm) * 4
        return far_call(pc, t, s) if w & 0x80000000 else far_jump(pc, t, s)

    def sx(v, bits):
        return v - (1 << bits) if v & (1 << (bits - 1)) else v

    if (w & 0xFF000010) == 0x54000000:                    # b.cond
        cond = w & 15
        assert cond < 14, 'b.al/b.nv at %x' % site
        t = site + sx((w >> 5) & 0x7FFFF, 19) * 4
        inv = (w & ~(0x7FFFF << 5) & ~15) | (cond ^ 1) | (_rel(pc, pc + 16, 19) << 5)
        return [inv] + far_jump(pc + 4, t, s)
    if (w & 0x7E000000) == 0x34000000:                    # cbz / cbnz
        t = site + sx((w >> 5) & 0x7FFFF, 19) * 4
        inv = ((w ^ 0x01000000) & ~(0x7FFFF << 5)) | (_rel(pc, pc + 16, 19) << 5)
        return [inv] + far_jump(pc + 4, t, s)
    if (w & 0x7E000000) == 0x36000000:                    # tbz / tbnz
        t = site + sx((w >> 5) & 0x3FFF, 14) * 4
        inv = ((w ^ 0x01000000) & ~(0x3FFF << 5)) | (_rel(pc, pc + 16, 14) << 5)
        return [inv] + far_jump(pc + 4, t, s)
    return [w]


# ====================================================================== tiny two-pass assembler
class Asm:
    """Build a cave with labels instead of hand-counted offsets.
        a = Asm(start)
        a(cbz_w_to('w8', 'skip'))        # or a(lambda pc, L: cbz_w(pc, 8, L['skip']))
        a(ldr_w(8, 9, 4))                # plain int words
        a.many(lambda pc, L: far_return(pc, 0x11108F0))   # multi-word helpers (fixed length!)
        a.label('skip')
        words = a.words()
    A callable item gets (pc, labels) and returns one word; many() items return a fixed-length list."""

    def __init__(self, pc0):
        self.pc0, self.items, self.labels = pc0, [], {}

    def here(self):
        return self.pc0 + 4 * sum(n for n, _ in self.items)

    def label(self, name):
        assert name not in self.labels, 'label %s twice' % name
        self.labels[name] = self.here()

    def __call__(self, item):
        self.items.append((1, item))
        return self

    def many(self, fn):
        n = len(fn(self.here(), _Any(self.here())))     # probe the length with dummy labels
        self.items.append((n, fn))
        return self

    def words(self):
        out, pc = [], self.pc0
        for n, it in self.items:
            if isinstance(it, int):
                ws = [it]
            else:
                r = it(pc, self.labels)
                ws = r if isinstance(r, list) else [r]
            assert len(ws) == n, 'item at %x changed length' % pc
            out += ws
            pc += 4 * n
        return out


class _Any(dict):
    """Label dict for length probing: every label = the probing pc (always in range; results are discarded)."""
    def __init__(self, pc):
        super().__init__()
        self.pc = pc

    def __missing__(self, k):
        return self.pc


def to(fn, *args):
    """Label-taking shortcut: to(cbz_w, 'w8', 'skip') == lambda pc, L: cbz_w(pc, 'w8', L['skip']).
    The LAST argument is the label name (or an int address)."""
    *regs, lab = args
    return lambda pc, L: fn(pc, *regs, L[lab] if isinstance(lab, str) else lab)


def cbz_w_to(rt, lab): return to(cbz_w, rt, lab)


# ====================================================================== output
def write_live(filename, groups, order, doc):
    """Write diag/net/<filename>: one list per group in `order`, plus ORDER. Asserts no two records overlap.
    Far groups get a comment: they need the far C++ record form."""
    seen = {}
    for g in order:
        for a, o, n, c in groups[g]:
            for i in range(len(n) // 2):
                assert a + i not in seen, 'overlap %x (%s, %s)' % (a + i, g, seen.get(a + i))
                seen[a + i] = g
    out = ['"""' + doc.strip() + '\nCave records: orig "00000000". FAR records (0xC500000..0xC50FFFF) must be built in as',
           'BuiltinPatchRecord{off, NAME, {}, true} (see cave_lib.cpp_rows). Apply caves before hooks."""', '']
    for g in order:
        far = any(is_far(a) for a, *_ in groups[g])
        out.append('%s = [%s' % (g, '  # FAR cave records' if far else ''))
        for a, o, n, c in groups[g]:
            out.append('    (0x%X, "%s", "%s", %s),' % (a, o, n, c))
        out.append(']')
    out += ['', 'ORDER = [%s]' % ', '.join(order)]
    open(os.path.join(HERE, filename), 'w').write('\n'.join(out) + '\n')
    print('%s written' % filename)


def cpp_rows(group_name, recs):
    """C++ declarations + table rows for patch_manager.cpp. Far records get the accepted form
    (executable_padding = true, empty original); others the add_dusk_records.py form."""
    decl, rows = [], []
    for a, o, n, c in recs:
        name = 'DUSK_W_%X' % a
        arr = ', '.join('0x' + n[i:i + 2] for i in range(0, len(n), 2))
        decl.append('// %s (%s)' % (hex(a), group_name))
        decl.append('constexpr std::array<u8, %d> %s{%s};' % (len(n) // 2, name, arr))
        if is_far(a):
            rows.append('    BuiltinPatchRecord{0x%X, %s, {}, true},' % (a, name))
        else:
            oa = ', '.join('0x' + o[i:i + 2] for i in range(0, len(o), 2))
            decl.append('constexpr std::array<u8, %d> %s_ORIGINAL{%s};' % (len(o) // 2, name, oa))
            rows.append('    BuiltinPatchRecord{0x%X, %s, %s_ORIGINAL},' % (a, name, name))
    return '\n'.join(decl), '\n'.join(rows)


# ====================================================================== references into the NEAR_TRAMP pool
def pool_refs(lo=0x563EE00, hi=0x563F000):
    """adrp(page of lo..hi) followed by add/ldr/str whose final address is in [lo, hi), in shipped records
    and in every *_live.py. Finds stale uses of the old MAP inbox. Only checks the word right after the adrp."""
    sources = {'patch_manager.cpp': {}}      # source -> {addr: word}; each source checked on its own
    for a in set(x & ~3 for x in SHIPPED):
        if all(a + i in SHIPPED for i in range(4)):
            sources['patch_manager.cpp'][a] = shipped_word(a)
    for f in glob.glob(os.path.join(HERE, '..', '**', '*_live.py'), recursive=True):
        d = sources.setdefault(os.path.basename(f), {})
        for m in re.finditer(r'\(\s*0x([0-9A-Fa-f]+)\s*,\s*"[0-9A-Fa-f]*"\s*,\s*"([0-9A-Fa-f]{8})"', open(f).read()):
            d[int(m.group(1), 16)] = struct.unpack('<I', bytes.fromhex(m.group(2)))[0]
    hits = []
    for src, words in sources.items():
        hits += _pool_refs_in(src, words, lo, hi)
    return sorted(hits)


def _pool_refs_in(src, words, lo, hi):
    hits = []
    for a, w in words.items():
        if (w & 0x9F000000) != 0x90000000 or (a + 4) not in words:
            continue
        p = (((w >> 5) & 0x7FFFF) << 2) | ((w >> 29) & 3)
        if p & (1 << 20):
            p -= 1 << 21
        page = ((a >> 12) + p) << 12
        if page != (lo & ~0xFFF):
            continue
        n = words[a + 4]
        imm = (n >> 10) & 0xFFF
        if (n & 0xFF800000) == 0x91000000:
            off = imm
        elif (n & 0x3FC00000) in (0x39400000, 0x39000000):     # ldr/str unsigned imm, any size
            off = imm << (n >> 30)
        else:
            continue
        if lo <= page + off < hi:
            hits.append('%s 0x%X: %s ; %s' % (src, a, dis1(a, w), dis1(a + 4, n)))
    return sorted(hits)


# ====================================================================== self-test
def _selftest():
    pc = 0x563EE00
    checks = [
        (b(pc, 0x1110A6C), 'b #0x1110a6c'), (bl(pc, 0x11963CC), 'bl #0x11963cc'),
        (bcond(pc, 'ne', pc + 8), 'b.ne #0x563ee08'), (beq(pc, pc - 4), 'b.eq #0x563edfc'),
        (cbz_w(pc, 'w8', pc + 0x40), 'cbz w8, #0x563ee40'), (cbnz_x(pc, 20, pc + 4), 'cbnz x20, #0x563ee04'),
        (tbz(pc, 10, 8, pc + 8), 'tbz w10, #8, #0x563ee08'), (tbnz(pc, 3, 40, pc + 8), 'tbnz x3, #0x28, #0x563ee08'),
        (adrp(pc, 'x16', 0xC50F000), 'adrp x16, #0xc50f000'), (adr(pc, 1, pc + 0x10), 'adr x1, #0x563ee10'),
        (add_xi(16, 16, 0x123), 'add x16, x16, #0x123'), (sub_xi('sp', 'sp', 0x20), 'sub sp, sp, #0x20'),
        (add_xi(2, 'sp', 0), 'mov x2, sp'), (add_wi(1, 2, 3), 'add w1, w2, #3'),
        (add_xr(10, 9, 8), 'add x10, x9, x8'), (cmp_wi(8, 4), 'cmp w8, #4'), (cmp_xr(1, 2), 'cmp x1, x2'),
        (cmp_wr(8, 9), 'cmp w8, w9'), (mov_x(0, 19), 'mov x0, x19'), (mov_w(1, 2), 'mov w1, w2'),
        (movz_w(9, 1), 'mov w9, #1'), (movk_x(1, 0x1234, 1), 'movk x1, #0x1234, lsl #16'),
        (and_ff(9, 1), 'and w9, w1, #0xff'), (ldr_x(8, 8, 0xDF8), 'ldr x8, [x8, #0xdf8]'),
        (str_x(10, 'sp', 0x10), 'str x10, [sp, #0x10]'), (ldr_w(9, 9, 0x1F8), 'ldr w9, [x9, #0x1f8]'),
        (str_w('wzr', 21), 'str wzr, [x21]'), (ldrh(1, 2, 6), 'ldrh w1, [x2, #6]'), (strh(1, 2, 2), 'strh w1, [x2, #2]'),
        (ldrb(8, 8, 0xFD8), 'ldrb w8, [x8, #0xfd8]'), (strb(9, 19, 0x20), 'strb w9, [x19, #0x20]'),
        (stur_w('wzr', 11, -0x14), 'stur wzr, [x11, #-0x14]'), (ldur_x(1, 2, -8), 'ldur x1, [x2, #-8]'),
        (stp_x(9, 10, 'sp', 0), 'stp x9, x10, [sp]'), (stp_pre(29, 30, 'sp', -16), 'stp x29, x30, [sp, #-0x10]!'),
        (ldp_post(29, 30, 'sp', 16), 'ldp x29, x30, [sp], #0x10'), (ldp_pre(8, 9, 20, 0x28), 'ldp x8, x9, [x20, #0x28]!'),
        (ldp_x(1, 2, 3, 8), 'ldp x1, x2, [x3, #8]'), (br('x16'), 'br x16'), (blr(17), 'blr x17'),
        (RET, 'ret'), (NOP, 'nop'),
    ]
    for w, want in checks:
        got = dis1(pc, w)
        assert got == want, 'encoder: %s != %s' % (got, want)
    # relocate round trips (targets must come out the same)
    assert dis1(0xC500000, relocate(0x11108EC, 0xC500000)[0]) == 'cbnz w20, #0xc500010'
    assert dis1(0xC500004, relocate(0x11108EC, 0xC500000)[1]) == 'adrp x16, #0x1110000'
    assert dis1(0xC500008, relocate(0x11108EC, 0xC500000)[2]) == 'add x16, x16, #0xa6c'
    # two-pass assembler
    a = Asm(0xC500000)
    a(to(cbz_w, 'w8', 'out'))
    a(NOP)
    a.many(lambda p, L: far_return(p, 0x11108F0))
    a.label('out')
    a(RET)
    ws = a.words()
    assert len(ws) == 6 and dis1(0xC500000, ws[0]) == 'cbz w8, #0xc500014', dis1(0xC500000, ws[0])
    print('encoders: %d checks + relocate + Asm OK' % len(checks))


if __name__ == '__main__':
    _selftest()
    rows = read_registry()
    print('registry: %d rows' % len(rows))
    for r in rows:
        print('  %-14s %-22s 0x%X..0x%X  %s' % (r['owner'], r['tag'], r['lo'], r['hi'], r['purpose']))
    others = live_records()
    for name, (lo, hi, kind) in POOLS.items():
        used = sum(min(hi, r['hi']) - max(lo, r['lo']) for r in rows if r['lo'] < hi and lo < r['hi'])
        clash = sorted(set(x & ~3 for x in range(lo, hi) if x in SHIPPED or x in others))
        print('pool %-10s 0x%X..0x%X %-4s claimed %#x of %#x; shipped/live records inside: %s' % (
            name, lo, hi, kind, used, hi - lo, ['%X' % x for x in clash[:8]] or 'none'))
    refs = pool_refs()
    print('adrp references into the old inbox 0x563EE00..0x563EFFF: %s' % (len(refs) or 'none'))
    for h in refs:
        print('  ' + h)
