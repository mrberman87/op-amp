#!/usr/bin/env python3
"""Generate the discrete RF BJT op-amp schematic (KiCad 10).

Single-stage, fully self-biased, gain-boosted (regulated) cascode front-end
using BFP420 (NPN) / BFP520 (PNP) RF transistors:

    Q1/Q2   NPN diff pair            Q5    NPN emitter-follower output buffer
    Q3/Q4   PNP mirror load          Qbuf  NPN current sink (output)
    Q3c/Q4c PNP cascodes             Qb    NPN diode (bias reference)
    Qh      PNP helper (boost)       Qtail NPN tail current source
    Re3/RT1 mirror emitter trim      Rc    helper load

Validated in sim/rf_final.py: Aol ~= 60 dB, f-3dB ~= 13.8 MHz (RL=10k),
PM ~= 60 deg.  Reuses the emitter machinery in gen_sch.py; connectivity is
expressed as net labels + short stubs so every net is explicit and ERC-clean.
"""
import os
import sys

import gen_sch as g

# ---- device models (identical to sim/rf_frontend.py) -----------------------
_BFP420 = (
    "IS=0.20045f BF=72.534 NF=1.2432 VAF=28.383 IKF=0.48731 ISE=19.049f "
    "NE=2.0518 BR=7.8287 NR=1.3325 VAR=19.705 IKR=0.69141m ISC=0.019237f "
    "NC=1.1724 RB=8.5757 IRB=0.72983m RBM=3.4849 RE=0.31111 RC=0.10105 "
    "CJE=1.8063f VJE=0.8051 MJE=0.46576 FC=0.73234 CJC=234.53f VJC=0.81696 "
    "MJC=0.30232 XCJC=0.3 TF=6.7661p XTF=0.42199 VTF=0.23794 ITF=1m PTF=0 "
    "TR=2.3249n XTB=0 EG=1.11 XTI=3 TNOM=300")
_BFP520 = (
    "IS=15a BF=235 NF=1 VAF=25 IKF=0.4 ISE=25f NE=2 BR=1.5 NR=1 VAR=2 "
    "IKR=0.01 ISC=20f NC=2 RB=11 RBM=7.5 RE=0.6 RC=7.6 CJE=235f VJE=0.958 "
    "MJE=0.335 FC=0.5 CJC=93f VJC=0.661 MJC=0.236 XCJC=1 TF=1.7p XTF=10 "
    "VTF=5 ITF=0.7 PTF=50 TR=50n XTB=-0.25 EG=1.11 XTI=0.35 TNOM=298")

_NPN = [("Sim.Device", "NPN"), ("Sim.Type", "GUMMELPOON"),
        ("Sim.Pins", "1=B 2=E 3=C"), ("Sim.Params", _BFP420)]
_PNP = [("Sim.Device", "PNP"), ("Sim.Type", "GUMMELPOON"),
        ("Sim.Pins", "1=B 2=E 3=C"), ("Sim.Params", _BFP520)]
_POT = [("Sim.Device", "R"), ("Sim.Type", "POT"),
        ("Sim.Pins", "1=r0 2=wiper 3=r1"), ("Sim.Params", "r=100 pos=0.3")]

# ---- footprints ------------------------------------------------------------
R = "Resistor_SMD:R_0603_1608Metric"
C = "Capacitor_SMD:C_0603_1608Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
POT = "Potentiometer_SMD:Potentiometer_Bourns_3214W_Vertical"
HDR = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical_SMD_Pin1Left"

