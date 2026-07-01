#!/usr/bin/env python3
import os, sys, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from kuavo_sim import KuavoSim
left = {'xyz': [0.42, 0.0, 0.61], 'ypr': [-0.6, 0.0, 0.0]}
right = {'xyz': [0.42, 0.0, 0.61], 'ypr': [0.6, 0.0, 0.0]}
print('diag_start', flush=True)
with KuavoSim() as bot:
    print('constructed', flush=True)
    ok = bot.wait_ready(timeout=5.0)
    print('wait_ready', ok, flush=True)
    print('before_solve', flush=True)
    res = bot.solve_ik(left, right, frame=2, timeout=3.0)
    print('after_solve', type(res).__name__, getattr(res, 'success', None), getattr(res, 'error_reason', None), flush=True)
print('diag_done', flush=True)
