"""TEST ONLY: pick a Bloodsworn by hand-sequence from the hub screen, with a screenshot before the confirm.
python diag/twin/handpick.py WHO RIGHTS [sigil=1]   (RIGHTS = number of Right presses from Albert; sigil=1 presses Down first)
Sequence: Minus, R, A, [Down], Right xN, (shot), A, B, L, B.  Never presses Y."""
import sys, time
sys.path.insert(0, 'diag/twin')
import tctl
who, rights = sys.argv[1], int(sys.argv[2])
sigil = 'sigil=1' in sys.argv
def p(b, n=45):
    tctl.call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [b], 'frames': 6}, {'buttons': [], 'frames': n}]}})
    time.sleep(1.2)
def shot(tag):
    tctl.call(who, {'method': 'screenshot', 'params': {'height': 360}}, '<WORKSPACE>/diag/twin/%s_hp_%s.png' % (who, tag))
p('Minus', 60); shot('menu')
if 'stop=menu' in sys.argv:
    sys.exit(0)
p('R'); shot('tab'); p('A', 60)
if sigil:
    p('Down')
for i in range(rights):
    p('Right')
shot('cursor')
if 'stop=cursor' in sys.argv:
    sys.exit(0)
p('A', 70); shot('after'); p('B'); p('L'); p('B'); shot('end')
