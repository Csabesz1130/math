"""Paper-to-code kits: exact oracles for checking transcribed algorithms.

A kit module provides ``NAME``, ``FAMILY``, ``ENTRYPOINT``, ``INTERFACE``,
``instances(seed, count)``, ``oracle(instance)``, ``check(instance, output,
reference)`` and a ``baseline(instance)`` implementing a classical method.
"""

from __future__ import annotations

from types import ModuleType

from . import scheduling, superstring

_KITS: dict[str, ModuleType] = {kit.NAME: kit for kit in (scheduling, superstring)}


def get(name: str) -> ModuleType:
    try:
        return _KITS[name]
    except KeyError as error:
        raise KeyError(f"unknown kit {name!r}; available: {', '.join(sorted(_KITS))}") from error


def names() -> list[str]:
    return sorted(_KITS)
