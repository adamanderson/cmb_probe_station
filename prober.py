"""Prober interface and the Velox hook.

Nothing outside this module knows how Velox is reached.  `VeloxProber` speaks SCI
commands through a `Transport`; the transport itself (SCI over TCP/IP, or a bridge
script on the Velox PC) is still to be written -- see SocketTransport.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional, Protocol

log = logging.getLogger(__name__)


class ProberError(RuntimeError):
    pass


class Prober(ABC):
    @abstractmethod
    def move_to(self, x: float, y: float, theta: Optional[float] = None) -> None:
        """Move the chuck to (x, y), with the chuck lowered to separation first.

        theta is the chuck rotation in degrees, counter-clockwise; None leaves it alone."""

    @abstractmethod
    def touchdown(self) -> None:
        """Raise the chuck to the preset contact height."""

    @abstractmethod
    def lift(self) -> None:
        """Lower the chuck to the separation height."""

    def close(self) -> None:
        pass


class MockProber(Prober):
    def __init__(self):
        self.events: list[tuple] = []

    def move_to(self, x: float, y: float, theta: Optional[float] = None) -> None:
        self.events.append(("move", x, y) if theta is None else ("move", x, y, theta))
        log.info("[mock] move_to(%s, %s, theta=%s)", x, y, theta)

    def touchdown(self) -> None:
        self.events.append(("touchdown",))
        log.info("[mock] touchdown")

    def lift(self) -> None:
        self.events.append(("lift",))
        log.info("[mock] lift")


class Transport(Protocol):
    def send(self, command: str) -> str:
        """Send one SCI command string and return the response string."""


class SocketTransport:
    """TODO: the real link to Velox.

    Decide between SCI over TCP/IP and a bridge script on the Velox PC, then implement
    send() to return the response to one command.  Until then, real (non-dry) runs
    stop here with a clear message; `selftest` does not need a prober.
    """

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port

    def send(self, command: str) -> str:
        raise NotImplementedError("Velox transport not implemented yet (see prober.SocketTransport)")


class VeloxProber(Prober):
    """Velox SCI commands (names and parameters from the Velox Remote Interface Guide):

    MoveChuck x y PosRef Unit Velocity   -- XY move; Z must be at separation or lower
    MoveTheta Position PosRef Unit Velocity -- chuck rotation (degrees, counter-clockwise positive)
    MoveChuckSeparation [Velocity]       -- chuck Z to separation height
    MoveChuckContact [Velocity]          -- chuck Z to the preset contact height

    Contact height must already be set in Velox (these commands return an error
    otherwise).  Commands are synchronous: the response comes back when the move is done.
    """

    def __init__(self, transport: Transport, posref: str = "Z", unit: str = "Y", velocity: float = 100.0,
                 theta_posref: str = "Z"):
        self._t = transport
        self._posref, self._unit, self._velocity = posref, unit, velocity
        self._theta_posref = theta_posref

    def _sci(self, command: str) -> str:
        log.debug("SCI > %s", command)
        response = self._t.send(command).strip()
        log.debug("SCI < %s", response)
        # ASSUMPTION to verify against real responses: every response starts with an
        # integer error code, 0 meaning success (e.g. "0:" or "0 ...").
        head = response.replace(":", " ").split()
        if not head or not head[0].lstrip("-").isdigit():
            raise ProberError(f"unparseable response to {command!r}: {response!r}")
        if int(head[0]) != 0:
            raise ProberError(f"{command!r} failed: {response}")
        return response

    def move_to(self, x: float, y: float, theta: Optional[float] = None) -> None:
        self.lift()
        if theta is not None:
            # Syntax from the SCI guide (MoveTheta Position PosRef Unit Velocity; positive is
            # counter-clockwise). UNVERIFIED on the real station: the guide's own example
            # ("MoveTheta 1000. R E") does not match its parameter table, and the theta
            # PosRef (H/Z/C) is a choice still to make.
            self._sci(f"MoveTheta {theta:.4f} {self._theta_posref} D {self._velocity:g}")
        self._sci(f"MoveChuck {x:.1f} {y:.1f} {self._posref} {self._unit} {self._velocity:g}")

    def touchdown(self) -> None:
        self._sci(f"MoveChuckContact {self._velocity:g}")

    def lift(self) -> None:
        self._sci(f"MoveChuckSeparation {self._velocity:g}")
