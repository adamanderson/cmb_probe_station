"""Logic that normally needs hardware, tested with fakes."""
import sys
import types

import pytest

from probestation.config import MuxConfig
from probestation.prober import ProberError, VeloxProber


class FakeBus:
    writes = []

    def __init__(self, bus):
        pass

    def write_byte(self, addr, value):
        FakeBus.writes.append((addr, value))

    def close(self):
        pass


@pytest.fixture
def fake_smbus(monkeypatch):
    FakeBus.writes = []
    monkeypatch.setitem(sys.modules, "smbus2", types.SimpleNamespace(SMBus=FakeBus))


def test_adg729_bytes(fake_smbus):
    from probestation.mux import ADG729

    mux = ADG729(MuxConfig())
    mux.select(1, 2)  # iA = bit 0, jB = bit 5 with the default (assumed) mapping
    mux.select(3, 4)
    mux.open_all()
    assert FakeBus.writes == [(0x44, 0x00), (0x44, 0b00100001), (0x44, 0b10000100), (0x44, 0x00)]
    with pytest.raises(ValueError):
        mux.select(2, 2)


def test_adg729_rejects_bad_bit_map(fake_smbus):
    from probestation.mux import ADG729

    with pytest.raises(ValueError):
        ADG729(MuxConfig(a_bits=(0, 1, 2, 3), b_bits=(3, 5, 6, 7)))


class FakeTransport:
    def __init__(self, replies):
        self.sent, self.replies = [], list(replies)

    def send(self, command):
        self.sent.append(command)
        return self.replies.pop(0) if self.replies else "0:"


def test_velox_command_sequence():
    t = FakeTransport([])
    p = VeloxProber(t, posref="Z", unit="Y", velocity=100)
    p.move_to(12500.0, 8300.0)
    p.touchdown()
    p.lift()
    assert t.sent == [
        "MoveChuckSeparation 100",
        "MoveChuck 12500.0 8300.0 Z Y 100",
        "MoveChuckContact 100",
        "MoveChuckSeparation 100",
    ]


def test_velox_error_code_raises():
    p = VeloxProber(FakeTransport(["0:", "615: Timeout During Command Execution"]))
    with pytest.raises(ProberError):
        p.move_to(0, 0)
