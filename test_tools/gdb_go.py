"""Let a game that waits at boot for a debugger run: connect to its gdb stub, continue, close.
python diag/twin/gdb_go.py PORT [TRIES=120]"""
import socket, sys, time
sys.path.insert(0, 'diag/net')
from gdb import Gdb
port = int(sys.argv[1]); tries = int(sys.argv[2]) if len(sys.argv) > 2 else 120
for i in range(tries):
    try:
        g = Gdb(port)
        break
    except OSError:
        time.sleep(1)
else:
    sys.exit('no gdb stub on %d' % port)
print('connected', g.cmd('?')[:20], flush=True)
g._send('c')
time.sleep(0.5)
g.s.close()
print('continued and closed', flush=True)
