"""The host panel window for the twin rig (TWIN_HOST_PANEL=1): serves launcher/lan_fix/panel.html on
127.0.0.1:18450, passes /api/* on to the match server's panel API (18451) and opens the same
app-mode window as launcher/lan_fix/lan_fix_host.py. Runs until killed.
Usage: python diag/twin/panel_window.py HOST_IP"""
import json, os, subprocess, sys, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
PAGE = WS / 'launcher' / 'lan_fix' / 'panel.html'
PANEL_PORT, API_PORT = 18450, 18451
HOST_IP = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'


class Panel(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, data, kind='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _forward(self, body=None):
        request = urllib.request.Request('http://127.0.0.1:%d%s' % (API_PORT, self.path), data=body,
                                         headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=3) as reply:
                self._send(reply.status, reply.read())
        except (OSError, urllib.error.URLError):
            self._send(503, json.dumps({'error': 'server not running', 'host_ip': HOST_IP}).encode())

    def do_GET(self):
        if self.path.startswith('/api/'):
            return self._forward()
        if self.path in ('/', '/index.html'):
            return self._send(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
        self._send(404, b'{}')

    def do_POST(self):
        self._forward(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')


def open_window(url):
    roots = [os.environ.get(name, '') for name in ('ProgramFiles(x86)', 'ProgramFiles', 'LOCALAPPDATA')]
    for tail in ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe'):
        for root in roots:
            path = os.path.join(root, tail)
            if root and os.path.exists(path):
                profile = os.path.join(os.environ.get('LOCALAPPDATA', str(WS)), 'DuskbloodsHostPanel')
                subprocess.Popen([path, '--app=' + url, '--window-size=1180,860',
                                  '--user-data-dir=' + profile, '--no-first-run',
                                  '--no-default-browser-check'])
                return
    import webbrowser
    webbrowser.open(url)


server = ThreadingHTTPServer(('127.0.0.1', PANEL_PORT), Panel)
server.daemon_threads = True
if '--no-window' not in sys.argv:
    open_window('http://127.0.0.1:%d/' % PANEL_PORT)
print('panel on http://127.0.0.1:%d/' % PANEL_PORT, flush=True)
server.serve_forever()
