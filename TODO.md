# TODO — two-stage LCSC op-amp (Rev E)

Status: **two-stage design meets the 60 dB / 10 MHz spec in closed loop.**

Known-good state:

- `gen_sch_rf.py` → `opamp.kicad_sch` (A3), ERC **0 errors / 0 warnings**.
- `sim/rf_two_stage.py` closed-loop test: **59.91 dB, 0 dB peaking,
  f−3dB 11.47 MHz, 57.96 dB at 10 MHz**.
- The exported netlist reproduces the sim exactly (59.91 dB, 11.47 MHz).
- `sim/stress_two.py`: no VCEO violations, no device above 50 % Pd.
- `./check.sh` runs regenerate + ERC + netlist + closed-loop + stress.

---

## 1. Done

- [x] **Second gain stage.** Q13 (BFP420 CE) with R19 load, R20/C6 emitter,
      C7 = 68 p Miller compensation. Open-loop gain ~110 dB.
- [x] **Push-pull output** (Q16/Q18, class-AB, Q19 Vbe multiplier).
- [x] **VCEO protection** (Q3/Q12/Q15/Q17 cascodes).
- [x] **Capacitive-load stability** (R17 = 47 Ω isolation).
- [x] **Tail dissipation** (R18 = 470 Ω).
- [x] **Human-readable schematic**: functional blocks with dashed borders,
      left-to-right signal flow, block titles.

---

## 2. PCB layout

Started: 4-layer board generated from the schematic table, all parts on top.
`opamp.kicad_pcb` was first produced by `gen_pcb.py`; it is now edited in place
(J1 locked by hand, placement by `place.py`), so `gen_pcb.py` must not be re-run
on it. `set_rules.py` writes the rules; `verify_board.py` gates (inside `./check.sh`).

**Done**
- [x] **2.1 Stackup.** 4 copper, 1.6 mm: F.Cu signal+parts / In1.Cu solid GND /
      In2.Cu +15 V and −15 V pours / B.Cu GND. Order as JLC0004-100L.
- [x] **2.2 Outline.** 50 × 40 mm. Courtyards ≥ 1 mm inside the edge; a
      courtyard-free strip along the bottom (y > 37.2 mm) and left (x < 2.2 mm)
      edges is reserved for the OUT trace back to J1 pin 1.
- [x] **2.3 All components on F.Cu** — asserted by the gate, not assumed.
- [x] **2.4 SOT-343 pad 4.** BFP420 is 4-lead (1=B, 2=E, 3=C, 4=E); pad 4 is
      created and tied to pad 2's net on all six BFP420s.
- [x] **2.5 Netlist integrity.** 117/117 schematic pins match their board pads;
      nets are taken from `gen_sch_rf.NET`, so board and schematic cannot drift.
- [x] **2.6 Design rules.** min clearance 0.2 mm, min track 0.2 mm, via 0.6/0.3;
      classes Default / Power (+/−15 V, GND: 0.5 mm, 0.8/0.4 via) / Analog (hi-Z).
- [x] **2.7 Placement** (`place.py`, after a review + adversarial review).
      Stage 1 is a ring on its side so INP/INN reach their bases from J1
      without crossings; stage 2 above it with C6 beside Q13; output stage on
      the right edge, NPN half over +15 V and PNP half over −15 V; R17/R7
      bottom-right. Q1/Q2 2.8 mm apart (shared emitter copper), mirror Q4/Q6
      4.6 mm apart with heat sources placed symmetrically about it. One
      ratsnest crossing left, c1 × vcp — inherent in the circuit topology; take
      it on vcp (DC bias) as a B.Cu hop. Courtyards ≥ 1.0 mm apart.
- [x] **2.7a In2.Cu split.** +15 V top half, −15 V bottom half, plus a +15 V
      finger down the left edge under J1 pin 5 and C1/C11 (J1's +15 V pin is
      in the bottom half). Every rail pad sits over its own pour except R1.1
      (+15 V, 7 mm from the pour): give it a short F.Cu trace.
- [x] **2.7b Local decoupling** (added after review): C8 at Q17's collector,
      C9 at Q18's collector, C10 at Q12's base, C4 at Q3's base, C5 at
      Q15/Q17's bases, C11/C12 10 µF bulk at J1. All within 3.8 mm.
- [x] **2.7c Mounting holes + fiducials.** M3 holes H1 (top-left) and H2
      (bottom-right); fiducials FID1–3 on three corners; board ID on B.Silk.
      Silkscreen references 1.0 mm / 0.15 mm, each beside its own part.

**To do**
- [ ] **2.8 Routing.** Nothing is wired yet (100 unconnected pads is expected
      at this stage). Route F.Cu over the intact In1.Cu ground; do not put signal
      traces on In1.Cu or In2.Cu.
- [ ] **2.9 High-Z discipline.** Route c2, d1, d2, d3 and the C7 Miller loop
      first, shortest possible, each with a via stitch to In1.Cu nearby.
      Current spread (half-perimeter): c2 10.8, d1 5.1, d2 19.5, e1 7.9 mm.
      Route OUT from R17/R7 along the bottom edge and up the left edge to J1
      pin 1 (the reserved strip), not across stage 1.
- [ ] **2.10 Thermal copper.** R19 (1206, 156 mW) needs a pour plus 2–3 vias
      into In2.Cu; keep it away from Q13's base — 156 mW in still air shifts a
      nearby BJT's Vbe by several hundred µV and the input offset is ~0.56 mV.
