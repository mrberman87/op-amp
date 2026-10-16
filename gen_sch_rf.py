#!/usr/bin/env python3
"""Generate the discrete RF BJT op-amp schematic (KiCad 10).

Single-stage, fully self-biased, gain-boosted (regulated) cascode front-end
using BFP420 (NPN) / BFP520 (PNP) RF transistors:

    Q1/Q2   NPN diff pair            Q8    NPN emitter-follower output buffer
    Q3/Q4   PNP mirror load          Q11   NPN current sink (output)
    Q5/Q6   PNP cascodes             Q9    NPN diode (bias reference)
    Q7      PNP helper (boost)       Q10   NPN tail current source
    R5/R8   mirror degeneration      R6    helper load

R8 is a fixed 54.9R (E96) output-mirror degeneration resistor.  Its value is
chosen to cancel the amplifier's *systematic* input offset, which is ~16 mV
otherwise (early effect on the input pair + the saturated reference-side
cascode).  This replaces the former RV1 100R offset trimmer.

Validated in sim/rf_final.py: Aol ~= 58.8 dB, f-3dB ~= 12 MHz (RL=10k),
PM ~= 66 deg, open-loop Vos ~= 0.  The main amplifier is drawn with real
wires; net labels are used only at the external terminals (INP / INN / OUT
and the J1 rails).
"""
import os

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

# ---- footprints ------------------------------------------------------------
R = "Resistor_SMD:R_0603_1608Metric"
C = "Capacitor_SMD:C_0603_1608Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
HDR = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical_SMD_Pin1Left"

# ---- component placement ---------------------------------------------------
# (ref, lib, value, x, y, ang, mirror, footprint)
# PNP mirror/cascode:  Q3/Q5/Q7 are rotated 180 deg (base on the right); Q4/Q6
# use mirror x (base on the left).  That lets each transistor pair share a
# straight base-tie wire with no wire crossing a symbol body.
COMPONENTS = [
    # I/O
    ("J1",  "Connector_Generic:Conn_01x06", "Conn_01x06", 40.64, 90.17, 0, "y", HDR),
    # input differential pair + tail
    ("Q1",  "Transistor_BJT:Q_NPN_BEC", "BFP420", 86.36, 93.98, 0, None, SOT23),
    ("Q2",  "Transistor_BJT:Q_NPN_BEC", "BFP420", 124.46, 93.98, 0, None, SOT23),
    ("Q10", "Transistor_BJT:Q_NPN_BEC", "BFP420", 105.41, 119.38, 0, None, SOT23),
    ("R3",  "Device:R", "1k", 107.95, 128.27, 0, None, R),
    # mirror + regulated cascode
    ("Q3",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 91.44, 63.5, 180, None, SOT23),
    ("Q4",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 124.46, 63.5, 0, "x", SOT23),
    ("Q5",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 91.44, 78.74, 180, None, SOT23),
    ("Q6",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 124.46, 78.74, 0, "x", SOT23),
    ("R5",  "Device:R", "22", 88.9, 54.61, 0, None, R),
    ("R8",  "Device:R", "54.9", 127.0, 54.61, 0, None, R),
    # helper (gain boost)
    ("Q7",  "Transistor_BJT:Q_PNP_BEC", "BFP520", 121.92, 71.12, 180, None, SOT23),
    ("R6",  "Device:R", "15k", 107.95, 82.55, 0, None, R),
    # output buffer
    ("Q8",  "Transistor_BJT:Q_NPN_BEC", "BFP420", 140.97, 86.36, 0, None, SOT23),
    ("Q11", "Transistor_BJT:Q_NPN_BEC", "BFP420", 140.97, 106.68, 0, None, SOT23),
    ("R4",  "Device:R", "390", 143.51, 115.57, 0, None, R),
    # load + supply decoupling
    ("R7",  "Device:R", "10k", 156.21, 95.25, 0, None, R),
    ("C1",  "Device:C", "100n", 254.0, 60.96, 0, None, C),
    ("C2",  "Device:C", "100n", 254.0, 140.97, 0, None, C),
    # bias network
    ("Q9",  "Transistor_BJT:Q_NPN_BEC", "BFP420", 63.5, 116.84, 0, None, SOT23),
    ("R1",  "Device:R", "13.7k", 55.88, 106.68, 0, None, R),
    ("R2",  "Device:R", "1k", 66.04, 125.73, 0, None, R),
]

