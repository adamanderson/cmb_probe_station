# Design decisions

Each entry: what was decided, and why. Status is current as of 2026-10-12.

## Hardware and links
- **LAN link to Velox, not GPIB.** Velox's GPIB interface needs a National Instruments GPIB board and NI-488.2 drivers on the Velox PC, with the Pi as bus controller through a USB adapter, which means linux-gpib on the Pi (fiddly). The prober also has an Ethernet port. SCI works over TCP/IP; the legacy SCPI command set does not. The Keysight 82357 GPIB adapter on hand is not used.
- **Pi networking.** Built-in Ethernet stays on the lab network (SSH). A USB Ethernet dongle gives a direct private link to the Velox PC, so prober control is isolated from the lab network. Static addresses, no gateway (proposed: Pi 192.168.50.1, Velox PC 192.168.50.2).
- **Dongle chip.** Avoid ASIX AX88179A/B and AX88772D/E: they share USB ID `0b95:1790` (bcdDevice 2.00 / 3.00) and, as of Oct 2026, mainline Linux support was still a patch series under review. Prefer Realtek RTL8152/8153 (`r8152`) or older ASIX AX88772A/B/C (`asix`). Candidate: StarTech USB31000S2 (RTL8153 per the retailer); verify with `lsusb` (`0bda:8153`) and `ethtool -i`. 10/100 is plenty: the Pi 3B has USB 2.0 anyway.
- **Meter is the Agilent 34401A** (6.5-digit DMM), not a Keithley 2400. Controlled over RS-232 through a USB-serial converter.
- **2-wire resistance.** Resistances are about 2-20 kOhm and only open vs shorted matters, so a few ohms of mux and cable resistance is irrelevant.
- **ADG729 is a matrix of 8 independent switches** (per Adafruit): DA reaches any of 1A-4A, DB any of 1B-4B. Meter HI goes to DA, LO to DB, and probe pin n goes to both nA and nB. Measure between pins i and j by closing iA and jB only.

## Meter settings
- **Fixed 100 kOhm range (10 uA test current), never autorange.** It covers 2-20 kOhm with about 1.2 V at full scale, and autoranging an open pad steps through ranges with more test current.
- **Open-circuit voltage is unknown** (not in the manual). It must be measured; the ADG729's signals must stay within its supply rails.

## Pi software
- **Custom ADG729 driver on smbus2**, not the Adafruit package. The protocol is one byte (bit n set = switch n closed, 0x00 = all open). The Adafruit class also defaults to the ADG728's address 0x4C and drags in Blinka. The bit-to-switch mapping (which bit is 1A vs 1B) is **assumed** as bits 0-3 = 1A-4A, 4-7 = 1B-4B; confirm from the datasheet and with `selftest` on a known resistor.
- **All 6 unique pin pairs (i < j) at every touchdown.** A site = one chuck position = one touchdown of the whole 4-pin card, not one pad.
- **Output: raw ohms plus an overload flag, no pass/fail thresholds.** Columns: `timestamp, site_id, x, y, hi_pin, lo_pin, ohms, overload`; `ohms` blank on overload.
- **Explicit chuck (x, y) coordinates first.** Sites come from a CSV (`site_id,x,y`). The user may later move wafer-layout knowledge into Velox's wafer map; that change should touch only `prober.py` and how the sites file is produced, not the measurement loop.
- **One invocation = one pass over the sites file.** For repeated passes, run again.
- **A site's six rows are written together**, so a site in the output file is always complete. If a run aborts mid-site, that site's rows are discarded; `--resume` re-measures it.
- **Safe shutdown.** Whatever happens (error, Ctrl-C, SIGHUP/SIGTERM turned into KeyboardInterrupt), the mux is opened and the chuck lowered to separation. A lockfile allows only one run at a time (several users can SSH in). Run inside tmux or screen.
- **Hooks**: optional `before_move`, `after_touchdown`, `after_measurement`, `on_error` callbacks in `sequence.Hooks`.
- **Everything runs in dry-run mode** with mocks (`MockMux`, `MockDMM`, `MockProber`) so it can be developed and tested without hardware.

## Open decisions
- Velox transport: SCI over TCP/IP vs a bridge script on the Velox PC. `SocketTransport` is a stub.
- `posref` and units for the sites-file coordinates (default `Z` = zero, microns).
- How to tie the 34401A's Input LO to the mux ground.
