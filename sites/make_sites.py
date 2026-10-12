"""Convert the wafer designers' pad file into a touchdown sites file (site_id,x,y).

Pads come in +/- pairs ("B00+", "B00-"). Within a group (Grouptype, GroupIndex,
Group Section) the pairs are taken in file order, and the 4-pin card covers two
adjacent pairs per touchdown, so a group of 25 pairs gives 24 sites: (0,1), (1,2), ...

Each site also gets a rotation `theta` (degrees, counter-clockwise, wafer frame): the
direction of the vector from the "+" pad of the first pair to the "+" pad of the second
pair, plus --theta-offset. This assumes the card's pin row lies along that vector; if the card's
native orientation differs, set --theta-offset. How this maps to the chuck's theta (sign,
zero, rotation of XY about the chuck centre) depends on the Velox calibration.

Usage: python sites/make_sites.py sites/example_pads.csv sites.csv [--group-size 25] [--theta-offset 0]
"""
from __future__ import annotations

import argparse
import csv
import logging
import math
import sys
from collections import OrderedDict

log = logging.getLogger("make_sites")

GROUP_KEYS = ("Grouptype", "GroupIndex", "Group Section")


def read_groups(path):
    """Return {group_key: OrderedDict(pair_stem -> [(label, x, y), ...])}, in file order."""
    groups = OrderedDict()
    with open(path, newline="", encoding="utf-8-sig") as f:  # files carry a BOM
        for row in csv.DictReader(f):
            key = tuple(row[k].strip() for k in GROUP_KEYS)
            label = row["Pad Label"].strip()
            stem = label.rstrip("+-")  # "B00+" and "B00-" form one pair
            pad = (label, float(row["Pad X center"]), float(row["Pad Y center"]))
            groups.setdefault(key, OrderedDict()).setdefault(stem, []).append(pad)
    return groups


def wrap_degrees(a):
    """Wrap an angle to (-180, 180]."""
    a = math.fmod(a, 360.0)
    if a <= -180.0:
        a += 360.0
    elif a > 180.0:
        a -= 360.0
    return a


def plus_axis(first, second):
    """Angle in degrees of the vector from the '+' pad of `first` to the '+' pad of `second`."""
    p1 = next(p for p in first if p[0].endswith("+"))
    p2 = next(p for p in second if p[0].endswith("+"))
    return math.degrees(math.atan2(p2[2] - p1[2], p2[1] - p1[1]))


def make_sites(groups, group_size, theta_offset=0.0):
    """Yield (site_id, x, y, theta): (x, y) is the centroid of the 4 pads under the card."""
    for key, pairs in groups.items():
        name = "".join(key)
        bad = [s for s, pads in pairs.items() if len(pads) != 2]
        if bad:
            raise ValueError(f"group {name}: pairs without exactly 2 pads: {bad}")
        if len(pairs) != group_size:
            log.warning("group %s has %d pairs, expected %d", name, len(pairs), group_size)
        stems = list(pairs)
        for i in range(len(stems) - 1):
            pair_pads = (pairs[stems[i]], pairs[stems[i + 1]])
            pads = pair_pads[0] + pair_pads[1]
            x = sum(p[1] for p in pads) / 4
            y = sum(p[2] for p in pads) / 4
            theta = wrap_degrees(plus_axis(*pair_pads) + theta_offset)
            yield f"{name}_{stems[i]}_{stems[i + 1]}", x, y, theta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pads")
    ap.add_argument("out")
    ap.add_argument("--group-size", type=int, default=25, help="expected pairs per group")
    ap.add_argument("--theta-offset", type=float, default=0.0,
                    help="degrees added to the pad-axis angle (card's native orientation)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    sites = list(make_sites(read_groups(args.pads), args.group_size, args.theta_offset))
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "x", "y", "theta"])
        for site_id, x, y, theta in sites:
            w.writerow([site_id, f"{x:.3f}", f"{y:.3f}", f"{theta:.2f}"])
    log.info("wrote %d sites to %s", len(sites), args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