# ---- wires (drawn connectivity; labels only at the external terminals) -----
# Internal nets and the pins they join (from sim/rf_final.py):
#   T    = Q1.E Q2.E Q10.C            c1 = Q1.C Q3.B Q4.B Q5.C
#   n1   = Q3.C Q5.E                  c2 = Q2.C Q6.C Q8.B
#   n2   = Q4.C Q6.E Q7.B             vcph = Q5.B Q6.B Q7.C R6.1
#   e3   = Q3.E R5.2 (=coincident)    e4 = Q4.E R8.2 (=coincident)
#   vref = Q9.B Q9.C Q10.B Q11.B R1.2  veb = Q9.E R2.1
#   vet  = Q10.E R3.1                 veb2 = Q11.E R4.1
#   OUT  = Q8.E Q11.C R7.1 J1.1
WIRES = [
    # T (input-pair emitters + tail collector)
    ((88.9, 99.06), (127.0, 99.06)),
    ((107.95, 114.3), (107.95, 99.06)),
    # n1 : Q3.C -> Q5.E
    ((88.9, 68.58), (88.9, 73.66)),
    # c1 : Q5.C -> Q1.C (left collector column)
    ((88.9, 83.82), (88.9, 88.9)),
    # c1 : mirror base tie Q3.B -> Q4.B
    ((96.52, 63.5), (119.38, 63.5)),
    # c1 : riser from the base tie down to the collector column
    ((99.06, 63.5), (99.06, 86.36)),
    ((99.06, 86.36), (88.9, 86.36)),
    # n2 : Q4.C -> Q6.E (Q7.B taps in)
    ((127.0, 68.58), (127.0, 73.66)),
    # c2 : Q6.C -> Q2.C, plus branch to Q8.B
    ((127.0, 83.82), (127.0, 88.9)),
    ((127.0, 86.36), (135.89, 86.36)),
    # vcph : cascode base tie Q5.B -> Q6.B, plus Q7.C drop
    ((96.52, 78.74), (119.38, 78.74)),
    ((119.38, 76.2), (119.38, 78.74)),
    # OUT : Q8.E -> Q11.C, plus branch to R7
    ((143.51, 91.44), (143.51, 101.6)),
    ((143.51, 91.44), (156.21, 91.44)),
    # vref bus
    ((58.42, 116.84), (53.34, 116.84)),
    ((53.34, 116.84), (53.34, 111.76)),
    ((53.34, 111.76), (135.89, 111.76)),
    ((55.88, 110.49), (55.88, 111.76)),
    ((97.79, 111.76), (97.79, 119.38)),
    ((97.79, 119.38), (100.33, 119.38)),
    ((135.89, 111.76), (135.89, 106.68)),
    # J1 pin stubs (labels sit at the outer end)
    ((45.72, 85.09), (48.26, 85.09)),
    ((45.72, 87.63), (48.26, 87.63)),
    ((45.72, 90.17), (48.26, 90.17)),
    ((45.72, 92.71), (48.26, 92.71)),
    ((45.72, 95.25), (48.26, 95.25)),
    ((45.72, 97.79), (48.26, 97.79)),
]

JUNCTIONS = [
    (107.95, 99.06),   # T : tail riser meets emitter tie
    (99.06, 63.5),     # c1 : riser meets mirror base tie
    (88.9, 86.36),     # c1 : riser meets collector column
    (127.0, 71.12),    # n2 : Q7.B taps the cascode-emitter node
    (127.0, 86.36),    # c2 : Q8.B branch
    (107.95, 78.74),   # vcph : R6.1
    (119.38, 78.74),   # vcph : Q6.B + Q7.C drop
    (143.51, 91.44),   # OUT : Q8.E + R7 branch
    (55.88, 111.76),   # vref : R1.2 tap
    (66.04, 111.76),   # vref : Q9.C
    (97.79, 111.76),   # vref : Q10.B tap
]

