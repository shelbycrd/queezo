"""Environment validation for the single-worker inference budgets."""
import os


def budget(name, default, lower, upper, *, parse=int):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = parse(raw)
    except ValueError:
        raise ValueError(f'{name} must be a number in [{lower}, {upper}].') from None
    if not lower <= value <= upper:
        raise ValueError(f'{name} must be a number in [{lower}, {upper}].')
    return value
