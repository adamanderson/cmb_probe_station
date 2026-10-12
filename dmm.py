"""Agilent/Keysight 34401A over RS-232 (SCPI), 2-wire resistance on a fixed range."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from .config import DmmConfig
from .mux import MockMux

log = logging.getLogger(__name__)
OVERLOAD_LEVEL = 9.0e37  # the meter returns 9.9E+37 for an overload (open input)


class DMMError(RuntimeError):
    pass


@dataclass
class Reading:
    ohms: Optional[float]  # None when overloaded
    overload: bool


class DMM(ABC):
    @abstractmethod
    def configure(self) -> None: ...

    @abstractmethod
    def read_ohms(self) -> Reading: ...

    def close(self) -> None:
        pass


class Keysight34401A(DMM):
    def __init__(self, cfg: DmmConfig):
        import serial  # imported lazily so dry runs need no serial library

        self._cfg = cfg
        # The meter is a DTE device: use a null-modem (DTE-to-DTE) cable, and keep
        # DTR/DSR handshaking on unless the cable disables it.
        self._ser = serial.Serial(
            port=cfg.port,
            baudrate=cfg.baudrate,
            bytesize=cfg.bytesize,
            parity=cfg.parity,
            stopbits=cfg.stopbits,
            timeout=cfg.timeout_s,
            dsrdtr=cfg.dsrdtr,
        )

    def _write(self, cmd: str) -> None:
        self._ser.write((cmd + "\n").encode("ascii"))  # a newline must end every command

    def _query(self, cmd: str) -> str:
        self._write(cmd)
        line = self._ser.readline().decode("ascii", errors="replace").strip()
        if not line:
            raise DMMError(f"timeout waiting for a response to {cmd!r}")
        return line

    def check_errors(self) -> None:
        resp = self._query("SYST:ERR?")
        if not resp.startswith(("+0", "0")):
            raise DMMError(f"instrument error: {resp}")

    def configure(self) -> None:
        self._write("SYST:REM")  # required before remote control over RS-232
        self._write("*RST")
        self._write("*CLS")
        self._write(f"CONF:RES {self._cfg.range_ohms:g}")  # 2-wire ohms, fixed range
        self._write(f"RES:NPLC {self._cfg.nplc:g}")
        self._query("*OPC?")  # wait until the settings are in effect
        self.check_errors()

    def read_ohms(self) -> Reading:
        value = float(self._query("READ?"))
        if abs(value) > OVERLOAD_LEVEL:
            return Reading(None, True)
        return Reading(value, False)

    def close(self) -> None:
        try:
            self._write("SYST:LOC")  # give the front panel back
        finally:
            self._ser.close()


class MockDMM(DMM):
    """Deterministic fake: reads the pair selected on a MockMux."""

    def __init__(self, mux: MockMux):
        self._mux = mux

    def configure(self) -> None:
        pass

    def read_ohms(self) -> Reading:
        pair = self._mux.pair
        if pair is None or pair == (1, 4) or pair == (4, 1):
            return Reading(None, True)  # nothing connected / open structure
        return Reading(5000.0 * abs(pair[0] - pair[1]), False)
