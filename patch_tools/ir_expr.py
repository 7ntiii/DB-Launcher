"""Readable view of an IR dump (EDEN_NX2_IR_DUMP): Identity copies resolved, single-use values
inlined into expressions. Usage:
  python tools/ir_expr.py FILE                 every multi-use / side-effect line, simplified
  python tools/ir_expr.py FILE --value %123     the expression tree of one value (depth 12)
"""
import re
import sys

LINE = re.compile(r'^\[[0-9a-f]+\]\s+(?:(%\d+)\s+=\s+)?(\w+)\s*(.*?)\s*(?:\(uses: (\d+)\))?$')
NAMES = {
    'FPMul32': '*', 'FPAdd32': '+', 'IAdd32': '+i', 'ISub32': '-i',
}


def parse(path):
    values, order, blocks = {}, [], []
    for raw in open(path, encoding='utf-8'):
        raw = raw.rstrip()
        if raw.startswith('Block'):
            order.append(('block', raw))
            continue
        m = LINE.match(raw)
        if not m:
            continue
        name, op, args, uses = m.groups()
        args = [a.strip() for a in args.split(',')] if args else []
        entry = {'name': name, 'op': op, 'args': args, 'uses': int(uses or 0)}
        if name:
            values[name] = entry
        order.append(('inst', entry))
    return values, order


def resolve(values, a):
    seen = 0
    while a in values and values[a]['op'] == 'Identity' and seen < 100:
        a = values[a]['args'][0]
        seen += 1
    return a


def fmt_const(a):
    if a.startswith('#'):
        try:
            v = int(a[1:])
            if v > 0x30000000:
                import struct
                f = struct.unpack('<f', struct.pack('<I', v & 0xffffffff))[0]
                return f'{f:.6g}'
        except ValueError:
            pass
    return a


def expr(values, a, depth, top=False):
    a = resolve(values, a)
    if a not in values:
        return fmt_const(a)
    e = values[a]
    if depth <= 0 or (not top and e['uses'] > 1 and e['op'] not in ('GetCbufF32', 'GetCbufU32')):
        return a
    op, args = e['op'], e['args']
    if op in ('GetCbufF32', 'GetCbufU32'):
        off = args[1].lstrip('#')
        try:
            off = f'{int(off):#x}'
        except ValueError:
            off = expr(values, args[1], depth - 1)
        return f'c{args[0].lstrip("#")}[{off}]' + ('u' if op.endswith('U32') else '')
    if op in ('BitCastF32U32', 'BitCastU32F32'):
        return expr(values, args[0], depth)
    parts = [expr(values, x, depth - 1) for x in args]
    if op in NAMES and len(parts) == 2:
        return f'({parts[0]} {NAMES[op]} {parts[1]})'
    if op == 'FPFma32':
        return f'fma({", ".join(parts)})'
    return f'{op}({", ".join(parts)})'


def main():
    path = sys.argv[1]
    values, order = parse(path)
    if '--value' in sys.argv:
        v = sys.argv[sys.argv.index('--value') + 1]
        depth = int(sys.argv[sys.argv.index('--depth') + 1]) if '--depth' in sys.argv else 12
        print(v, '=', expr(values, v, depth, top=True))
        return
    for kind, item in order:
        if kind == 'block':
            print(item)
            continue
        e = item
        if e['op'] in ('Identity', 'ConditionRef') or (e['name'] and e['uses'] == 1 and e['op'] not in ('Phi',)):
            continue
        if e['name'] is None:
            print('   ', e['op'], ', '.join(expr(values, x, 6) for x in e['args']))
        elif e['op'] == 'Phi':
            print('  ', e['name'], '= Phi', ' '.join(e['args']))
        else:
            print('  ', e['name'], f'[{e["uses"]}] =', expr(values, e['name'], 6, top=True))


if __name__ == '__main__':
    main()
