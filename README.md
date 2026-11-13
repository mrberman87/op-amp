# Discrete Operational Amplifier — Two-Stage, LCSC-sourced (Rev E)

A **discrete-component operational amplifier** built only from parts LCSC
stocks. No op-amp ICs: transistors, resistors and capacitors.

Rev E adds a **second gain stage** to Rev D. That is what makes the 60 dB
requirement reachable: the single-stage Rev D topped out at 58.5 dB because
the BFP420's Early voltage (`VAF = 28.4 V`) sets its intrinsic gain at
~60.7 dB. The second stage raises the **open-loop** gain to ~110 dB, so a
60 dB closed loop has ~50 dB of loop gain, and the Miller capacitor sets the
bandwidth.

---

## 1. Target vs. achieved

| Parameter | Target | Rev E | Verdict |
|---|---|---|---|
| Closed-loop gain | 60 dB (1000 V/V) | **59.9 dB** | met |
| −3 dB bandwidth | DC → 10 MHz | **DC → 11.5 MHz** | met |
| Gain at 10 MHz | 60 dB | **58.0 dB** (−2 dB) | ~met |
| Open-loop gain | — | **~110 dB** | — |
| Phase margin | > 45° | **~65°** (no closed-loop peaking) | met |
| Output stage | push-pull | **class-AB complementary** | met |
| Supplies | ±15 V | ±15 V | — |
| ERC | clean | **0 errors / 0 warnings** | met |
| Device stress | no overstress | **no VCEO or >50 % Pd violations** | met |

The closed-loop response is flat (no peaking) from DC to ~1 MHz, −2 dB at
10 MHz, −3 dB at 11.5 MHz. The low-frequency gain is 59.4 dB at 0.01 Hz,
so the AC bypass in stage 2 does **not** introduce an audio-band rolloff in
closed loop.

---

## 2. Topology

```
 IN+ ─┐
      ├─ Q1/Q2 BFP420 diff pair ── Q4/Q6 MMBTH81 mirror ── c2
 IN− ─┘   (Q3 ref-side cascode)    (Q5/Q7 cascodes, Q8 helper)
                                                             │
                        ┌────────────────────────────────────┘
                        ▼
                  Q11 buffer (BFP420 + Q12 cascode) ── d1
                                                             │
                        ┌────────────────────────────────────┘
                        ▼
                  Q13 stage-2 CE (BFP420), R19 load, R20/C6 emitter
                                                             │
                        C7 = 68 p Miller compensation ───────┤
                                                             │
                        ┌────────────────────────────────────┘
                        ▼
                  Q14 buffer (BFP420 + Q15 cascode) ── d3
                                                             │
                        ┌────────────────────────────────────┘
                        ▼
                  Q16/Q18 class-AB push-pull (BFP420 / MMBTH81)
                  Q19 Vbe multiplier, R17 = 47 Ω isolation ── OUT
```

**Why stage 2 is a CE with a bypassed emitter.** A common-emitter stage
needs its emitter at AC ground to have gain. The DC bias needs a defined
current, so the emitter resistor `R20 = 50 Ω` is bypassed by `C6 = 220 µF`.
The bypass corner is ~15 Hz in **open loop**, but the closed-loop 60 dB
response stays flat because the open-loop gain at low frequency (~85 dB) is
still far above 60 dB. The measured closed-loop gain is 59.4 dB at 0.01 Hz.

**Miller compensation.** `C7 = 68 pF` from d1 to d2 sets the dominant pole.
Sweeping it gives the trade-off:

| C7 | closed-loop gain | peaking | f−3dB |
|---|---|---|---|
| 22 pF | 59.9 dB | 3.7 dB | 27.6 MHz |
| 47 pF | 59.9 dB | 0.6 dB | 16.2 MHz |
| **68 pF** | **59.9 dB** | **0 dB** | **11.5 MHz** |
| 100 pF | 59.9 dB | 0 dB | 7.4 MHz |

---

## 3. Devices and LCSC part numbers

| Part | Type | fT | VCEO | Package | LCSC |
|---|---|---|---|---|---|
| BFP420H6327 | NPN | 25 GHz | 4.5 V | SOT-343 | **C412737** |
| MMBTH81 | PNP | 600 MHz | 20 V | SOT-23 | **C190349** |
| MMBT3904 | NPN | 300 MHz | 40 V | SOT-23 | **C20526** |

