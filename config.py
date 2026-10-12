"""Configuration: dataclasses with defaults, loaded from a TOML file."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # pip install tomli on older Pythons


@dataclass
class MuxConfig:
    bus: int = 1
    address: int = 0x44
    # Switch bit (0-7) closing each probe pin (1-4) on the DA (HI) and DB (LO) sides.
    # ASSUMED ordering -- verify against the ADG729 datasheet and the selftest.
    a_bits: tuple = (0, 1, 2, 3)
    b_bits: tuple = (4, 5, 6, 7)


@dataclass
class DmmConfig:
    port: str = "/dev/ttyUSB0"
    # Factory RS-232 settings of the 34401A: 9600 baud, even parity / 7 data bits,
    # 2 stop bits (fixed), DTR/DSR handshake. Must match the front-panel I/O menu.
    baudrate: int = 9600
    bytesize: int = 7
    parity: str = "E"
    stopbits: int = 2
    dsrdtr: bool = True
    timeout_s: float = 10.0
    range_ohms: float = 1e5  # fixed range; no autorange
    nplc: float = 1.0


@dataclass
class ProberConfig:
    host: str = "192.168.50.2"
    port: int = 0  # TODO: set once the Velox transport is chosen
    posref: str = "Z"  # MoveChuck reference: H home, Z zero, C center, R relative, D die home
    unit: str = "Y"  # Y = microns
    velocity: float = 100.0  # percent
    theta_posref: str = "Z"  # MoveTheta reference: H home, Z zero, C center (unverified choice)


@dataclass
class RunConfig:
    settle_s: float = 0.05  # wait after closing the mux, before reading
    lock_file: str = "/tmp/probestation.lock"


@dataclass
class Config:
    mux: MuxConfig = field(default_factory=MuxConfig)
    dmm: DmmConfig = field(default_factory=DmmConfig)
    prober: ProberConfig = field(default_factory=ProberConfig)
    run: RunConfig = field(default_factory=RunConfig)


def _build(cls, data: dict[str, Any]):
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ValueError(f"Unknown {cls.__name__} keys: {sorted(unknown)}")
    kwargs = {k: (tuple(v) if isinstance(v, list) else v) for k, v in data.items()}
    return cls(**kwargs)


def load_config(path: str | None) -> Config:
    """Load a TOML config; with no path, return the defaults."""
    if path is None:
        return Config()
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    unknown = set(raw) - {"mux", "dmm", "prober", "run"}
    if unknown:
        raise ValueError(f"Unknown config sections: {sorted(unknown)}")
    return Config(
        mux=_build(MuxConfig, raw.get("mux", {})),
        dmm=_build(DmmConfig, raw.get("dmm", {})),
        prober=_build(ProberConfig, raw.get("prober", {})),
        run=_build(RunConfig, raw.get("run", {})),
    )
