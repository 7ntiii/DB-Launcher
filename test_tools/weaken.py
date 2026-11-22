"""TEST ONLY: lower one enemy's HP on every given game.
python diag/twin/weaken.py GAMES KEY_HEX [HP=80]
Finds the Trespasser enemy by its key through trespassers.py's output on each game (chr addresses differ per game)."""
import re
import struct
import subprocess
import sys

sys.path.insert(0, 'diag/twin')
from mem import Mem

games, key = sys.argv[1], sys.argv[2].lower()
hp = int(sys.argv[3]) if len(sys.argv) > 3 else 80
for w in games:
    out = subprocess.run([sys.executable, 'diag/twin/trespassers.py', w], capture_output=True, text=True).stdout
    m = re.search(r'enemy chr (0x[0-9a-f]+) key %s ' % key, out)
    if not m:
        print(w, 'enemy not found')
        continue
    chr_ = int(m.group(1), 16)
    mm = Mem(w)
    d = mm.u64(mm.u64(chr_ + 0x2470) + 0x18)
    old = mm.u32(d + 0x290)
    mm.write(d + 0x290, struct.pack('<I', hp))
    print(w, 'chr %x hp %d -> %d' % (chr_, old, mm.u32(d + 0x290)))
