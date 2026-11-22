"""For working on the page: serves the launcher's window without opening it and prints its address.

    python show_page.py [seconds]       (DUSKLAN_ROLE=host|join picks the launcher; default 600 seconds)
"""
import sys
import time

from dusklan import web

launcher = web.Launcher()
server, url = web.serve(launcher)
print(url, flush=True)
end = time.time() + int(sys.argv[1] if len(sys.argv) > 1 else 600)
while time.time() < end:
    launcher.last_question = time.time()
    time.sleep(1)
