"""Live A/B test for the final's fire at the out player's spot (diag/net/deathfx2_notes.md). Game B only by default.
    python diag/twin/finalout_off_live.py [B]        FINALOUT_HOOK off: stock word back at main+0x1140DCC
    python diag/twin/finalout_off_live.py [B] undo   FINALOUT_HOOK on again
With the hook off, B's game does not run the elimination block for the out player, so B keeps its copy of that
player (it is not destroyed 2 s after the death). If B then shows no fire while the laptop does, the block's removal
of the copy (while its death effect still plays) is the cause, and assist_v427_finalhold.diff is the fix.
Side effect while off: B's copy of the out player keeps stage 1 until the final ends (as before v3.9.9)."""
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem  # noqa: E402

OFF, STOCK, HOOK = 0x1140DCC, '885d0034', 'b607fe17'
args = sys.argv[1:]
games = next((a for a in args if a.isalpha() and a.isupper()), 'B')
undo = 'undo' in args
for g in games:
    m = Mem(g)
    have = m.read(m.base + OFF, 4).hex()
    want = HOOK if undo else STOCK
    if have == want:
        print(g, 'main+%#x already %s' % (OFF, want))
    elif have in (STOCK, HOOK):
        m.write(m.base + OFF, bytes.fromhex(want), code=True)
        print(g, 'main+%#x %s -> %s (%s)' % (OFF, have, want, 'hook on' if undo else 'hook OFF'),
              '; reads back', m.read(m.base + OFF, 4).hex())
    else:
        print(g, 'main+%#x is %s: neither stock nor hook, NOT written' % (OFF, have))
