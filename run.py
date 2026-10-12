"""Command line: `python -m probestation run|selftest ...`"""
from __future__ import annotations

import argparse
import fcntl
import logging
import signal
import sys
from contextlib import ExitStack, contextmanager
from datetime import datetime

from .config import Config, load_config
from .dmm import Keysight34401A, MockDMM
from .mux import ADG729, MockMux
from .prober import MockProber, SocketTransport, VeloxProber
from .sequence import PIN_PAIRS, ResultWriter, completed_sites, load_sites, run_sequence

log = logging.getLogger("probestation")


@contextmanager
def run_lock(path: str):
    """Only one process may drive the prober at a time (several users can SSH in)."""
    fh = open(path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        raise SystemExit(f"Another run is already in progress (lock file {path}).")
    try:
        yield
    finally:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def _turn_signals_into_exceptions() -> None:
    """So a dropped SSH session or `kill` still runs the safe-shutdown code."""

    def handler(signum, frame):
        raise KeyboardInterrupt(f"received signal {signum}")

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGHUP, handler)


@contextmanager
def open_devices(cfg: Config, dry_run: bool, with_prober: bool):
    with ExitStack() as stack:
        if dry_run:
            mux = MockMux()
            dmm = MockDMM(mux)
            prober = MockProber() if with_prober else None
        else:
            mux = ADG729(cfg.mux)
            stack.callback(mux.close)
            dmm = Keysight34401A(cfg.dmm)
            stack.callback(dmm.close)
            prober = None
            if with_prober:
                p = cfg.prober
                prober = VeloxProber(SocketTransport(p.host, p.port), p.posref, p.unit, p.velocity)
                stack.callback(prober.close)
        dmm.configure()
        yield mux, dmm, prober


def cmd_run(args, cfg: Config) -> int:
    sites = load_sites(args.sites)
    if args.resume and not args.out:
        raise SystemExit("--resume needs --out pointing at the earlier results file")
    out = args.out or f"results_{datetime.now():%Y%m%d_%H%M%S}.csv"
    skip = completed_sites(out) if args.resume else set()
    with run_lock(cfg.run.lock_file), open_devices(cfg, args.dry_run, True) as (mux, dmm, prober):
        writer = ResultWriter(out)
        try:
            n = run_sequence(sites, mux, dmm, prober, writer, cfg.run.settle_s, skip=skip)
        finally:
            writer.close()
    log.info("measured %d site(s); results in %s", n, out)
    return 0


def cmd_selftest(args, cfg: Config) -> int:
    """Sweep the six pin pairs and print what the meter reads (no prober needed)."""
    with run_lock(cfg.run.lock_file), open_devices(cfg, args.dry_run, False) as (mux, dmm, _):
        try:
            for hi, lo in PIN_PAIRS:
                mux.select(hi, lo)
                reading = dmm.read_ohms()
                mux.open_all()
                shown = "overload (open)" if reading.overload else f"{reading.ohms:.6g} ohm"
                print(f"pins {hi}-{lo}: {shown}")
        finally:
            mux.open_all()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="probestation")
    parser.add_argument("--config", help="TOML config file (defaults are used if omitted)")
    parser.add_argument("--dry-run", action="store_true", help="use mock devices; touches no hardware")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="one pass over a sites file")
    p_run.add_argument("--sites", required=True, help="CSV with columns site_id,x,y")
    p_run.add_argument("--out", help="results CSV (default: results_<timestamp>.csv)")
    p_run.add_argument("--resume", action="store_true", help="skip sites already complete in --out")
    p_run.set_defaults(func=cmd_run)
    p_test = sub.add_parser("selftest", help="read all six pin pairs through the mux")
    p_test.set_defaults(func=cmd_selftest)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _turn_signals_into_exceptions()
    return args.func(args, load_config(args.config))


if __name__ == "__main__":
    sys.exit(main())
