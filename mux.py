"""ADG729 matrix switch driver.

The chip takes a single byte over I2C: bit n set = switch n closed, 0x00 = all open.
Wiring (see the hardware doc): meter HI -> DA, meter LO -> DB, and probe pin n goes
to both nA and nB.  Measuring between pins i and j therefore closes switch iA
(HI side) and switch jB (LO side) and nothing else.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from .config import MuxConfig

log = logging.getLogger(__name__)
PINS = (1, 2, 3, 4)


class Mux(ABC):
    @abstractmethod
    def select(self, hi: int, lo: int) -> None:
        """Connect meter HI to probe pin `hi` and meter LO to probe pin `lo`."""

    @abstractmethod
    def open_all(self) -> None:
        """Open every switch."""

    def close(self) -> None:
        self.open_all()


def _check_pins(hi: int, lo: int) -> None:
    if hi not in PINS or lo not in PINS:
        raise ValueError(f"pins must be in {PINS}, got hi={hi} lo={lo}")
    if hi == lo:
        # iA together with iB would tie HI to LO through the mux (a false short).
        raise ValueError(f"refusing to connect HI and LO to the same pin ({hi})")


class ADG729(Mux):
    def __init__(self, cfg: MuxConfig):
        a, b = tuple(cfg.a_bits), tuple(cfg.b_bits)
        bits = a + b
        if len(a) != 4 or len(b) != 4 or sorted(bits) != list(range(8)):
            raise ValueError("a_bits and b_bits must be 4 distinct bits each, covering 0-7")
        self._a, self._b = a, b
        self._address = cfg.address
        from smbus2 import SMBus  # imported lazily so dry runs need no I2C library

        self._bus = SMBus(cfg.bus)
        self.open_all()

    def _write(self, value: int) -> None:
        self._bus.write_byte(self._address, value)

    def select(self, hi: int, lo: int) -> None:
        _check_pins(hi, lo)
        self._write((1 << self._a[hi - 1]) | (1 << self._b[lo - 1]))

    def open_all(self) -> None:
        self._write(0x00)

    def close(self) -> None:
        try:
            self.open_all()
        finally:
            self._bus.close()


class MockMux(Mux):
    """Records the selected pair; used for dry runs and tests."""

    def __init__(self):
        self.pair: tuple[int, int] | None = None

    def select(self, hi: int, lo: int) -> None:
        _check_pins(hi, lo)
        self.pair = (hi, lo)

    def open_all(self) -> None:
        self.pair = None
