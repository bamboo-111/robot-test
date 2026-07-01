#!/usr/bin/env python3
import os, sys, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from kuavo_sim import KuavoSim
import make_heart
pts = make_heart.heart_waypoints(make_heart.N_WAYPOINTS)
print('points', len(pts), flush=True)
with KuavoSim() as bot:
    bot.wait_ready(timeout=5.0)
    for i, (left, right) in enumerate(pts):
        t0 = time.time()
        res = bot.solve_ik(left, right, frame=2, timeout=3.0)
        print('solve', i, 'dt', round(time.time()-t0, 3), 'success', getattr(res, 'success', None), 'err', getattr(res, 'error_reason', None), flush=True)
print('done', flush=True)
