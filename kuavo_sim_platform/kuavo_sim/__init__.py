"""Kuavo 5-W script control platform."""

from .modes import CtrlMode, resolve_mode

__all__ = [
    "CtrlMode",
    "KuavoSim",
    "KuavoSimError",
    "resolve_mode",
]


def __getattr__(name):
    if name in {"KuavoSim", "KuavoSimError"}:
        from .client import KuavoSim, KuavoSimError

        return {"KuavoSim": KuavoSim, "KuavoSimError": KuavoSimError}[name]
    raise AttributeError(name)
