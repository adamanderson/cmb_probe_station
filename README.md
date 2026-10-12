# probestation

Pi-side orchestration for the CM300xi resistance measurements: for each site in a
sites file, move the chuck, touch down, measure the six unique pin pairs of the 4-pin
probe card through the ADG729 with the 34401A, and write raw ohms plus an overload flag.

## Layout

| File | Role |
| --- | --- |
| `probestation/mux.py` | ADG729 driver (smbus2, one byte per write) + `MockMux` |
| `probestation/dmm.py` | 34401A over RS-232 (SCPI) + `MockDMM` |
| `probestation/prober.py` | `Prober` interface, `VeloxProber` (SCI commands), `MockProber`, transport stub |
| `probestation/sequence.py` | the measurement loop, hooks, CSV writer, resume logic |
| `probestation/run.py` | CLI: `run` and `selftest`, run lock, signal handling |
| `config.example.toml`, `sites.example.csv` | example inputs |

## Use

```
pip install -r requirements.txt            # on the Pi; dry runs need none of it
python -m probestation --dry-run selftest   # mock devices, touches no hardware
python -m probestation --dry-run run --sites sites.example.csv --out demo.csv
python -m probestation --config my.toml selftest           # real mux + meter, no prober
python -m probestation --config my.toml run --sites sites.csv --out wafer1.csv
python -m probestation --config my.toml run --sites sites.csv --out wafer1.csv --resume
python -m pytest                            # tests (no hardware needed)
```

Run inside `tmux` or `screen` so a dropped SSH session does not matter; SIGHUP and
SIGTERM still run the safe shutdown (mux opened, chuck lowered to separation).

## Sites file and output

`sites.csv`: `site_id,x,y`. One row = one chuck position = one touchdown of the card.
Coordinates are sent to Velox's `MoveChuck` using `posref` and `unit` from the config.

Output columns: `timestamp, site_id, x, y, hi_pin, lo_pin, ohms, overload`. `ohms` is
blank when the meter overloads (open input). A site's six rows are written together,
so a site in the file is always complete; if a run aborts mid-site, that site's rows
are discarded and `--resume` measures it again.

## Hooks

`Hooks` in `sequence.py` has optional `before_move`, `after_touchdown`,
`after_measurement` and `on_error` callbacks, passed to `run_sequence`.

## Still to do / verify before a real run

1. **ADG729 bit mapping.** `a_bits`/`b_bits` in the config assume bits 0-3 are 1A-4A
   and bits 4-7 are 1B-4B. Check the datasheet, then run `selftest` with a known
   resistor between two pins; a wrong mapping shows up as overload or wrong pairs.
2. **34401A serial setup.** Match the front-panel I/O menu to the config (factory:
   9600 baud, even parity / 7 data bits, 2 stop bits). The meter is a DTE device, so
   the USB-serial adapter needs a null-modem (DTE-to-DTE) cable; DTR/DSR handshaking
   is on by default.
3. **Velox transport.** `prober.SocketTransport.send()` is a stub: choose SCI over
   TCP/IP or a bridge script on the Velox PC. `VeloxProber` assumes each response
   starts with an integer error code (0 = success) -- confirm against real responses.
   Contact height must already be set in Velox.
4. **Meter open-circuit voltage** is not in the 34401A manual; measure it before
   connecting the mux (see the hardware doc).
