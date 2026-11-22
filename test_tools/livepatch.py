"""Patch one instruction word in running twin games, JIT-safe (write_memory code=True), only when the
current word is the expected original: python diag/twin/livepatch.py OFF NEWWORD ORIGWORD [A|B|AB]
(OFF = main offset; words as hex, e.g. 0xd503201f for nop). Run it again with the words swapped to undo."""
import struct
import sys
import time

sys.path.insert(0, 'diag/twin')
from mem import Mem


def main():
    off, new, orig = (int(a, 16) for a in sys.argv[1:4])
    for w in (sys.argv[4] if len(sys.argv) > 4 else 'AB'):
        m = Mem(w)
        a = m.base + off
        have = struct.unpack('<I', m.read(a, 4))[0]
        if have == orig:
            m.write(a, struct.pack('<I', new), code=True)
            print(time.strftime('%H:%M:%S'), w, f'main+{off:#x} {orig:#010x} -> {new:#010x}')
        else:
            print(time.strftime('%H:%M:%S'), w, f'main+{off:#x} is {have:#010x}, expected {orig:#010x}: not patched')


if __name__ == '__main__':
    main()