- [ ] **2.11 Ground strategy.** Single solid GND, star-referenced at J1 pin 4.
      Do not split the plane. Stitch the perimeter every 3–5 mm.
- [ ] **2.12 Guard ring** around Q1/Q2/Q3 and the input traces from J1.
- [ ] **2.13 Test points.** None placed yet: add +15V, −15V, vcn, vcd, c2, d2,
      OUTA, OUT. Bring-up of this circuit is blind without them.
- [ ] **2.16 Re-check after routing:** `kicad-cli pcb drc` must reach 0 violations
      apart from nothing, and fill zones (`B` in the GUI) before generating
      Gerbers.

**Deliberate choice worth knowing:** R17 (47 Ω isolation) and R7 (10 k load)
sit at the output stage, bottom-right, so R17 isolates the long OUT trace's
capacitance from the output pair. OUT then returns to J1 pin 1 along the bottom
and left edges (a part-free strip is reserved for it), past the tail and bias
parts and away from the stage-1/stage-2 high-impedance nodes.

---

## 3. BOM / ordering

| Ref | Value / part | Package | LCSC | Notes |
|---|---|---|---|---|
| Q1, Q2, Q11, Q13, Q14, Q16 | BFP420H6327 | SOT-343 | **C412737** | 32 k stock |
| Q4–Q8, Q18 | MMBTH81 | SOT-23 | **C190349** | 10.6 k stock |
| Q3, Q9, Q10, Q12, Q15, Q17, Q19 | MMBT3904 | SOT-23 | **C20526** | 4.3 M stock |
| R19 | 1k | **1206** | — | 156 mW |
| R1 | 13.7k | 0603 | — | bias reference |
| R2 | 1k | 0603 | — | |
| R3 | 180 | 0603 | — | tail |
| R4 | 6.8k | 0603 | — | vcn top |
| R5 | 22 | 0603 | — | mirror ref |
| R6 | 22k | 0603 | — | helper |
| R7 | 10k | 0603 | — | load |
| R8 | 20 | 0603 | — | mirror out |
| R9 | 8.2k | 0603 | — | vcn bottom |
| R10 | 6.8k | 0603 | — | vcd top |
| R11 | 11k | 0603 | — | vcd bottom |
| R12/R13 | 1.8k / 1.2k | 0603 | — | Vbe multiplier |
| R14 | 10k | 0603 | — | |
| R15/R16 | 4.7 | 0603 | — | output emitters |
| R17 | 47 | 0603 | — | isolation |
| R18 | 470 | 0603 | — | tail collector |
| R20 | 50 | 0603 | — | stage-2 emitter |
| C1–C5, C8–C10 | 100n | 0603 | — | |
| C11, C12 | 10 µF, ≥25 V X5R | 1206 | — | rail bulk at J1 |
| C6 | 220 µF | 6.3×5.4 mm | — | stage-2 bypass |
| C7 | 68 p | 0603 | — | Miller |

- [ ] **3.1** Resolve LCSC C-codes for the 0603 passives (all E24/E96).
- [ ] **3.2** Check JLCPCB assembly availability (BFP420/MMBTH81 are
      extended parts; expect a setup fee).

---

## 4. Characterization / improvements

- [ ] **4.1 Output DC offset.** At 60 dB closed loop the ~0.5 mV input offset
      becomes ~0.5 V at the output. Add a trim (Re4/R5 asymmetry) or a DC
      servo if a low offset is required.
- [ ] **4.2 Temperature sweep** (0 / 27 / 70 °C): gain, bandwidth, offset.
- [ ] **4.3 CMRR / PSRR** — not measured.
- [ ] **4.4 Large-signal / slew rate / clipping.** The class-AB stage has not
      been characterised at full swing.
- [ ] **4.5 Closed-loop step response** and settling.
- [ ] **4.7 Input-pair thermal asymmetry.** Q2 dissipates ~19 mW, Q1 ~8 mW
      (Q1 is cascoded by Q3, Q2 is not). Self-heating mismatch ≈ several mV of
      input offset, not visible in SPICE. Fix in the circuit: cascode Q2's
      collector too (an MMBT3904 with its base on vcn), then re-run
      rf_two_stage.py / verify_netlist.py.
- [ ] **4.8 Base stoppers.** Consider 0603 base-stopper footprints at the
      BFP420 follower bases (Q11, Q14, Q16) if bench shows GHz oscillation.
- [ ] **4.6 Low-frequency corner.** C6 = 220 µF gives a ~15 Hz open-loop
      corner; the closed loop is flat to 0.01 Hz because Aol ≫ 60 dB there.
      Verify on the bench.

---

## 5. Housekeeping

- [ ] **5.1** Rev-C/Rev-D files (`sim/rf_final.py`, `sim/rf_frontend.py`,
      `sim/rf_lcsc.py`, `sim/rf_two.py`, `sim/rf_wide.py`) are historical.
      `rf_frontend.py` still contains the **fictitious BFP520 PNP model**.
- [ ] **5.2** Delete the old schematic backups (`opamp.kicad_sch.bak*`,
      `gen_sch.py.bak`).
- [ ] **5.3** Regenerate or remove `artifacts/freq_response_openloop.png`
      (it is the Rev-C figure).
