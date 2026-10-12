"""The measurement loop: one pass over a sites file.

A site is one chuck position = one touchdown of the 4-pin probe card.  At each site
all six unique pin pairs are measured; a site's rows are written together, so a
site in the output file is always complete (this is what --resume relies on).
"""
from __future__ import annotations

import csv
import itertools
import logging
import os
import time
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from typing import Callable, Iterable, Optional

from .dmm import DMM
from .mux import PINS, Mux
from .prober import Prober

log = logging.getLogger(__name__)
PIN_PAIRS = list(itertools.combinations(PINS, 2))  # 6 pairs, hi < lo


@dataclass
class Site:
    site_id: str
    x: float
    y: float


@dataclass
class Result:
    timestamp: str
    site_id: str
    x: float
    y: float
    hi_pin: int
    lo_pin: int
    ohms: Optional[float]  # None when overloaded
    overload: bool


@dataclass
class Hooks:
    """Optional callbacks; any may be left as None."""

    before_move: Optional[Callable[[Site], None]] = None
    after_touchdown: Optional[Callable[[Site], None]] = None
    after_measurement: Optional[Callable[[Result], None]] = None
    on_error: Optional[Callable[[Optional[Site], BaseException], None]] = None


def load_sites(path: str) -> list[Site]:
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"site_id", "x", "y"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        sites = [Site(r["site_id"].strip(), float(r["x"]), float(r["y"])) for r in reader]
    ids = [s.site_id for s in sites]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: site_id values must be unique")
    return sites


def completed_sites(out_path: str) -> set[str]:
    """Sites that already have all their pair rows in an existing output file."""
    if not os.path.exists(out_path):
        return set()
    counts: dict[str, int] = {}
    with open(out_path, newline="") as fh:
        for row in csv.DictReader(fh):
            counts[row["site_id"]] = counts.get(row["site_id"], 0) + 1
    return {sid for sid, n in counts.items() if n >= len(PIN_PAIRS)}


class ResultWriter:
    COLUMNS = [f.name for f in fields(Result)]

    def __init__(self, path: str):
        new = not os.path.exists(path) or os.path.getsize(path) == 0
        self._fh = open(path, "a", newline="")
        self._csv = csv.writer(self._fh, lineterminator="\n")
        if new:
            self._csv.writerow(self.COLUMNS)
            self._flush()

    def _flush(self) -> None:
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def write_all(self, results: Iterable[Result]) -> None:
        for r in results:
            ohms = "" if r.ohms is None else f"{r.ohms:.8g}"
            self._csv.writerow([r.timestamp, r.site_id, r.x, r.y, r.hi_pin, r.lo_pin, ohms, int(r.overload)])
        self._flush()

    def close(self) -> None:
        self._fh.close()


def _call(hook, *args) -> None:
    if hook is not None:
        hook(*args)


def _best_effort(fn: Callable[[], None], what: str) -> None:
    try:
        fn()
    except Exception:
        log.exception("shutdown step failed: %s", what)


def run_sequence(
    sites: Iterable[Site],
    mux: Mux,
    dmm: DMM,
    prober: Prober,
    writer: ResultWriter,
    settle_s: float = 0.05,
    hooks: Optional[Hooks] = None,
    skip: Optional[set[str]] = None,
) -> int:
    """Measure every site not in `skip`. Returns the number of sites measured.

    Whatever happens (error, Ctrl-C, SIGTERM turned into KeyboardInterrupt), the mux
    is opened and the chuck lowered to separation before this function exits.
    """
    hooks = hooks or Hooks()
    skip = skip or set()
    measured = 0
    current: Optional[Site] = None
    try:
        mux.open_all()
        for site in sites:
            if site.site_id in skip:
                log.info("skipping %s (already complete)", site.site_id)
                continue
            current = site
            _call(hooks.before_move, site)
            prober.move_to(site.x, site.y)
            prober.touchdown()
            _call(hooks.after_touchdown, site)
            rows: list[Result] = []
            for hi, lo in PIN_PAIRS:
                mux.select(hi, lo)
                time.sleep(settle_s)
                reading = dmm.read_ohms()
                mux.open_all()
                result = Result(
                    datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    site.site_id, site.x, site.y, hi, lo, reading.ohms, reading.overload,
                )
                rows.append(result)
                _call(hooks.after_measurement, result)
            writer.write_all(rows)
            prober.lift()
            measured += 1
            log.info("site %s done", site.site_id)
            current = None
    except BaseException as exc:
        if current is not None:
            log.error("aborted at site %s; its rows were not written", current.site_id)
        if hooks.on_error is not None:
            _best_effort(lambda: hooks.on_error(current, exc), "on_error hook")
        raise
    finally:
        _best_effort(mux.open_all, "open mux")
        _best_effort(prober.lift, "lift chuck")
    return measured
