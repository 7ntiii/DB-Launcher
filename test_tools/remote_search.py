"""remote_search.py: wait until K remote players search in the rig's host panel (tailscale_rig_notes.md).
python diag/twin/remote_search.py K [TIMEOUT_S]      (run_night.sh `match` with RIG_NET=tailscale)
python diag/twin/remote_search.py --selftest         (no panel needed: the row rule on made-up rows)
Read only: GET http://127.0.0.1:18451/api/state (the panel the rig's pkgtest serve runs), nothing is sent.
Remote = any row that is not this PC: not 127.0.0.1 (game 1) and not the panel's host_ip (this PC's 100.x, the
second rig game). Guests' second games come as 127.0.2.<k> and count. A row the panel marks "NOT on Tailscale"
(joined with a home address) is reported and never counted. Exit 0 once K remote rows search, 1 on time-out."""
import json
import sys
import time
import urllib.request

API = 'http://127.0.0.1:18451/api/state'


def remote_rows(state):
    """-> (searching remote ips, remote ips not on Tailscale) for one panel state."""
    own = (state.get('server') or {}).get('host_ip') or ''
    searching, wrong = [], []
    for row in state.get('players', []):
        ip = row.get('ip') or ''
        if not ip or ip == '127.0.0.1' or ip == own:
            continue
        if 'NOT on ' in (row.get('detail') or ''):
            wrong.append(ip)
        elif row.get('kind') == 'search':
            searching.append(ip)
    return searching, wrong


def selftest():
    st = {'server': {'host_ip': '100.70.1.2'},
          'players': [{'ip': '127.0.0.1', 'kind': 'search'}, {'ip': '100.70.1.2', 'kind': 'search'},
                      {'ip': '100.90.3.4', 'kind': 'search'}, {'ip': '127.0.2.1', 'kind': 'search'},
                      {'ip': '100.99.5.6', 'kind': 'hub'},
                      {'ip': '192.168.1.66', 'kind': 'search', 'detail': 'NOT on Tailscale (192.168.1.66): ...'}]}
    searching, wrong = remote_rows(st)
    assert searching == ['100.90.3.4', '127.0.2.1'], searching
    assert wrong == ['192.168.1.66'], wrong
    print('selftest PASS: remote searching', searching, '| not on Tailscale', wrong)
    return 0


def main(argv):
    if argv[1:2] == ['--selftest']:
        return selftest()
    k = int(argv[1]) if len(argv) > 1 else 2
    timeout = float(argv[2]) if len(argv) > 2 else 1800
    t0, last = time.time(), None
    while time.time() - t0 < timeout:
        try:
            searching, wrong = remote_rows(json.loads(urllib.request.urlopen(API, timeout=5).read()))
        except (OSError, ValueError) as error:
            searching, wrong = None, [str(error)]
        now = (tuple(searching or ()), tuple(wrong))
        if now != last:
            last = now
            if searching is None:
                print(time.strftime('%H:%M:%S'), 'panel not answering:', wrong[0], flush=True)
            else:
                print(time.strftime('%H:%M:%S'), f'remote players searching: {len(searching)} of {k}',
                      searching, flush=True)
                if wrong:
                    print(time.strftime('%H:%M:%S'), 'NOT on Tailscale (must join again with this PC\'s 100.x):',
                          wrong, flush=True)
        if searching is not None and len(searching) >= k:
            print(time.strftime('%H:%M:%S'), f'{len(searching)} remote players searching', flush=True)
            return 0
        time.sleep(2)
    print(time.strftime('%H:%M:%S'), f'time-out: fewer than {k} remote players searched in {timeout:.0f} s', flush=True)
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
