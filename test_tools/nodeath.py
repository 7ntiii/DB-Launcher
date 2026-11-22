"""TEST ONLY - NEVER SHIP. Keep ONE game's local player from dying (the engine's own "no dead" bit).
python diag/twin/nodeath.py WHO on|off|show [mode=bit|global|both] [force=1]

What it changes (static analysis, diag/net/test_tools_notes.md section 1):
  mod = [[chr+0x2470]+0x18] (the chr's data module; [mod+8] == chr is checked first)
  mode=bit    (default) u16 mod+0x4A0 bit 2 = "no dead" of THIS chr. Read by 0x19BDF34 (is-no-dead), which
              0x19BDD00 (cannot-die) ORs into the min-HP clamp of every HP-decrease event (0xDDF7E8, 0xDE0EB4,
              0x19BC070, ...): the hit still lands, HP stops at 1 instead of 0. The game clears this bit itself
              in 0xEE1AD4 (a chr reset, callers 0xE8045C / 0x17F2A58), so long tests re-assert it (fightfoe does).
  mode=global byte main+0x5B84290 = the debug "player no dead" switch: 0x19BDF34 also returns 1 when it is
              set and chr == [WCM+0x1A8] (this game's own player only). Nothing in the game clears it.
  mode=both   both.
Never touched: bit 1 / bit 4 (no-damage), main+0x5B842C0 (no dead for ALL chrs incl. enemies),
main+0x5B842D4 (all no damage). The player's own attacks are unaffected (the bit only acts on the player's
own HP clamp). Only this game's memory, no code bytes, no network message; 'off' undoes it. Lost on restart.
Run from the workspace root. As a module: state(w), set_nodeath(w, on, mode) -> (before, after) dicts."""
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, 'diag/twin')
from world_lib import W, WCM_G  # noqa: E402

FLAGS_OFF = 0x4A0          # u16 flag word in the chr data module            [V 0xDDF780, 0x19BDF40, 0x19BDD20]
NODEAD_BIT = 1 << 2        # "no dead"                                         [V 0x19BDF44 tbnz #2]
IMMORTAL_BIT = 1 << 0      # event immortality (0xF1DFD4 bfxil), also no-dead  [V 0x19BDD24; not written here]
NODMG_BIT = 1 << 1         # no damage (predicted path 0xDDF784), NOT used     [V]
PLAYER_NODEAD_G = 0x5B84290  # debug byte, local player only                  [V 0x19BDF90..0x19BDFA0]
DBG_GATE_G = 0x5B3CE38     # must be non-null or 0x19BDF34 asserts             [V 0x19BDF54]


def module(w):
    """(chr, mod, problem) for the local player"""
    chr_, _, _ = w.me()
    if not chr_:
        return None, None, 'no local player chr (entry 0)'
    m = w.q(chr_ + 0x2470)
    mod = w.q(m + 0x18) if m else None
    if not mod:
        return chr_, None, '[chr+0x2470]+0x18 unreadable'
    back = w.q(mod + 8)
    if back != chr_:
        return chr_, mod, '[mod+8] = %s != chr %s' % (w.rel(back), w.rel(chr_))
    return chr_, mod, None


def state(w):
    chr_, mod, why = module(w)
    e = w.player_entry(0)
    st = {'chr': chr_, 'mod': mod, 'why': why,
          'flags': w.h(mod + FLAGS_OFF) if mod else None,
          'mod_hp': w.i(mod + 0x290) if mod else None, 'mod_max': w.i(mod + 0x294) if mod else None,
          'master_hp': w.i(e[3] + 0xF30) if e and e[3] else None,
          'global': w.b(w.base + PLAYER_NODEAD_G),
          'gate': w.q(w.base + DBG_GATE_G),
          'wcm_player': None}
    wcm = w.g(WCM_G)
    st['wcm_player'] = w.q(wcm + 0x1A8) if wcm else None
    return st


def fmt(st):
    f = st['flags']
    bits = '?' if f is None else 'flags 0x%04x (nodead b2 %d, immortal b0 %d, nodamage b1 %d)' % (
        f, (f >> 2) & 1, f & 1, (f >> 1) & 1)
    return '%s | global player-no-dead byte %s | HP mod+0x290 %s/%s, master %s' % (
        bits, st['global'], st['mod_hp'], st['mod_max'], st['master_hp'])


def set_nodeath(w, on, mode='bit', force=False, quiet=False):
    """returns (before, after) or (before, None) on refusal"""
    before = state(w)
    if before['why'] and not (force and before['mod']):
        print('%s: refused: %s' % (w.who, before['why']))
        return before, None
    if mode in ('bit', 'both'):
        f = before['flags']
        if f is None:
            print('%s: flag word unreadable' % w.who)
            return before, None
        nf = (f | NODEAD_BIT) if on else (f & ~NODEAD_BIT)
        if nf != f:
            # low byte only (bit 2 lives there); a one-shot latch bit 6/7 change in the same frame could be lost
            w.write(before['mod'] + FLAGS_OFF, struct.pack('<B', nf & 0xFF))
    if mode in ('global', 'both'):
        if not before['gate']:
            print('%s: main+0x%X is null: the global switch is not read; skipping it' % (w.who, DBG_GATE_G))
        elif before['wcm_player'] != before['chr']:
            print('%s: [WCM+0x1A8] %s != entry-0 chr %s: global switch would not apply; skipping it' % (
                w.who, w.rel(before['wcm_player']), w.rel(before['chr'])))
        else:
            w.write(w.base + PLAYER_NODEAD_G, b'\x01' if on else b'\x00')
    after = state(w)
    if not quiet:
        print('%s: chr %s mod %s' % (w.who, w.rel(before['chr']), w.rel(before['mod'])))
        print('  before: %s' % fmt(before))
        print('  after : %s' % fmt(after))
    return before, after


def main():
    if len(sys.argv) < 3 or sys.argv[2] not in ('on', 'off', 'show'):
        print(__doc__)
        sys.exit(1)
    o = {'mode': 'bit', 'force': '0'}
    for a in sys.argv[3:]:
        k, _, v = a.partition('=')
        if k not in o:
            sys.exit('unknown option %s' % a)
        o[k] = v
    if o['mode'] not in ('bit', 'global', 'both'):
        sys.exit('mode must be bit, global or both')
    w = W(sys.argv[1])
    if sys.argv[2] == 'show':
        st = state(w)
        print('%s: chr %s mod %s%s' % (w.who, w.rel(st['chr']), w.rel(st['mod']),
                                       ' (%s)' % st['why'] if st['why'] else ''))
        print('  ' + fmt(st))
        w.report_missing()
        return 0
    on = sys.argv[2] == 'on'
    if on:
        print('%s: TEST ONLY - no-dead on the local player (never ship this)' % w.who)
    _, after = set_nodeath(w, on, o['mode'], o['force'] not in ('0', 'no', ''))
    w.report_missing()
    if after is None:
        return 1
    f = after['flags'] or 0
    ok_bit = bool(f & NODEAD_BIT) == on if o['mode'] in ('bit', 'both') else True
    ok_g = True
    if o['mode'] in ('global', 'both') and after['gate'] and after['wcm_player'] == after['chr']:
        ok_g = bool(after['global']) == on
    if not (ok_bit and ok_g):
        print('%s: read-back does not match' % w.who)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