`BFP420` is a **4.5 V** part, so every BFP420 is cascoded on ±15 V:

- Q1 (input pair, reference side) → Q3
- Q11 (buffer 1) → Q12
- Q13 (stage 2) runs at Vce ≈ 1.9 V, safe
- Q14 (buffer 2) → Q15
- Q16 (output NPN) → Q17

The MMBTH81 mirror/cascode/helper/output-PNP sees ≤ 15.8 V, inside its 20 V
rating.

### Reference designators

| Ref | Role | Part |
|---|---|---|
| Q1, Q2 | input differential pair | BFP420 |
| Q3 | reference-side cascode | MMBT3904 |
| Q4, Q6 | PNP mirror | MMBTH81 |
| Q5, Q7 | mirror cascodes | MMBTH81 |
| Q8 | regulated-cascode helper | MMBTH81 |
| Q9 | bias-reference diode | MMBT3904 |
| Q10 | tail current source | MMBT3904 |
| Q11 | buffer 1 | BFP420 |
| Q12 | buffer-1 cascode | MMBT3904 |
| Q13 | **stage-2 CE gain** | BFP420 |
| Q14 | buffer 2 | BFP420 |
| Q15 | buffer-2 cascode | MMBT3904 |
| Q16 | output NPN | BFP420 |
| Q17 | output-NPN cascode | MMBT3904 |
| Q18 | output PNP | MMBTH81 |
| Q19 | Vbe multiplier (class-AB bias) | MMBT3904 |
| R1 | bias reference 13.7k | 0603 |
| R2 | bias emitter 1k | 0603 |
| R3 | tail emitter 180 | 0603 |
| R4 | `vcn` divider top 6.8k | 0603 |
| R5 | mirror-ref degeneration 22 | 0603 |
| R6 | helper load 22k | 0603 |
| R7 | load 10k | 0603 |
| R8 | mirror-out degeneration 20 | 0603 |
| R9 | `vcn` divider bottom 8.2k | 0603 |
| R10 | `vcd` divider top 6.8k | 0603 |
| R11 | `vcd` divider bottom 11k | 0603 |
| R12 | Vbe multiplier top 1.8k | 0603 |
| R13 | Vbe multiplier bottom 1.2k | 0603 |
| R14 | PNP base pull-down 10k | 0603 |
| R15 | output NPN emitter 4.7 | 0603 |
| R16 | output PNP emitter 4.7 | 0603 |
| R17 | output isolation 47 | 0603 |
| R18 | tail collector 470 | 0603 |
| **R19** | **stage-2 collector load 1k** | **1206** |
| R20 | stage-2 emitter 50 | 0603 |
| C1, C2 | rail decoupling at J1 100n | 0603 |
| C11, C12 | rail bulk at J1 10 µF, ≥25 V X5R | 1206 |
| C8, C9 | output-collector decoupling (Q17 / Q18) 100n | 0603 |
| C10 | vcd bypass at Q12's base 100n | 0603 |
| C3 | Vbe bypass 100n | 0603 |
| C4, C5 | cascode-bias bypass 100n | 0603 |
| C6 | stage-2 emitter bypass 220 µF | 6.3×5.4 mm |
| C7 | Miller compensation 68 pF | 0603 |
| J1 | I/O header | 1×6, 2.54 mm |

---

## 4. Results (`sim/rf_two_stage.py`)

Closed-loop non-inverting, `Rf = 10 kΩ`, `Rg = 10 Ω` (gain = 1001):

| Quantity | Value |
|---|---|
| Closed-loop gain | **59.91 dB** |
| Peaking | **0 dB** |
| f−3dB | **11.47 MHz** |
| Gain at 10 MHz | **57.96 dB** |
| Gain at 0.01 Hz | 59.42 dB |
| Open-loop gain | ~110 dB |

### Device stress

`sim/stress_two.py` checks every junction and every resistor's dissipation.
All transistors are inside their VCEO and below 50 % of their Pd rating; all
resistors are below the 75 % chip-resistor derating. The hottest parts:

