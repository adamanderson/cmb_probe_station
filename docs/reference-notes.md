# Reference notes from the manuals

Facts taken from the manuals during design, so they need not be re-derived. "Verified" means
read in the manual; "Assumed" means not confirmed. Re-check a quoted syntax against the PDF
in `docs/manuals/` before relying on it for anything safety-relevant.

## Agilent/Keysight 34401A (HP 34401A User's Manual, 34401-90004)
**RS-232 (verified)**
- DB-9 rear connector; the meter is a **DTE** device, so a **null-modem (DTE-to-DTE) cable** is needed.
- Baud: 300, 600, 1200, 2400, 4800 or 9600 (factory 9600). Parity/data bits: None/8, Even/7 (factory), Odd/7. **2 stop bits and 1 start bit are fixed.** Baud and parity are set only from the front-panel I/O menu and must match the host.
- **DTR/DSR handshake**: the meter will not accept data unless DTR is true. To disable it, leave DTR unconnected and tie DSR true, and then use 300-1200 baud. pyserial: `dsrdtr=True`.
- **Every command must end with a newline.** After a query, read the response before sending more.
- **`SYSTem:REMote` must be sent first** to enter remote mode; `SYSTem:LOCal` returns the front panel.
- Do not use RS-232 if the meter is configured to output pass/fail signals on pins 1 and 9 (can damage the RS-232 circuitry).
- Reading rate to RS-232 is about 55/s at 4.5 digits (spec table).

**SCPI used (verified in the command reference)**
- `CONFigure:RESistance <range>` (2-wire ohms), `RESistance:NPLCycles {0.02|0.2|1|10|100}`, `READ?`, `SYSTem:ERRor?`, `*RST`, `*CLS`, `*OPC?`.

**Resistance measurement (verified)**
- Test current by range: 100 ohm 1 mA, 1 kohm 1 mA, 10 kohm 100 uA, **100 kohm 10 uA**, 1 Mohm 5 uA, 10 Mohm 500 nA, 100 Mohm 500 nA in parallel with 10 Mohm. 20% overrange on all ranges.
- The current source is referenced to the LO input; the test current flows out of Input HI.
- 2-wire accuracy specs assume Math Null; without it add 0.2 ohm of error. 4-wire is not used here.
- **The manual gives no open-circuit voltage or compliance spec** for the resistance ranges. Measure it with a second DMM on the open leads (100 kohm and 10 kohm ranges).
- Overload reads **9.90000000E+37** over the remote interface. An overload sets bit 3 of the standard event register but **adds nothing to the error queue**, so `SYST:ERR?` stays clean after open-circuit reads.
- Input protection is 1000 V on all ranges (protects the meter, says nothing about the terminal output).

## Velox (Remote Interface Guide and Kernel command reference)
**Interfaces (verified)**
- SCI (System Control Interface) is the main remote command set; commands and responses are ASCII, space-separated, not case sensitive.
- The Velox **GPIB** interface requires an NI GPIB board and NI-488.2 drivers on the Velox PC; Velox appears as a device (default address 22). The Pi would be the controller.
- **SCPI is legacy and is not supported through the Scripting Console or TCP/IP**; use SCI. The TCP/IP transport details (port, framing) are **not yet found**: look in the Velox User Guide / Remote Interface Guide.
- The Scripting Console runs Python (IronPython-based) with a `velox` module in which each SCI command is a function of the same name.
- Responses start with an error code (the guide says "every remote command returns a Response string, starting with an error code"). `VeloxProber` **assumes** the form `<int>:` or `<int> ...` with 0 = success: **confirm on a real response.**
- Resetting the PC or Message Server can lose settings such as Contact Height: re-check them first.
- GPIB only: `$StartCommand <command>` runs a long command on a separate thread; `$CommandStatus` returns `$BUSY` until it finishes.
- Selected error codes: 615 Timeout During Command Execution, 602 Not in Remote Mode, 605 No Current Project.

**Chuck commands used (verified syntax)**
- `MoveChuck XValue YValue [PosRef] [Unit] [Velocity] [Comp]`: XY move. PosRef: `H` home (default), `Z` zero, `C` center, `R` relative, `D` die home. Unit: `Y` microns (default), `I` mils, `J` jogs, `E` encoder, `X` index. Velocity default 100 (percent). Comp: `T` technology (default), `N`, `P`, `O`. Example: `MoveChuck 5000. 5000. R Y 100`. If chuck Z is at or above contact height, the Interlock and Auto Z flags decide whether it separates first or returns an error, so always separate before moving.
- `MoveChuckContact [Velocity]`: chuck Z to the preset contact height; error if none is set.
- `MoveChuckSeparation [Velocity]`: chuck Z to the separation height; error if no contact height.
- Also exist: `ReadChuckPosition`, `ReadChuckStatus`, `ReadChuckHeights`, `StopChuckMovement`, `SearchChuckContact`, `SetChuckHeight`, `MoveChuckZ`, `MoveChuckZSafe`, `MoveChuckIndex`. `MoveChuckLift` is the load/unload lift, not the touchdown, and only initiates motion.

## Adafruit ADG729 breakout (Adafruit product guide; `adafruit_adg72x` driver source v1.0.7)
- A matrix switch with 8 independent switches, not a selecting mux: DA connects to 1A-4A, DB to 1B-4B. Break-before-make is guaranteed; switch time is about 100 ns. Default I2C address 0x44 (two address pins, 0x44-0x47). Analog signals must stay within the supply; not for power.
- Driver protocol (verified from source): one byte written to the device, bit n = switch n (0-7), 1 = closed, `0x00` = all open. The mapping of bits to 1A-4A/1B-4B is not stated in the driver; **assumed** 0-3 = A, 4-7 = B.

## Linux USB Ethernet (searched Oct 2026)
- ASIX AX88179A/B/AX88772D/E/AX88279 share USB ID `0b95:1790` and differ by bcdDevice (2.00 = AX88179A/B, 3.00 = AX88772D/E, 4.00 = AX88279). The mainline `ax88179_178a` driver covered only the older AX88179/AX88178A; a patch series to add the newer family was at v11 and under review. Not confirmed merged.
- Realtek RTL8152/8153 use the in-kernel `r8152` driver (they may bind `cdc_ether` on some kernels; both work for this use).
