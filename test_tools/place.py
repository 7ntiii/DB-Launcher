"""Twin helper: python diag/twin/place.py VIEWER MOVER DIST -> measures the viewer's camera-forward by a short
stick step, then teleports the mover DIST m in front of the viewer (debug server write_memory)."""
import sys, time, struct, math, os
sys.path.insert(0, 'diag/twin')
from mem import Mem
import tctl
PORT = {'A': 6543, 'B': 6544}
def chrs(m):
    arr = m.read(m.u64(m.u64(m.base + 0x5b3cd88) + 0x30), 0x38 * 3)
    return [struct.unpack_from('<7Q', arr, i * 0x38) for i in range(3)]
def pos(m, phys):
    for k in range(10):   # the debug server can miss a read while the game is busy
        try:
            return struct.unpack('<3f', m.read(phys + 0x70, 12))
        except TypeError:
            time.sleep(0.5)
    return struct.unpack('<3f', m.read(phys + 0x70, 12))
viewer, mover, dist = sys.argv[1], sys.argv[2], float(sys.argv[3])
side = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0   # metres to the viewer's side, so its own body does not hide the mover
mv, mm = Mem(viewer), Mem(mover)
pv = chrs(mv)[0][5]; pm = chrs(mm)[0][5]
a = pos(mv, pv)
tctl.call(viewer, {'method': 'input_sequence', 'params': {'steps': [{'left_stick': [0, 1], 'frames': 8}, {'frames': 12}]}})
b = pos(mv, pv)
dx, dz = b[0] - a[0], b[2] - a[2]; n = math.hypot(dx, dz) or 1
fx, fz = dx / n, dz / n
tgt = (b[0] + fx * dist + fz * side, b[1] + 0.3, b[2] + fz * dist - fx * side)
yaw = math.atan2(fx, fz)            # face the viewer: forward (-sin, -cos) points back along -f
print(f'viewer {viewer} {a} -> {b} fwd=({fx:.2f},{fz:.2f}); mover {mover} to {tgt} yaw {yaw:.2f}')
mm.write(pm + 0x70, struct.pack('<3f', *tgt))
mm.write(pm + 0x64, struct.pack('<f', yaw))
time.sleep(1.5)
print('mover now', pos(mm, pm), 'viewer copy of mover', pos(mv, chrs(mv)[1][5]))