# labels: (text, x, y, justify) - external terminals only
LABELS = [
    ("INP", 81.28, 93.98, "right"),
    ("INN", 119.38, 93.98, "right"),
    ("OUT", 143.51, 91.44, "left"),
    ("OUT", 48.26, 85.09, "left"),
    ("INP", 48.26, 87.63, "left"),
    ("INN", 48.26, 90.17, "left"),
    ("GND", 48.26, 92.71, "left"),
    ("+15V", 48.26, 95.25, "left"),
    ("-15V", 48.26, 97.79, "left"),
]

# power symbols: (ref, lib, value, x, y, ang)
POWER = [
    # +15V
    ("#PWR01", "power:+15V", "+15V", 88.9, 50.8, 0),      # R5.1
    ("#PWR02", "power:+15V", "+15V", 127.0, 50.8, 0),     # R8.1
    ("#PWR04", "power:+15V", "+15V", 119.38, 66.04, 0),   # Q7.E
    ("#PWR05", "power:+15V", "+15V", 143.51, 81.28, 0),   # Q8.C
    ("#PWR06", "power:+15V", "+15V", 55.88, 102.87, 0),   # R1.1
    ("#PWR07", "power:+15V", "+15V", 254.0, 57.15, 0),    # C1.1
    # -15V
    ("#PWR08", "power:-15V", "-15V", 107.95, 132.08, 180),  # R3.2
    ("#PWR09", "power:-15V", "-15V", 107.95, 86.36, 180),   # R6.2
    ("#PWR010", "power:-15V", "-15V", 143.51, 119.38, 180),  # R4.2
    ("#PWR011", "power:-15V", "-15V", 66.04, 129.54, 180),   # R2.2
    ("#PWR012", "power:-15V", "-15V", 254.0, 137.16, 180),   # C2.1
    # GND
    ("#PWR013", "power:GND", "GND", 156.21, 99.06, 0),       # R7.2
    ("#PWR014", "power:GND", "GND", 254.0, 64.77, 0),        # C1.2
    ("#PWR015", "power:GND", "GND", 254.0, 144.78, 0),       # C2.2
    # PWR_FLAG assemblies (give the rails a driver for ERC)
    ("#PWR016", "power:+15V", "+15V", 30.48, 158.75, 0),
    ("#FLG1", "power:PWR_FLAG", "PWR_FLAG", 30.48, 161.29, 0),
    ("#PWR017", "power:-15V", "-15V", 38.1, 158.75, 180),
    ("#FLG2", "power:PWR_FLAG", "PWR_FLAG", 38.1, 161.29, 0),
    ("#PWR018", "power:GND", "GND", 45.72, 158.75, 0),
    ("#FLG3", "power:PWR_FLAG", "PWR_FLAG", 45.72, 161.29, 0),
]

# PWR_FLAG tie wires
WIRES += [
    ((30.48, 158.75), (30.48, 161.29)),
    ((38.1, 158.75), (38.1, 161.29)),
    ((45.72, 158.75), (45.72, 161.29)),
]

SIM_FIELDS = {"Q1": _NPN, "Q2": _NPN, "Q10": _NPN, "Q8": _NPN,
              "Q9": _NPN, "Q11": _NPN,
              "Q3": _PNP, "Q4": _PNP, "Q5": _PNP, "Q6": _PNP, "Q7": _PNP}
NO_SIM = {"J1"}

