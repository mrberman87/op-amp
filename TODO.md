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

The board is complete: placed, routed, KiCad DRC 0 violations / 0 unconnected
under the project's net-class rules. Re-floorplanned and re-routed after a
further review: signal-flow placement, J1 re-pinned to the board, OUT/OUTA
on a GND corridor, rip-up/reroute + tidy passes (no stepped traces), then an
independent adversarial review whose fixes are applied (open items below).

Pipeline (the board is edited in place; `gen_pcb.py` must not be re-run):
`place.py` syncs parts and pad nets from `gen_sch_rf.NET`, shapes the outline
and pours, strips old routing and places the parts; `route.py` routes (OUT/OUTA
corridor, signals, rail fanouts, rip-up/reroute, tidy, stitching, R19 copper);
`set_rules.py` / `set_stackup.py` write rules and stack-up; `verify_board.py`
gates. All run from `./check.sh` except `place.py` / `route.py` (deliberate
steps: `python3 place.py --seed 34 --iters 1000000 --cross 8 && python3
place.py --polish && python3 route.py`). Do not use KiCad's "Update PCB from Schematic" (schematic auto net
names differ from the board's). `freeroute.py` is an optional Freerouting
round trip; it was tried and gave worse results (see its docstring).

**Done**
- [x] **2.1 Stack-up** (`set_stackup.py`). 4 copper, 1.606 mm: F.Cu 1 oz
      signal+parts / 0.21 mm 7628 / In1.Cu ½ oz solid GND / 1.065 mm core /
      In2.Cu ½ oz rails / 0.21 mm 7628 / B.Cu 1 oz GND. In1/In2 typed as power
      planes. The common default 4-layer build (e.g. JLC04161H-7628) — confirm
      dielectric thicknesses with the fab.
- [x] **2.2 Outline.** 50 × 40 mm, 2 mm corner radius. Two M3 holes (H1
      top-left, H2 bottom-right) with Ø7 mm copper keepouts on every layer;
      fiducials FID1–3; board ID on B.Silk.
- [x] **2.3 All components on F.Cu**, asserted by the gate.
- [x] **2.4 SOT-343 pad 4** tied to pad 2 on all six BFP420s.
- [x] **2.5 Netlist integrity.** Every schematic pin's net is on its board pad
      (gate), including the six pads re-netted by the J1 re-pin and stoppers.
- [x] **2.6 Design rules.** Default 0.2/0.2, Analog (high-Z) 0.2/0.25, Power
      0.25/0.5 with 0.8/0.4 vias; min annular ring 0.15 mm (0.6/0.3 via).
- [x] **2.7 Placement** (`place.py --seed 34 --iters 1000000 --cross 8`,
      then `place.py --polish`). Signal flow left to right along the top and
      back down the middle: stage 1 beside J1's input pins, tail / bias below
      it; stage 2 along the top with Q13 facing its pins (base + Miller C7
      upper left, collector to R19 / R22, emitter to C13 / R20 / C6), so the
      no-cross nets (c2, c2b, d1, d2, e1, d2b, d3b) have no ratsnest
      crossings; output stage one column across the In2 GND corridor (Q17/Q16,
      C3 + Q19, Q18), R15/R16/R17 at OUTA. Q1/Q2 3.5 mm (centres, rot 90),
      mirror Q4/Q6 4.2 mm; R24 3.5 mm from Q1. `--polish` keeps the placement
      and seats parts by rule (`SNUG`): stoppers R21/R23 on their bases,
      C10/C14/C5/C13/C8/C9/C3 on their pins, TP8 by TP7 — never accepting a
      spot that adds a no-cross crossing. Courtyards ≥ 0.8 mm apart (0.25 mm
      for the base stoppers and 0.3 mm inside the matched pairs).
- [x] **2.7a In2.Cu.** +15 V top, −15 V bottom, a 3 mm GND corridor between
      them (y 19.5–22.5 mm, in line with J1 pin 4) and a 2.5 mm GND frame round
      the edge. J1 is pinned to match (1 +15V, 2 INP, 3 GND, 4 OUT, 5 INN,
      6 −15V): each rail pin lands in its own pour, no tab.
