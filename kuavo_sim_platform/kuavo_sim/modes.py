"""Control mode enum and parser."""

from enum import IntEnum


class CtrlMode(IntEnum):
    NoControl = 0
    ArmOnly = 1
    BaseOnly = 2
    BaseArm = 3
    ArmEeOnly = 4


NAME_TO_MODE = {mode.name: int(mode) for mode in CtrlMode}


def resolve_mode(value):
    """Return a validated mode integer from an int-like value or enum name."""
    if isinstance(value, CtrlMode):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text in NAME_TO_MODE:
            return NAME_TO_MODE[text]
        try:
            return resolve_mode(int(text, 10))
        except ValueError as exc:
            valid = ", ".join(NAME_TO_MODE)
            raise ValueError(f"unknown mode {value!r}; valid names: {valid}") from exc
    ivalue = int(value)
    if ivalue not in NAME_TO_MODE.values():
        raise ValueError(f"mode out of range 0..4: {ivalue}")
    return ivalue
