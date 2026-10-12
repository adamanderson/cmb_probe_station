# probestation: CM300xi resistance-measurement automation

Python package for a Raspberry Pi 3B. For each site in a sites file it moves the CM300xi
chuck (through Velox on a Windows PC), touches down a 4-pin probe card, measures all 6
unique pin pairs through an ADG729 mux with an Agilent 34401A DMM, and logs raw ohms.
Goal: tell open from shorted structures at a very low test level (wafer resistances are
about 2-20 kOhm). The Velox-side setup (touchdown parameters, pad finding, bondpad
coordinate calibration) is being done by hand by the user, in parallel.

## Read first
@docs/hardware.md
@docs/decisions.md

Read on demand (not imported, they are long): `docs/reference-notes.md` (facts taken from
the 34401A and Velox manuals, with what is verified vs assumed) and `docs/manuals/`
(the PDFs; search them with `pdftotext`, do not read them whole).

## Code map
| File | Role |
| --- | --- |
| `probestation/mux.py` | ADG729 driver (smbus2, one byte per write) + `MockMux` |
| `probestation/dmm.py` | 34401A over RS-232/SCPI + `MockDMM` |
| `probestation/prober.py` | `Prober` interface, `VeloxProber` (SCI commands), `MockProber`, `SocketTransport` stub |
| `probestation/sequence.py` | measurement loop, hooks, CSV writer, resume |
| `probestation/run.py` | CLI (`run`, `selftest`), run lock, signal handling |
| `probestation/config.py` | dataclass config loaded from TOML |

## Commands
- `python -m pytest` (no hardware needed)
- `python -m probestation --dry-run selftest`
- `python -m probestation --dry-run run --sites sites.example.csv --out demo.csv`
- Real mux + meter, no prober: `python -m probestation --config my.toml selftest`

## Working rules
- **Hardware safety.** Develop against the mocks. Do not run anything non-dry-run, and
  never send motion commands to the real station, without the user's explicit go-ahead
  in that session. Chuck motion can crash the probes into the wafer.
- **Never invent instrument or Velox syntax.** Check `docs/reference-notes.md` and the
  manuals; if something is unverified, say so in a code comment and in the README's
  "Still to do" list.
- **All Velox knowledge stays in `prober.py`.** The rest of the code must not know how
  Velox is reached or what its commands look like.
- **Mux safety.** Never connect HI and LO to the same pin (iA with iB is a false short;
  `_check_pins` enforces it). Always `open_all()` between measurements and on exit.
- **Meter.** Fixed 100 kOhm range, never autorange. Overload is a reading of 9.9E37,
  recorded as a blank `ohms` plus `overload=1`; there are no pass/fail thresholds.
- **Tests run without hardware.** `pyserial` and `smbus2` are imported lazily; keep it so.
- **Python 3.9+ on the Pi.** Keep `from __future__ import annotations` at the top of modules.
  `tomli` is the fallback where `tomllib` is missing.
- Use `logging`, not `print`, except for the `selftest` table.

## Open items (details in docs/decisions.md)
1. ADG729 bit mapping (`a_bits`/`b_bits`) is an assumption; confirm from the datasheet and with `selftest`.
2. Velox transport is a stub: choose SCI over TCP/IP or a bridge script on the Velox PC, then implement `SocketTransport.send()`. `VeloxProber` assumes each response starts with an integer error code (0 = success): confirm.
3. Decide `posref` for the sites file coordinates (default `Z`, microns) and confirm the contact height is set in Velox.
4. Measure the 34401A's open-circuit voltage on the 100 kOhm range (not in its manual); above about 3 V the ADG729 needs a 5 V supply or input protection.
5. Decide how to tie the 34401A's Input LO to the mux ground.
6. Confirm the Velox PC has a free network port for the private link to the Pi.
7. The USB Ethernet dongle is not bought yet. Candidate: StarTech USB31000S2 (Realtek RTL8153 per the retailer): check `lsusb` shows `0bda:8153` on arrival.