- [x] **2.7b Decoupling.** Cascode-base caps C10/C14/C5, C13 at Q13's emitter,
      C8/C9 at the Q17/Q18 collectors, C3 across Q19 — each placed by `SNUG`
      at the nearest legal spot (3.8–4.5 mm centre to centre). C1 at Q14/Q15,
      C11 (bulk) at J1 pin 1, C2/C12 at J1 pin 6. Each cap has its own via.
- [x] **2.8 Routing** (`route.py`): 350 segments, 132 vias, KiCad DRC 0 / 0.
      Grid A* router, then a rip-up/reroute pass (each net alone against the
      finished board, kept if shorter) and a tidy pass (every chain redrawn
      with the fewest 0/45/90° segments that clear the other nets: 622 → 350
      segments, no staircases). No vias and no B.Cu on c2, c2b, d1, d2, d2b,
      d3b, INP, INN. Routed lengths (mm): c2 5.3, c2b 1.5, d1 9.7, d2 8.8,
      d2b 7.5, d3b 12.9, e1 13.8, e3 6.0, e4 2.4, vcp 13.0, INP 5.5, INN 9.8.
      Rail fanout stubs ≤ 2.4 mm except R4 (2.15).
- [x] **2.9 OUT / OUTA** run on B.Cu straight along the In2 GND corridor: OUT
      (0.5 mm, y 20.65) to J1 pin 4, OUTA (0.3 mm, y 21.6) to R24. Shielded
      from F.Cu by In1; the corridor is stitched to In1 / B.Cu by a row of GND
      vias along each edge (13 vias, 3.5 mm pitch where they fit).
- [x] **2.10 Thermal copper.** R19's +15 V pad has an F.Cu copper area tied by
      its via to In2.
- [x] **2.11 Ground.** In1 solid; B.Cu GND pour (split by the OUT/OUTA
      runs, each half stitched); GND stitching vias round the perimeter every
      3 mm and along the corridor.
- [x] **2.13 Test points.** TP1–TP8: +15V, −15V, GND, vcn, vcd, OUTA, OUT,
      and GND (TP8, beside TP7: scope ground at the output).
      None on c2/d2: a probe pad on a high-impedance node adds capacitance.
- [x] **2.14 Silkscreen.** References 1.0 mm / 0.15 mm (0.8 mm / 0.15 mm in
      four crowded spots), each placed beside its own part where possible.

**Declined, with reason**
- **2.12 Guard ring.** Guard rings protect pA-level inputs from leakage; the
  input bias current here is ~21 µA, so board leakage is irrelevant.

**Open / judgment calls for the bench**
- [ ] **2.15** R4 (+15 V end of the vcn divider) sits over the −15 V half and
      reaches the +15 V pour through an 11 mm, 0.5 mm stub that passes the
      mirror. No legal +15 V spot exists within 14 mm of Q3. Harmless at DC
      (≈ 1 mA); moving R4 to the +15 V side would carry vcn instead (C4
      decouples it).
- [ ] **2.16** No base stoppers on Q1/Q2 (noise vs the 10 Ω R25) or on the
      MMBTH81 output PNP Q18 (600 MHz part). Add if the bench shows GHz
      oscillation.
- [ ] **2.17** Refill zones (`B`) after any edit and before generating Gerbers.
- [ ] **2.18** R22 (Q14's base stopper) is 7.6 mm from Q14 (d2b 7.5 mm of
      trace after the stopper) and R23's d3b is 12.9 mm. R19, C14 and Q15 box
      Q14's base in; moving Q14 to open a gap cascades into C14 / d3
      crossings. A local re-floorplan of Q13–Q14–Q15 would fix both.
- [ ] **2.19** Input-pair thermal symmetry: R1 (55 mW) is 3.8 mm from Q1 and
      5.7 mm from Q2 (independent review: ≈ 52 vs 47 mW/mm). Small against
      the circuit's own 19 vs 8 mW pair imbalance (4.7).
- [ ] **2.20** vcd (DC, bypassed at all three cascode bases) is 64 mm long.

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
| C1–C5, C8–C10, C13, C14 | 100n | 0603 | — | |
| R21–R23 | 33 | 0603 | — | base stoppers |
| R24 / R25 | 10k / 10 | 0603 | — | on-board feedback (60 dB) |
| TP1–TP8 | test pad | Ø1.5 mm SMD | — | |
| J1 | 6-way screw terminal 3.5 mm | THT | — | Phoenix PT 1,5/6-3,5-H or equivalent |
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
