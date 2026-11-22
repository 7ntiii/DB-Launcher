"""Full-size picture of rig game WHO: python diag/twin/shot3big.py WHO NAME"""
import sys, os
sys.path.insert(0, 'diag/twin')
import screen
who, name = sys.argv[1], sys.argv[2]
out = os.path.abspath('diag/net/user3p_2311/%s_%s.png' % (who, name))
screen.call(who, {'method': 'screenshot', 'params': {'height': 720}}, out)
print(out)