# ---- component placement ---------------------------------------------------
# (ref, lib, value, x, y, ang, mirror, footprint)
COMPONENTS = [
    # I/O
    ("J1",  "Connector_Generic:Conn_01x06", "Conn_01x06", 40, 90, 0, "y", HDR),
    # input differential pair + tail
    ("Q1",  "Transistor_BJT:Q_NPN_BEC", "BFP420", 105, 115, 0, None, SOT23),
    ("Q2",  "Transistor_BJT:Q_NPN_BEC", "BFP420", 135, 115, 0, None, SOT23),
    ("Q10", "Transistor_BJT:Q_NPN_BEC", "BFP420", 120, 138, 0, None, SOT23),
    ("R3",  "Device:R", "1k", 120, 152, 0, None, R),
    # mirror + regulated cascode
    ("Q3",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 105, 85, 0, "x", SOT23),
    ("Q4",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 135, 85, 0, "x", SOT23),
    ("Q5",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 105, 102, 0, "x", SOT23),
    ("Q6",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 135, 102, 0, "x", SOT23),
    ("R5",  "Device:R", "22", 105, 72, 0, None, R),
    ("RV1", "Device:R_Potentiometer", "100", 135, 72, 0, None, POT),
    # helper (gain boost)
    ("Q7",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 170, 92, 0, "x", SOT23),
    ("R6",  "Device:R", "15k", 170, 108, 0, None, R),
    # output buffer
    ("Q8",  "Transistor_BJT:Q_NPN_BEC", "BFP420", 200, 100, 0, None, SOT23),
    ("Q11", "Transistor_BJT:Q_NPN_BEC", "BFP420", 220, 120, 0, None, SOT23),
    ("R4",  "Device:R", "390", 220, 135, 0, None, R),
    # load + supply decoupling
    ("R7",  "Device:R", "10k", 245, 100, 0, None, R),
    ("C1",  "Device:C", "100n", 255, 60, 0, None, C),
    ("C2",  "Device:C", "100n", 255, 140, 0, None, C),
    # bias network
    ("Q9",  "Transistor_BJT:Q_NPN_BEC", "BFP420", 75, 120, 0, None, SOT23),
    ("R1",  "Device:R", "13k", 60, 105, 0, None, R),
    ("R2",  "Device:R", "1k", 75, 135, 0, None, R),
]

# ---- connectivity (net -> [(ref, pin)]) ------------------------------------
NETS = {
    "INP":  [("Q1", "1"), ("J1", "2")],
    "INN":  [("Q2", "1"), ("J1", "3")],
    "T":    [("Q1", "2"), ("Q2", "2"), ("Q10", "3")],
    "c1":   [("Q3", "1"), ("Q4", "1"), ("Q5", "3"), ("Q1", "3")],
    "c2":   [("Q6", "3"), ("Q2", "3"), ("Q7", "1"), ("Q8", "1")],
    "n1":   [("Q3", "3"), ("Q5", "2")],
    "n2":   [("Q4", "3"), ("Q6", "2")],
    "e3":   [("Q3", "2"), ("R5", "2")],
    "e4":   [("Q4", "2"), ("RV1", "3")],
    "vcph": [("Q7", "3"), ("Q5", "1"), ("Q6", "1"), ("R6", "1")],
    "vref": [("Q9", "1"), ("Q9", "3"), ("Q10", "1"), ("Q11", "1"),
             ("R1", "2")],
    "veb":  [("Q9", "2"), ("R2", "1")],
    "vet":  [("Q10", "2"), ("R3", "1")],
    "veb2": [("Q11", "2"), ("R4", "1")],
    "OUT":  [("Q8", "2"), ("Q11", "3"), ("R7", "1"), ("J1", "1")],
    # supply rails (driven by power symbols)
    "+15V": [("R1", "1"), ("R5", "1"), ("RV1", "1"), ("RV1", "2"),
             ("Q7", "2"), ("Q8", "3"), ("C1", "1"), ("J1", "5")],
    "-15V": [("R2", "2"), ("R3", "2"), ("R4", "2"), ("R6", "2"),
             ("C2", "1"), ("J1", "6")],
    "GND":  [("R7", "2"), ("C1", "2"), ("C2", "2"), ("J1", "4")],
}
RAILS = {"+15V": ("power:+15V", "+15V", 0),
         "-15V": ("power:-15V", "-15V", 180),
         "GND":  ("power:GND", "GND", 0)}

SIM_FIELDS = {"Q1": _NPN, "Q2": _NPN, "Q10": _NPN, "Q8": _NPN,
              "Q9": _NPN, "Q11": _NPN,
              "Q3": _PNP, "Q4": _PNP, "Q5": _PNP, "Q6": _PNP, "Q7": _PNP,
              "RV1": _POT}
NO_SIM = {"J1"}

L = 2.54  # stub length
GRID = 1.27


def snap(v):
    return round(round(v / GRID) * GRID, 4)


def _dir(px, py, cx, cy):
    dx, dy = px - cx, py - cy
    if abs(dx) >= abs(dy):
        return (1 if dx >= 0 else -1, 0)
    return (0, 1 if dy >= 0 else -1)


