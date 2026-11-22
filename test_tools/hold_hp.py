"""Test helper: keep a rig player's health full so a long fight can be driven: python diag/twin/hold_hp.py A [SECONDS=300]
Writes the local player's master HP ([entry0+0x18]+0xF30) back to its maximum 5 times a second. TEST ONLY."""
import struct, sys, time
sys.path.insert(0, 'diag/twin')
from world_lib import W
w = W(sys.argv[1]); secs = float(sys.argv[2]) if len(sys.argv) > 2 else 300
t0 = time.time()
while time.time() - t0 < secs:
    try:
        e = w.player_entry(0)
        mod = e[3]
        mx = 250  # below every character's maximum
        if 0 < w.i(mod + 0xF30) < mx:
            w.write(mod + 0xF30, struct.pack('<i', mx))
    except Exception:
        pass
    time.sleep(0.2)
