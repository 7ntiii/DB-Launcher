# kin7_apply.py: applies the kin7 kin_recall fix to regress_small.py (owner no-dead bit around recall_once,
# state 5 = NOT JUDGED). Run only when regress_small.py is NOT running. runmix.sh calls it once. kin7_notes.md.
import shutil
from pathlib import Path

P = Path(r'<WORKSPACE>\diag\twin\regress_small.py')
SP = Path(__file__).resolve().parent   # backup regress_small.pre_kin7.py next to this file
shutil.copy(P, SP / 'regress_small.pre_kin7.py')
s = P.read_bytes().decode('utf-8').replace('\r\n', '\n')


def rep(old, new):
    global s
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)


# 1. owner protected for the whole recall (state 5 = owner HP < 1, 0xD833E8..0xD8353C)
rep('''        stage['now'] = 'recall (kin out, area safe, press)'
        st, why, vals = recall_once(ctx, ctx.actor, stage)
    except Timeout as e:
        st, why, vals = 'SKIP', 'time-out during %s: %s' % (stage['now'], e), ''
    finally:
        stop.set()''', '''        stage['now'] = 'recall (kin out, area safe, press)'
        # kin7 (2026-11-17): state 5 RequestForceUnsummon comes ONLY from SummonState when the OWNER chr's HP
        # [[owner+0x2470]+0x18]+0x290 < 1 (0xD833E8..0xD8353C); no combat or cooldown rule is on that path. The four
        # inconclusive runs = the owner died during make_safe / the wait. TEST ONLY: the owner gets the engine's
        # no-dead bit on its own player chr (as kin_death), re-asserted by the watch, cleared at the end.
        import nodeath
        nd_b, nd_a = nodeath.set_nodeath(gw(ctx.actor), True, 'bit', quiet=True)
        if nd_a is None:
            raise Skip('owner %s: no-dead bit could not be set (%s)' % (ctx.actor, nd_b.get('why')))
        say('TEST ONLY owner %s protected: no-dead bit on its own player chr (%s)' % (ctx.actor, nodeath.fmt(nd_a)))
        try:
            st, why, vals = recall_once(ctx, ctx.actor, stage)
        finally:
            try:
                nodeath.set_nodeath(gw(ctx.actor), False, 'bit', quiet=True)
                say('owner %s: no-dead bit off again' % ctx.actor)
            except Exception as ex:
                say('owner %s: no-dead bit NOT cleared (%s): run  python diag/twin/nodeath.py %s off' % (
                    ctx.actor, ex, ctx.actor))
    except Skip as e:
        st, why, vals = 'SKIP', str(e), ''
    except Timeout as e:
        st, why, vals = 'SKIP', 'time-out during %s: %s' % (stage['now'], e), ''
    finally:
        stop.set()''')

# 2. the watch re-asserts the bit, and a state 5 makes the result NOT JUDGED (SKIP with the cause)
rep('''        def watch(until, secs):
            secs = max(3.0, min(secs, ctx.left() - 8))
            t0 = time.time()
            while time.time() - t0 < secs:''', '''        def watch(until, secs):
            secs = max(3.0, min(secs, ctx.left() - 8))
            t0 = time.time()
            try:
                import nodeath
                nodeath.set_nodeath(gw(a), True, 'bit', quiet=True)   # the game may clear it: re-assert
            except Exception:
                pass
            while time.time() - t0 < secs:''')

rep('''        if back and out:
            return 'PASS', '%s owner %s: 3 -> 4 -> 2 and 2 -> 3 on every game (safe place %s)' % (role, a, safe), vals''',
    '''        if any(5 in sq for sq in seq.values()):
            return 'SKIP', ('NOT JUDGED: state 5 RequestForceUnsummon seen (%s): the owner chr had HP < 1 '
                            '(0xD833FC), not a recall rule; owner master HP now %s' % (
                                {w: sq for w, sq in seq.items() if 5 in sq}, master_hp(a))), vals
        if back and out:
            return 'PASS', '%s owner %s: 3 -> 4 -> 2 and 2 -> 3 on every game (safe place %s)' % (role, a, safe), vals''')
P.write_bytes(s.replace('\n', '\r\n').encode('utf-8'))
print('ok')
