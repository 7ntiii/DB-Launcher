import sys, struct
sys.path.insert(0, 'diag/twin')
from mem import Mem
m = Mem(sys.argv[1]); a = int(sys.argv[2], 16); n = int(sys.argv[3], 16)
b = m.read(a, n)
for o in range(0, n, 16):
    q = struct.unpack_from('<4f', b, o); h = struct.unpack_from('<2Q', b, o)
    print('+%03x %016x %016x  %s' % (o, h[0], h[1], ' '.join('%.3g' % x for x in q)))
