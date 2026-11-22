"""TEST ONLY: press one button on one rig game: python diag/twin/press1.py WHO BUTTON"""
import sys
sys.path.insert(0, 'diag/twin')
from screen import press  # noqa: E402
press(sys.argv[1], sys.argv[2])
