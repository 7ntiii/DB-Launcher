"""Save a picture of rig game WHO: python diag/twin/shot3.py WHO NAME"""
import sys
sys.path.insert(0, 'diag/twin')
import screen
who, name = sys.argv[1], sys.argv[2]
img = screen.grab(who)
out = 'diag/net/user3p_2311/%s_%s.png' % (who, name)
try:
    img.save(out)
except AttributeError:
    open(out, 'wb').write(img)
print(out)
