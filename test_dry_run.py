import csv

import pytest

from probestation.dmm import MockDMM
from probestation.mux import MockMux
from probestation.prober import MockProber
from probestation.sequence import (
    PIN_PAIRS, Hooks, ResultWriter, Site, completed_sites, load_sites, run_sequence,
)

SITES = [Site("A01", 1.0, 2.0), Site("A02", 3.0, 4.0)]


def rows(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def run(tmp_path, sites=SITES, dmm_cls=MockDMM, skip=None, hooks=None, name="out.csv"):
    mux, prober = MockMux(), MockProber()
    out = tmp_path / name
    writer = ResultWriter(str(out))
    try:
        n = run_sequence(sites, mux, dmm_cls(mux), prober, writer, settle_s=0, hooks=hooks, skip=skip)
    finally:
        writer.close()
    return n, mux, prober, out


def test_six_unique_pairs_per_site(tmp_path):
    n, mux, prober, out = run(tmp_path)
    assert n == 2
    r = rows(out)
    assert len(r) == 12
    for site in ("A01", "A02"):
        pairs = {(int(x["hi_pin"]), int(x["lo_pin"])) for x in r if x["site_id"] == site}
        assert pairs == set(PIN_PAIRS)
    assert mux.pair is None  # left open


def test_overload_flag_and_blank_ohms(tmp_path):
    _, _, _, out = run(tmp_path)
    r = {(int(x["hi_pin"]), int(x["lo_pin"])): x for x in rows(out) if x["site_id"] == "A01"}
    assert r[(1, 4)]["overload"] == "1" and r[(1, 4)]["ohms"] == ""
    assert r[(1, 2)]["overload"] == "0" and float(r[(1, 2)]["ohms"]) == 5000.0


def test_motion_order(tmp_path):
    _, _, prober, _ = run(tmp_path, sites=SITES[:1])
    assert prober.events[:3] == [("move", 1.0, 2.0), ("touchdown",), ("lift",)]


class FailingDMM(MockDMM):
    def __init__(self, mux):
        super().__init__(mux)
        self.calls = 0

    def read_ohms(self):
        self.calls += 1
        if self.calls == 8:  # second site, second pair
            raise RuntimeError("meter fell over")
        return super().read_ohms()


def test_error_leaves_hardware_safe_and_keeps_finished_sites(tmp_path):
    seen = []
    hooks = Hooks(on_error=lambda site, exc: seen.append((site.site_id, str(exc))))
    mux, prober = MockMux(), MockProber()
    out = tmp_path / "out.csv"
    writer = ResultWriter(str(out))
    with pytest.raises(RuntimeError):
        run_sequence(SITES, mux, FailingDMM(mux), prober, writer, settle_s=0, hooks=hooks)
    writer.close()
    assert mux.pair is None
    assert prober.events[-1] == ("lift",)
    assert {x["site_id"] for x in rows(out)} == {"A01"}
    assert seen == [("A02", "meter fell over")]


def test_keyboard_interrupt_is_safe(tmp_path):
    class Interrupting(MockDMM):
        def read_ohms(self):
            raise KeyboardInterrupt

    mux, prober = MockMux(), MockProber()
    writer = ResultWriter(str(tmp_path / "o.csv"))
    with pytest.raises(KeyboardInterrupt):
        run_sequence(SITES, mux, Interrupting(mux), prober, writer, settle_s=0)
    writer.close()
    assert mux.pair is None and prober.events[-1] == ("lift",)


def test_resume_skips_complete_sites(tmp_path):
    _, _, _, out = run(tmp_path, sites=SITES[:1])
    assert completed_sites(str(out)) == {"A01"}
    mux, prober = MockMux(), MockProber()
    writer = ResultWriter(str(out))
    n = run_sequence(SITES, mux, MockDMM(mux), prober, writer, settle_s=0, skip=completed_sites(str(out)))
    writer.close()
    assert n == 1
    assert len(rows(out)) == 12


def test_mux_refuses_same_pin_and_bad_pins():
    mux = MockMux()
    with pytest.raises(ValueError):
        mux.select(2, 2)
    with pytest.raises(ValueError):
        mux.select(0, 1)
    with pytest.raises(ValueError):
        mux.select(1, 5)


def test_load_sites(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text("site_id,x,y\nA,1,2\nB,3.5,4\n")
    assert load_sites(str(p)) == [Site("A", 1.0, 2.0), Site("B", 3.5, 4.0)]
    p.write_text("site_id,x,y,theta\nA,1,2,30\nB,3,4,\n")
    assert load_sites(str(p)) == [Site("A", 1.0, 2.0, 30.0), Site("B", 3.0, 4.0, None)]
    p.write_text("site_id,x,y\nA,1,2\nA,3,4\n")
    with pytest.raises(ValueError):
        load_sites(str(p))
    p.write_text("id,x,y\nA,1,2\n")
    with pytest.raises(ValueError):
        load_sites(str(p))