| Device | Vce | Pd | Rating |
|---|---|---|---|
| Q13 (stage-2 CE) | 1.9 V | 23 mW | 4.5 V, 210 mW |
| Q10 (tail) | 7.2 V | 75 mW | 40 V, 200 mW |
| Q3 (input cascode) | 13.6 V | 67 mW | 40 V, 200 mW |
| Q7 (mirror cascode) | 11.8 V | 63 mW | 20 V, 225 mW |
| Q18 (output PNP) | 15.6 V | 38 mW | 20 V, 225 mW |
| R19 (stage-2 load) | — | **156 mW** | **1206 = 250 mW** |
| R1 (bias reference) | — | 55 mW | 0603 = 100 mW |
| R18 (tail collector) | — | 51 mW | 0603 = 100 mW |

**Known thermal asymmetry in the input pair.** Q2 dissipates ~19 mW
(Vce 3.5 V) against Q1's ~8 mW (Vce 1.6 V, cascoded by Q3). On a SOT-343 that
is a few kelvin of junction difference, i.e. several mV of input offset that the
SPICE models (no self-heating) do not show. The layout keeps Q1/Q2 2.8 mm apart
with shared emitter copper; the circuit fix is a second cascode on Q2's
collector (TODO 4.7).

> **PCB note:** the BFP420 is a 4-lead SOT-343 (1=B, 2=E, 3=C, 4=E). The
> schematic uses KiCad's 3-pin `Q_NPN_BEC` symbol; on the layout, pad 4
> must be tied to pad 2 (emitter).

---

## 5. Known limitations

- **Input bias current ~21 µA.** At a 60 dB closed loop with `Rf = 10 kΩ`
  this gives ~0.2 V of output offset; the measured output DC is ~0.56 V
  (the ~0.5 mV input offset amplified by 1000). A trim or a servo would
  remove it. Keep the feedback network impedance low.
- **Closed-loop 60 dB requires a low-impedance feedback network** (`Rf` in
  the low-kΩ range). A 1 MΩ feedback resistor would put 21 V across it.
- The schematic is complete and verified. The **PCB is placed but not routed**:
  4 layers (F.Cu signal+parts / In1.Cu GND / In2.Cu rails / B.Cu GND), 50 ×
  40 mm, all 47 parts on the top side, nets generated from the same table
  that draws the schematic. See TODO §2 for what is left.

---

## 6. Repository layout

```
opamp/
├── README.md
├── gen_sch_rf.py            generator for the Rev-E schematic (source of truth)
├── gen_sch.py               shared symbol/wire emitter
├── opamp.kicad_sch          generated schematic, Rev E (A3)
├── opamp.kicad_pcb          4-layer board, placed, unrouted
├── gen_pcb.py               board generator (floorplan + pours + nets)
├── set_rules.py             design rules and net classes -> .kicad_pro
├── verify_board.py          board gate (layer stack, nets, pad 4, DRC)
├── pcb_preview.py           placement PNG
├── check.sh                 regenerate + ERC + netlist + sim gate
├── sim/
│   ├── rf_two_stage.py      Rev-E two-stage netlist + closed-loop test
│   ├── stress_two.py        Vce / Pd check for Rev E
│   ├── rf_lcsc.py           Rev-D single-stage netlist (models live here)
│   └── …                    earlier experiments
├── analysis/  docs/  artifacts/  svg/
```

---

## 7. How to run

```bash
# regenerate the schematic
python3 gen_sch_rf.py

# design-rule check — must report 0 violations
kicad-cli sch erc --severity-all -o /tmp/erc.rpt opamp.kicad_sch

# schematic -> SPICE netlist
kicad-cli sch export netlist --format spice -o /tmp/opamp.cir opamp.kicad_sch

# closed-loop spec test (60 dB, bandwidth, peaking)
cd sim && python3 rf_two_stage.py

# device stress
cd sim && python3 stress_two.py

# everything
./check.sh
```

The exported netlist was verified to reproduce `sim/rf_two_stage.py`
exactly: **59.91 dB, no peaking, 11.47 MHz**.

---

## 8. References

Local copies under `docs/` (scanned; OCR sidecars in `docs/ocr/`):

- *Operational Amplifiers — Design and Applications* (Tobey/Graeme/Huelsman/Burr-Brown)
- *Analog Integrated Circuit Design* (Johns & Martin)
- *Analysis and Design of Analog Integrated Circuits* (Gray & Meyer)
- *Microelectronic Circuits* (Sedra & Smith)
- *The Art of Electronics*, 2nd ed. (Horowitz & Hill)

## 9. Tooling

- KiCad 10.0.6, `kicad-cli`, `pcbnew`
- ngspice 45.2
- Python 3 (`math`/`subprocess` only for the sims)