# Reference netlist for verification (from sim/rf_final.py).  Note the helper
# base Q7.1 is on n2 (the cascode emitter), matching rf_final.py's
# "Qh vcph n2 15 QP".
NETS = {
    "INP":  [("Q1", "1"), ("J1", "2")],
    "INN":  [("Q2", "1"), ("J1", "3")],
    "T":    [("Q1", "2"), ("Q2", "2"), ("Q10", "3")],
    "c1":   [("Q3", "1"), ("Q4", "1"), ("Q5", "3"), ("Q1", "3")],
    "c2":   [("Q6", "3"), ("Q2", "3"), ("Q8", "1")],
    "n1":   [("Q3", "3"), ("Q5", "2")],
    "n2":   [("Q4", "3"), ("Q6", "2"), ("Q7", "1")],
    "e3":   [("Q3", "2"), ("R5", "2")],
    "e4":   [("Q4", "2"), ("R8", "2")],
    "vcph": [("Q7", "3"), ("Q5", "1"), ("Q6", "1"), ("R6", "1")],
    "vref": [("Q9", "1"), ("Q9", "3"), ("Q10", "1"), ("Q11", "1"),
             ("R1", "2")],
    "veb":  [("Q9", "2"), ("R2", "1")],
    "vet":  [("Q10", "2"), ("R3", "1")],
    "veb2": [("Q11", "2"), ("R4", "1")],
    "OUT":  [("Q8", "2"), ("Q11", "3"), ("R7", "1"), ("J1", "1")],
    "+15V": [("R1", "1"), ("R5", "1"), ("R8", "1"),
             ("Q7", "2"), ("Q8", "3"), ("C1", "1"), ("J1", "5")],
    "-15V": [("R2", "2"), ("R3", "2"), ("R4", "2"), ("R6", "2"),
             ("C2", "1"), ("J1", "6")],
    "GND":  [("R7", "2"), ("C1", "2"), ("C2", "2"), ("J1", "4")],
}

TEXTS = [
    ("Discrete RF Operational Amplifier (BFP420 / BFP520)",
     15.24, 12.70),
    ("+/-15 V | Aol ~= 58.8 dB (RL=10k) | f-3dB ~= 12 MHz | GBW ~= 6 GHz | single stage",
     15.24, 15.24),
    ("Design notes", 15.24, 176.00),
    ("Input: Q1/Q2 BFP420 diff pair, tail source Q10 (vref = Q9/R1 diode).", 15.24, 178.54),
    ("Load: Q3/Q4 PNP mirror, degenerated by R5 (22R) and R8 (54.9R) -> Vos null.", 15.24, 181.08),
    ("Regulated cascode: Q5/Q6 cascode the mirror; helper Q7 senses n2 (Q4.C) and", 15.24, 183.62),
    ("  drives both cascode bases via vcph (R6 15k) -> gain boost to ~60 dB. Q8 buffers c2.", 15.24, 186.16),
    ("Q11 sinks the follower current; C1/C2 100n decouple the rails. J1: OUT/IN+/IN-/GND/+15V/-15V.", 15.24, 188.70),
    ("Internal nets (T, c1, c2, n1, n2, vcph, vref, e3/e4, veb/vet/veb2) are drawn as wires.", 15.24, 191.24),
    (".ac dec 60 1 40gig ; ngspice model cards are attached as Sim.* symbol fields.", 15.24, 193.78),
]


def main():
    g.COMPONENTS = COMPONENTS
    g.POWER = POWER
    g.WIRES = WIRES
    g.JUNCTIONS = JUNCTIONS
    g.LABELS = LABELS
    g.TEXTS = TEXTS
    g.SIM_FIELDS = SIM_FIELDS
    g.NO_SIM = NO_SIM

    body, moved = g.emit()
    body = body.replace('Discrete JFET-Input Op Amp', 'Discrete RF BJT Op Amp')
    body = body.replace('Discrete operational amplifier, +/-15V, Aol>=60dB, GBW=10MHz',
                        'Discrete RF BJT op amp, +/-15V, Aol~58.8dB, GBW~6GHz, single stage')
    body = body.replace('Rev B: mirror active load, input buffer, Vos trim, Vbe output bias',
                        'Rev C: regulated cascode, self-biased, BFP420/BFP520')
    body = body.replace('(rev "B")', '(rev "C")')

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "opamp.kicad_sch")
    with open(out, "w") as f:
        f.write(body)
    print("wrote", out, len(body), "bytes")
    print("components=%d power=%d wires=%d labels=%d"
          % (len(COMPONENTS), len(POWER), len(WIRES), len(LABELS)))
    if moved:
        print("--- %d text placements adjusted" % len(moved))
        for m in moved:
            print("   ", m)


if __name__ == "__main__":
    main()
