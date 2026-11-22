"""Poll timing of the newest search in the newest twin run: python diag/twin/polls.py"""
import glob, json
log = sorted(glob.glob('diag/twin/runs/*/frontdoor.log'))[-1]
ev = []
for line in open(log, encoding='utf-8', errors='replace'):
    try: ev.append(json.loads(line))
    except ValueError: pass
tickets = [e for e in ev if e.get('event') == 'online_ticket']
if tickets:
    t0 = tickets[-2]['time'] if len(tickets) > 1 else tickets[-1]['time']
    for e in ev:
        if e['time'] >= t0 - 0.5 and e.get('event') in ('frontend_type', 'online_match', 'online_matched_reply'):
            print('%7.2f %-22s %-44s %s' % (e['time'] - t0, e['event'], e.get('type', ''), e.get('peer', e.get('pid', ''))))