def build():
    comp = {c[0]: c for c in g.COMPONENTS}
    wires, labels, junctions = [], [], []
    power = []
    npwr = 0

    def _place(ref):
        c = comp[ref]
        return c[3], c[4]

    for net, pins in NETS.items():
        for (ref, pnum) in pins:
            _, lib, _, x, y, ang, mir = comp[ref][:7]
            px, py = g.gpin(lib, pnum, x, y, ang, mir)
            dx, dy = _dir(px, py, x, y)
            ex, ey = round(px + dx * L, 2), round(py + dy * L, 2)
            wires.append(((round(px, 2), round(py, 2)), (ex, ey)))
            if net in RAILS:
                libp, valp, angp = RAILS[net]
                npwr += 1
                power.append(("#PWR%02d" % npwr, libp, valp, ex, ey, angp))
            else:
                just = "right" if dx < 0 else "left"
                labels.append((net, ex, ey, just))

    # PWR_FLAG assemblies so the rails have a driver (ERC clean)
    flagpts = [("+15V", 30.0), ("-15V", 36.0), ("GND", 42.0)]
    nflg = 0
    for (val, x) in flagpts:
        libp, valp, angp = RAILS[val]
        nflg += 1
        x, y0 = snap(x), snap(160.0)
        y1 = round(y0 + L, 4)
        power.append(("#PWR%02d" % (npwr + nflg), libp, valp, x, y0, angp))
        power.append(("#FLG%d" % nflg, "power:PWR_FLAG", "PWR_FLAG",
                      x, y1, 0))
        wires.append(((x, y0), (x, y1)))

    return wires, labels, junctions, power


TEXTS = [
    ("Discrete RF Operational Amplifier (BFP420 / BFP520)",
     15.24, 12.70),
    ("+/-15 V | Aol >= 60 dB (RL=10k) | f-3dB ~= 13.8 MHz | GBW ~= 6 GHz | single stage",
     15.24, 15.24),
    ("Design notes", 15.24, 176.00),
    ("Input: Q1/Q2 BFP420 diff pair, tail source Q10 (vref = Q9/R1 diode).", 15.24, 178.54),
    ("Load: Q3/Q4 PNP mirror, degenerated by R5 (22R) and RV1 (100R trim) -> Vos null.", 15.24, 181.08),
    ("Regulated cascode: Q5/Q6 cascode the mirror; helper Q7 senses n2 and drives both", 15.24, 183.62),
    ("  cascode bases via vcph (R6 15k) -> gain boost to ~60 dB. Q8 emitter follower buffers c2.", 15.24, 186.16),
    ("Q11 sinks the follower current; C1/C2 100n decouple the rails. J1: OUT/IN+/IN-/GND/+15V/-15V.", 15.24, 188.70),
    ("Nets shown as labels: T tail, c1/c2 collectors, n1/n2 cascode mid, vcph, vref, e3/e4.", 15.24, 191.24),
    (".ac dec 60 1 40gig ; ngspice model cards are attached as Sim.* symbol fields.", 15.24, 193.78),
]


def main():
    g.COMPONENTS = [(r, l, v, snap(x), snap(y), a, m, f)
                    for (r, l, v, x, y, a, m, f) in COMPONENTS]
    wires, labels, junctions, power = build()
    g.POWER = power
    g.WIRES = wires
    g.JUNCTIONS = junctions
    g.LABELS = labels
    g.TEXTS = TEXTS
    g.SIM_FIELDS = SIM_FIELDS
    g.NO_SIM = NO_SIM

    body, moved = g.emit()
    body = body.replace('Discrete JFET-Input Op Amp', 'Discrete RF BJT Op Amp')
    body = body.replace('Discrete operational amplifier, +/-15V, Aol>=60dB, GBW=10MHz',
                        'Discrete RF BJT op amp, +/-15V, Aol>=60dB, GBW~6GHz, single stage')
    body = body.replace('Rev B: mirror active load, input buffer, Vos trim, Vbe output bias',
                        'Rev C: regulated cascode, self-biased, Vos trim, BFP420/BFP520')
    body = body.replace('(rev "B")', '(rev "C")')

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "opamp.kicad_sch")
    with open(out, "w") as f:
        f.write(body)
    print("wrote", out, len(body), "bytes")
    print("components=%d power=%d wires=%d labels=%d"
          % (len(COMPONENTS), len(power), len(wires), len(labels)))
    if moved:
        print("--- %d text placements adjusted" % len(moved))


if __name__ == "__main__":
    main()
