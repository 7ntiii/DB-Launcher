"""Both twin games: title -> Continue -> skip intro -> hub. Shots diag/twin/{A,B}_nav_*.png"""
import socket, sys, threading, time
sys.path.insert(0, 'diag/twin')
from tctl import call, PORT

def wait_server(who, timeout=300):
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection(('127.0.0.1', PORT[who]), 1).close(); return True
        except OSError:
            time.sleep(2)
    return False

def frames(who, n):
    t = time.time(); call(who, {'method': 'input_sequence', 'params': {'steps': [{'frames': n}]}})
    r = n / 30 - (time.time() - t)
    if r > 0: time.sleep(r)

def press(who, b):
    call(who, {'method': 'input_sequence', 'params': {'steps': [{'buttons': [b], 'frames': 6}, {'frames': 90}]}})

def shot(who, name):
    call(who, {'method': 'screenshot', 'params': {'height': 480}}, f'diag/twin/{who}_nav_{name}.png')

def run(who):
    if not wait_server(who):
        print(who, 'no debug server', flush=True); return
    frames(who, 600); shot(who, 'title'); press(who, 'A')
    frames(who, 300); shot(who, 'menu'); press(who, 'A')
    frames(who, 240)
    for _ in range(4):
        press(who, 'Plus'); press(who, 'A'); frames(who, 120)
    frames(who, 900); shot(who, 'done'); print(who, 'done', flush=True)

ts = [threading.Thread(target=run, args=(w,)) for w in 'AB']
for t in ts: t.start()
for t in ts: t.join()
