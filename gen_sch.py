#!/usr/bin/env python3
"""Generate a discrete JFET-input op-amp schematic (.kicad_sch, KiCad 10).

Rev B: current-mirror active load, NPN input buffer, offset-null trim pot,
Vbe-multiplier output bias, 10 MHz compensation, note block moved to sheet
bottom-left, input polarity labels corrected.
"""
import uuid, os, math, sys

ROOT = "ea34030c-8906-47ec-a5c9-047e049f0c5e"
PROJECT = "opamp"

LIBDIR = "/usr/share/kicad/symbols"
SYMLIB = {
    "Device": f"{LIBDIR}/Device.kicad_sym",
    "Transistor_BJT": f"{LIBDIR}/Transistor_BJT.kicad_sym",
    "Transistor_FET": f"{LIBDIR}/Transistor_FET.kicad_sym",
    "Connector_Generic": f"{LIBDIR}/Connector_Generic.kicad_sym",
    "power": f"{LIBDIR}/power.kicad_sym",
}

# ---- symbol pin tables (local coords) --------------------------------------
# NOTE: pin *positions* are physical; only the pin *numbers* change between the
# EBC and BEC variants of the same transistor drawing, so swapping EBC -> BEC
# (and BF245A -> Q_NJFET_DSG) leaves every wire coordinate valid.
PINS = {
    "Device:R": {"1": (0, 3.81), "2": (0, -3.81)},
    "Device:C": {"1": (0, 3.81), "2": (0, -3.81)},
    "Device:R_Potentiometer": {"1": (0, 3.81), "2": (3.81, 0), "3": (0, -3.81)},
    "Transistor_BJT:Q_NPN_BEC": {"1": (-5.08, 0), "2": (2.54, -5.08), "3": (2.54, 5.08)},
    "Transistor_BJT:Q_PNP_BEC": {"1": (-5.08, 0), "2": (2.54, -5.08), "3": (2.54, 5.08)},
    "Device:Q_NJFET_DSG": {"1": (2.54, 5.08), "2": (2.54, -5.08), "3": (-5.08, 0)},
    "Connector_Generic:Conn_01x06": {
        "1": (-5.08, 5.08), "2": (-5.08, 2.54), "3": (-5.08, 0),
        "4": (-5.08, -2.54), "5": (-5.08, -5.08), "6": (-5.08, -7.62)},
    "power:+15V": {"1": (0, 0)},
    "power:-15V": {"1": (0, 0)},
    "power:GND": {"1": (0, 0)},
    "power:PWR_FLAG": {"1": (0, 0)},
}


def extract_symbol(lib, name):
    path = SYMLIB[lib]
    s = open(path).read()
    key = '\t(symbol "%s"' % name
    i = s.find(key)
    if i < 0:
        key = '(symbol "%s"' % name
        i = s.find(key)
        if i < 0:
            raise SystemExit("symbol not found: %s:%s" % (lib, name))
    depth = 0
    k = i
    while k < len(s):
        if s[k] == '(':
            depth += 1
        elif s[k] == ')':
            depth -= 1
            if depth == 0:
                return s[i:k + 1]
        k += 1
    raise SystemExit("unbalanced")


def rot(px, py, ang):
    if ang == 0:
        return px, py
    if ang == 90:
        return -py, px
    if ang == 180:
        return -px, -py
    if ang == 270:
        return py, -px
    raise SystemExit("bad angle")


def gpin(lib, pnum, x, y, ang, mir):
    px, py = PINS[lib][pnum]
    if mir == "x":
        py = -py
    elif mir == "y":
        px = -px
    rx, ry = rot(px, py, ang)
    return (round(x + rx, 4), round(y - ry, 4))


def u():
    return str(uuid.uuid4())


# ---- footprints ------------------------------------------------------------
R = "Resistor_SMD:R_0603_1608Metric"
C = "Capacitor_SMD:C_0603_1608Metric"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SC59 = "Package_TO_SOT_SMD:SC-59"
POT = "Potentiometer_SMD:Potentiometer_Bourns_3214W_Vertical"
HDR = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical_SMD_Pin1Left"

# ---- components ------------------------------------------------------------
# (ref, lib, value, x, y, ang, mirror, footprint, dnp)
# lib_ids: Transistor_BJT:Q_NPN_BEC (1=B 2=E 3=C), Transistor_BJT:Q_PNP_BEC,
#          Device:Q_NJFET_DSG (1=D 2=S 3=G).
COMPONENTS = [
    # --- I/O connector + input series resistors
    ("J1",  "Connector_Generic:Conn_01x06", "Conn_01x06", 40.64, 34.29, 0, "y", HDR),
    ("R12", "Device:R", "1k",   95.25, 67.31, 90, None, R),
    ("R13", "Device:R", "1k",   95.25, 74.93, 90, None, R),
    # --- differential pair (Q1 gate = IN-, Q2 gate = IN+), source trim
    ("Q1",  "Device:Q_NJFET_DSG", "2SK209", 107.95, 67.31, 0, None, SC59),
    ("Q2",  "Device:Q_NJFET_DSG", "2SK209", 125.73, 74.93, 0, None, SC59),
    ("RT1", "Device:R_Potentiometer", "1k", 118.11, 81.28, 90, "x", POT),
    # --- active load: PNP mirror + shared emitter degeneration + cascode Q13
    ("Q9",  "Transistor_BJT:Q_PNP_BEC", "BC860", 115.57, 53.34, 0, "x", SOT23),
    ("Q10", "Transistor_BJT:Q_PNP_BEC", "BC860", 125.73, 52.07, 0, "x", SOT23),
    ("Q13", "Transistor_BJT:Q_PNP_BEC", "BC860", 125.73, 62.23, 0, "x", SOT23),
    ("R16", "Device:R", "4.3k", 118.11, 41.91, 0, None, R),
    ("Rb1", "Device:R", "8.2k", 135.89, 77.47, 0, None, R),
    ("Rb2", "Device:R", "33k",  135.89, 88.90, 0, None, R),
    ("C5", "Device:C", "100n", 139.70, 77.47, 0, None, C),
    # --- tail current mirror
    ("Q3",  "Transistor_BJT:Q_NPN_BEC", "BC850", 115.57, 97.79, 0, None, SOT23),
    ("R2",  "Device:R", "470",  118.11, 116.84, 0, None, R),
    ("Q4",  "Transistor_BJT:Q_NPN_BEC", "BC850", 99.06, 110.49, 0, None, SOT23),
    ("R3",  "Device:R", "470",  101.60, 123.19, 0, None, R),
    ("R1",  "Device:R", "14k",  106.68, 104.14, 0, None, R),
    ("C7",  "Device:C", "22p",  118.11, 63.50, 0, None, C),
    # --- input buffer + VAS + compensation
    ("Q11", "Transistor_BJT:Q_NPN_BEC", "BC850", 149.86, 54.61, 0, None, SOT23),
    ("Q5",  "Transistor_BJT:Q_PNP_BEC", "BC860", 163.83, 52.07, 0, "x", SOT23),
    ("Q16", "Transistor_BJT:Q_PNP_BEC", "BC860", 163.83, 62.23, 0, "x", SOT23),
    ("R6",  "Device:R", "900",  166.37, 40.64, 0, None, R),
    ("C6",  "Device:C", "100n", 161.29, 43.18, 0, None, C),
    ("R7",  "Device:R", "1.5k", 152.40, 92.71, 0, None, R),
    ("R8",  "Device:R", "150",  152.40, 105.41, 0, None, R),
    ("Rv1", "Device:R", "7.5k", 180.34, 49.53, 0, None, R),
    ("Rv2", "Device:R", "10k",  180.34, 60.96, 0, None, R),
    ("C3", "Device:C", "12p",  140.97, 67.31, 90, None, C),
    # --- driver + class-AB output
    ("Q6",  "Transistor_BJT:Q_NPN_BEC", "BC850", 182.88, 67.31, 0, None, SOT23),
    ("Q7",  "Transistor_BJT:Q_NPN_BEC", "BC850", 198.12, 73.66, 0, None, SOT23),
    ("Q8",  "Transistor_BJT:Q_PNP_BEC", "BC860", 198.12, 109.22, 0, "x", SOT23),
    ("Q12", "Transistor_BJT:Q_NPN_BEC", "BC850", 175.26, 96.52, 0, None, SOT23),
    ("R17", "Device:R", "1.1k", 170.18, 90.17, 0, None, R),
    ("R18", "Device:R", "1k",   170.18, 102.87, 0, None, R),
    ("C4",  "Device:C", "100n", 185.42, 96.52, 0, None, C),
    ("R9",  "Device:R", "2.7k", 189.23, 123.19, 0, None, R),
    ("R10", "Device:R", "2.2",  200.66, 86.36, 0, None, R),
    ("R11", "Device:R", "2.2",  200.66, 97.79, 180, None, R),
    # --- supply decoupling
    ("C1",  "Device:C", "100n", 133.35, 46.99, 0, None, C),
    ("C2",  "Device:C", "100n", 139.70, 46.99, 0, None, C),
]

# power symbols: (ref, lib, value, x, y, ang)
POWER = [
    ("#PWR01", "power:+15V", "+15V", 200.66, 36.83, 0),    # top +15V rail
    ("#PWR02", "power:-15V", "-15V", 200.66, 132.08, 180),  # bottom -15V rail
    ("#PWR03", "power:GND", "GND", 106.68, 107.95, 0),      # R1
    ("#PWR04", "power:GND", "GND", 133.35, 50.80, 0),       # C1
    ("#PWR05", "power:GND", "GND", 139.70, 50.80, 0),       # C2
    ("#PWR06", "power:+15V", "+15V", 57.15, 35.56, 0),      # J1 +15V
    ("#PWR07", "power:-15V", "-15V", 57.15, 40.64, 180),    # J1 -15V
    ("#PWR08", "power:GND", "GND", 48.26, 44.45, 0),        # J1 GND
    ("#FLG1", "power:PWR_FLAG", "PWR_FLAG", 193.04, 36.83, 0),
    ("#FLG2", "power:PWR_FLAG", "PWR_FLAG", 96.52, 129.54, 0),
    ("#FLG03", "power:PWR_FLAG", "PWR_FLAG", 48.26, 41.91, 270),
    # --- cascode bias dividers (rail connections via power symbols)
    ("#PWR09", "power:+15V", "+15V", 135.89, 73.66, 0),     # Rb1 top
    ("#PWR010", "power:-15V", "-15V", 135.89, 92.71, 180),  # Rb2 bottom
    ("#PWR011", "power:GND", "GND", 139.70, 73.66, 0),      # Cvc
    ("#PWR012", "power:+15V", "+15V", 180.34, 45.72, 0),    # Rv1 top
    ("#PWR013", "power:-15V", "-15V", 180.34, 64.77, 180),  # Rv2 bottom
    ("#PWR014", "power:GND", "GND", 118.11, 67.31, 0),      # Cz
]

# ---- simulation fields (KiCad ngspice) -------------------------------------
_NPN = [("Sim.Device", "NPN"), ("Sim.Type", "GUMMELPOON"),
        ("Sim.Pins", "1=B 2=E 3=C"),
        ("Sim.Params", "IS=6.7f VAF=120 BF=350 ISE=1f NE=1.5 IKF=0.3 "
                       "XTB=1.5 BR=60 XCJC=0.35 RC=1.5 CJC=1.5p CJE=2.5p "
                       "TR=10n TF=0.42n RB=15")]
_PNP = [("Sim.Device", "PNP"), ("Sim.Type", "GUMMELPOON"), ("Sim.Pins", "1=B 2=E 3=C"),
        ("Sim.Params", "IS=1.9f VAF=120 BF=300 ISE=1.7f NE=1.49 IKF=0.5 "
                       "XTB=1.5 BR=25 XCJC=0.35 RC=2 CJC=2p CJE=3p "
                       "TR=8n TF=0.55n RB=20")]
_NJF = [("Sim.Device", "NJFET"), ("Sim.Type", "SHICHMANHODGES"), ("Sim.Pins", "1=D 2=S 3=G"),
        ("Sim.Params", "VTO=-0.7 BETA=9.0m LAMBDA=0.006 RD=12 RS=13 "
                       "CGS=10p CGD=3p PB=0.4 FC=0.5")]
_POT = [("Sim.Device", "R"), ("Sim.Type", "POT"), ("Sim.Pins", "1=r0 2=wiper 3=r1"),
        ("Sim.Params", "r=1k pos=0.5")]
SIM_FIELDS = {
    "Q1": _NJF, "Q2": _NJF,
    "Q3": _NPN, "Q4": _NPN, "Q6": _NPN, "Q7": _NPN, "Q11": _NPN, "Q12": _NPN,
    "Q5": _PNP, "Q8": _PNP, "Q9": _PNP, "Q10": _PNP, "Q13": _PNP, "Q16": _PNP,
    "RT1": _POT,
}
NO_SIM = {"J1"}  # excludes the I/O connector from simulation

# ---- wires -----------------------------------------------------------------
WIRES = [
    ((110.49, 72.39), (110.49, 81.28)),
    ((121.92, 81.28), (128.27, 81.28)),
    ((128.27, 46.99), (118.11, 46.99)),
    ((166.37, 67.31), (177.8, 67.31)),
    ((106.68, 97.79), (106.68, 100.33)),
    ((152.4, 109.22), (152.4, 129.54)),
    ((101.6, 97.79), (101.6, 105.41)),
    ((118.11, 46.99), (118.11, 48.26)),
    ((92.71, 97.79), (110.49, 97.79)),
    ((118.11, 92.71), (118.11, 85.09)),
    ((110.49, 53.34), (110.49, 62.23)),
    ((110.49, 81.28), (114.3, 81.28)),
    ((189.23, 109.22), (189.23, 119.38)),
    ((45.72, 41.91), (48.26, 41.91)),
    ((133.35, 67.31), (137.16, 67.31)),
    ((133.35, 36.83), (133.35, 43.18)),
    ((185.42, 100.33), (185.42, 109.22)),
    ((200.66, 91.44), (200.66, 93.98)),
    ((118.11, 45.72), (118.11, 46.99)),
    ((118.11, 59.69), (118.11, 58.42)),
    ((128.27, 81.28), (128.27, 80.01)),
    ((45.72, 36.83), (57.15, 36.83)),
    ((99.06, 67.31), (102.87, 67.31)),
    ((144.78, 67.31), (152.4, 67.31)),
    ((92.71, 97.79), (92.71, 110.49)),
    ((110.49, 59.69), (120.65, 59.69)),
    ((86.36, 74.93), (91.44, 74.93)),
    ((170.18, 109.22), (177.8, 109.22)),
    ((133.35, 54.61), (133.35, 67.31)),
    ((200.66, 91.44), (205.74, 91.44)),
    ((92.71, 110.49), (93.98, 110.49)),
    ((45.72, 39.37), (57.15, 39.37)),
    ((57.15, 35.56), (57.15, 36.83)),
    ((200.66, 101.6), (200.66, 104.14)),
    ((101.6, 127), (101.6, 129.54)),
    ((99.06, 74.93), (120.65, 74.93)),
    ((133.35, 54.61), (144.78, 54.61)),
    ((152.4, 36.83), (152.4, 49.53)),
    ((45.72, 31.75), (49.53, 31.75)),
    ((170.18, 86.36), (177.8, 86.36)),
    ((170.18, 93.98), (170.18, 96.52)),
    ((200.66, 132.08), (200.66, 129.54)),
    ((185.42, 72.39), (185.42, 92.71)),
    ((118.11, 36.83), (200.66, 36.83)),
    ((118.11, 113.03), (118.11, 102.87)),
    ((152.4, 67.31), (166.37, 67.31)),
    ((200.66, 36.83), (200.66, 68.58)),
    ((57.15, 39.37), (57.15, 40.64)),
    ((48.26, 41.91), (48.26, 44.45)),
    ((170.18, 96.52), (170.18, 99.06)),
    ((152.4, 101.6), (152.4, 96.52)),
    ((101.6, 119.38), (101.6, 115.57)),
    ((86.36, 67.31), (91.44, 67.31)),
    ((200.66, 78.74), (200.66, 82.55)),
    ((177.8, 86.36), (185.42, 86.36)),
    ((200.66, 114.3), (200.66, 129.54)),
    ((189.23, 109.22), (193.04, 109.22)),
    ((185.42, 109.22), (189.23, 109.22)),
    ((185.42, 73.66), (193.04, 73.66)),
    ((139.7, 36.83), (139.7, 43.18)),
    ((185.42, 36.83), (185.42, 62.23)),
    ((170.18, 109.22), (170.18, 106.68)),
    ((45.72, 34.29), (49.53, 34.29)),
    ((200.66, 90.17), (200.66, 91.44)),
    ((177.8, 109.22), (185.42, 109.22)),
    ((189.23, 127), (189.23, 129.54)),
    ((177.8, 101.6), (177.8, 109.22)),
    ((200.66, 129.54), (96.52, 129.54)),
    ((118.11, 120.65), (118.11, 129.54)),
    ((152.4, 67.31), (152.4, 88.9)),
    ((177.8, 86.36), (177.8, 91.44)),
    ((118.11, 38.1), (118.11, 36.83)),
    ((45.72, 29.21), (49.53, 29.21)),
    ((128.27, 67.31), (133.35, 67.31)),
    # --- cascode rewiring
    ((128.27, 67.31), (128.27, 69.85)),      # n_x : Q13.C -> junction -> Q2.D
    ((120.65, 52.07), (120.65, 59.69)),      # n_q1d: moved Q10.B down to existing rail
    ((166.37, 44.45), (166.37, 46.99)),      # n_q5e: R6.2 -> Q5.E
    ((152.4, 59.69), (158.75, 59.69)),       # n_y  : Q11.E ->
    ((158.75, 59.69), (158.75, 52.07)),      # n_y  : -> moved Q5.B
    ((161.29, 39.37), (161.29, 36.83)),      # C6 top -> +15V rail
    ((161.29, 46.99), (166.37, 46.99)),      # C6 bottom -> n_q5e (Q5.E)
    # --- Q13 base bias net n_vb
    ((120.65, 62.23), (127.0, 62.23)),
    ((127.0, 62.23), (127.0, 83.82)),
    ((127.0, 83.82), (135.89, 83.82)),
    ((135.89, 81.28), (135.89, 85.09)),      # Rb1.2 - Rb2.1 divider
    ((139.7, 81.28), (135.89, 81.28)),       # Cvc -> n_vb node
    # --- Q16 base bias net n_vc
    ((180.34, 53.34), (180.34, 57.15)),      # Rv1.2 - Rv2.1 divider
    ((180.34, 57.15), (180.34, 62.23)),
    ((180.34, 62.23), (158.75, 62.23)),      # -> moved Q16.B
]

JUNCTIONS = [
    (128.27, 67.31),
    (166.37, 67.31),
    (200.66, 36.83),
    (189.23, 129.54),
    (110.49, 59.69),
    (193.04, 36.83),
    (118.11, 59.69),
    (106.68, 97.79),
    (118.11, 129.54),
    (185.42, 73.66),
    (166.37, 36.83),
    (185.42, 109.22),
    (48.26, 41.91),
    (200.66, 91.44),
    (133.35, 36.83),
    (152.4, 129.54),
    (177.8, 109.22),
    (101.6, 129.54),
    (177.8, 86.36),
    (118.11, 46.99),
    (170.18, 96.52),
    (152.4, 36.83),
    (139.7, 36.83),
    (185.42, 36.83),
    (101.6, 97.79),
    (185.42, 86.36),
    (189.23, 109.22),
    (133.35, 67.31),
    (152.4, 67.31),
    (200.66, 129.54),
    # --- cascode / bias junctions
    (161.29, 36.83),   # C6 top on +15V rail
    (166.37, 46.99),   # R6.2 + C6 + Q5.E
    (135.89, 81.28),   # Rb1.2 + divider + Cvc
    (135.89, 83.82),   # divider + n_vb route
    (180.34, 57.15),   # Rv2.1 + divider + n_vc route
]

# labels: (text, x, y, justify) - terminals only; internal nets are drawn
LABELS = [
    ("OUT", 49.53, 34.29, "left"),
    ("IN+", 49.53, 29.21, "left"),
    ("IN-", 49.53, 31.75, "left"),
    ("IN+", 86.36, 74.93, "right"),
    ("IN-", 86.36, 67.31, "right"),
    ("OUT", 205.74, 91.44, "left"),
]

TEXTS = [
    ("Discrete JFET-Input Operational Amplifier", 15.24, 12.70),
    ("+/-15 V supplies | Aol >= 60 dB | GBW 10 MHz | Zin ~ 1 Gohm | Zout < 1 ohm", 15.24, 15.24),
    ("Design notes", 15.24, 149.86),
    ("Input pair: matched 2SK209 / LSK170 / LSK389 JFETs; cascoded active load (Q13) holds the mirror off the input drains.", 15.24, 152.40),
    ("Active load: Q9/Q10 PNP mirror with shared R16 (4.3k); Q13 cascodes the PNP output so n_mc stays ~1 Vbe below VCC.", 15.24, 154.94),
    ("Q11 emitter follower isolates the mirror node from Q5 base current; Q16 cascodes the VAS output (n_vc bias).", 15.24, 157.48),
    ("Q13 bias: Rb1 8.2k / Rb2 33k divider on n_vb (C5 100n). Q16 bias: Rv1 7.5k / Rv2 10k on n_vc.", 15.24, 160.02),
    ("Compensation: C3 (Cc1) 12p n_x->n_q5c, Rz=0, C7 22p n_q1d->GND. GBW = gm_eff / (2*pi*C3).", 15.24, 162.56),
    ("Output bias: Q12 Vbe multiplier (R17 1.1k / R18 1k ~1.4 V) with C4 100n bootstrap; R10/R11 2.2 ohm for thermal stability.", 15.24, 165.10),
    ("Polarity: Q1 gate = IN- (inverting), Q2 gate = IN+. Rising IN- raises Q1 current, the mirror raises the node voltage, the PNP VAS pulls the output low.", 15.24, 167.64),
    ("RT1 (1k) trims Vos; R12/R13 1k are input series resistors. J1: OUT / IN+ / IN- / +15V / -15V / GND.", 15.24, 170.18),
    (".ac dec 40 10 1G", 15.24, 175.26),
]

# ---- global horizontal offset ----------------------------------------------
# Tables above are already in final sheet coordinates.
XOFS = 0


def apply_xofs():
    global COMPONENTS, POWER, WIRES, JUNCTIONS, LABELS
    COMPONENTS = [c[:3] + (c[3] + XOFS,) + c[4:] for c in COMPONENTS]
    POWER = [c[:3] + (c[3] + XOFS,) + c[4:] for c in POWER]
    WIRES = [((a[0] + XOFS, a[1]), (b[0] + XOFS, b[1])) for (a, b) in WIRES]
    JUNCTIONS = [(x + XOFS, y) for (x, y) in JUNCTIONS]
    LABELS = [(t, x + XOFS, y, j) for (t, x, y, j) in LABELS]


# ----------------------------------------------------------------------------
# automatic Reference/Value text placement (keeps text off wires and bodies)
# ----------------------------------------------------------------------------
FS = 1.27


def tbox(t, x, y, just="center", bottom=False):
    w = len(t) * FS * 0.95
    h = FS * 1.5
    if just == "left":
        x0 = x
    elif just == "right":
        x0 = x - w
    else:
        x0 = x - w / 2.0
    if bottom:
        y0, y1 = y - h, y
    else:
        y0, y1 = y - h / 2.0, y + h / 2.0
    return (x0, y0, x0 + w, y1)


def ov(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def body_box(lib, x, y, ang):
    if lib == "Device:R_Potentiometer":
        return (x - 3.0, y - 3.9, x + 3.0, y + 3.9)
    if lib.startswith("power:"):
        return (x - 4.5, y - 4.5, x + 4.5, y + 4.5)
    if lib.startswith("Transistor"):
        return (x - 3.5, y - 3.5, x + 3.5, y + 3.5)
    if ang in (90, 270):
        return (x - 3.81, y - 1.6, x + 3.81, y + 1.6)
    return (x - 1.6, y - 3.81, x + 1.6, y + 3.81)


def place_texts():
    occ = []
    for (a, b) in WIRES:
        x1, y1 = a
        x2, y2 = b
        occ.append((min(x1, x2) - 0.35, min(y1, y2) - 0.35,
                    max(x1, x2) + 0.35, max(y1, y2) + 0.35))
    for c in COMPONENTS:
        ref, lib, val, x, y, ang = c[:6]
        occ.append(body_box(lib, x, y, ang))
    for (ref, lib, val, x, y, ang) in POWER:
        occ.append(body_box(lib, x, y, ang))
        occ.append(tbox(val, x, y))
    for (t, x, y, j) in LABELS:
        occ.append(tbox(t, x, y, j, bottom=True))
    for (t, x, y) in TEXTS:
        occ.append(tbox(t, x, y, "left", bottom=True))

    cands = [(0, -2.54), (0, 2.54), (2.54, 0), (-2.54, 0),
             (0, -5.08), (0, 5.08), (3.81, 0), (-3.81, 0),
             (3.81, -2.54), (-3.81, -2.54), (3.81, 2.54), (-3.81, 2.54),
             (0, -7.62), (0, 7.62), (6.35, 0), (-6.35, 0),
             (6.35, -2.54), (-6.35, -2.54), (6.35, 2.54), (-6.35, 2.54),
             (0, -10.16), (0, 10.16), (8.89, 0), (-8.89, 0),
             (5.08, -5.08), (-5.08, -5.08), (5.08, 5.08), (-5.08, 5.08),
             (7.62, -5.08), (-7.62, -5.08), (7.62, 5.08), (-7.62, 5.08),
             (0, -12.70), (0, 12.70), (11.43, 0), (-11.43, 0),
             (11.43, -2.54), (-11.43, -2.54), (11.43, 2.54), (-11.43, 2.54),
             (10.16, -7.62), (-10.16, -7.62), (10.16, 7.62), (-10.16, 7.62),
             (0, -15.24), (0, 15.24), (13.97, 0), (-13.97, 0)]
    cands.sort(key=lambda d: math.hypot(d[0], d[1]))

    out, moved = {}, []
    for c in COMPONENTS:
        ref, lib, val, x, y, ang = c[:6]
        for name, txt, tx, ty in (("Reference", ref, x, y - 5.08),
                                  ("Value", val, x, y + 5.08)):
            best = None
            for dx, dy in [(0, 0)] + cands:
                b = tbox(txt, tx + dx, ty + dy)
                if b[0] < 11 or b[2] > 286 or b[1] < 11 or b[3] > 199:
                    continue
                if any(ov(b, o) for o in occ):
                    continue
                best = (b, tx + dx, ty + dy)
                if dx or dy:
                    moved.append("%s.%s (%.2f,%.2f) -> (%.2f,%.2f)"
                                 % (ref, name, tx, ty, tx + dx, ty + dy))
                break
            if best is None:
                best = (tbox(txt, tx, ty), tx, ty)
                moved.append("%s.%s NO CLEAR SPOT" % (ref, name))
            occ.append(best[0])
            out[(ref, name)] = (best[1], best[2])
    return out, moved


def sym_block(lib, name):
    b = extract_symbol(lib, name)
    return b.replace("(symbol \"%s\"" % name, "(symbol \"%s:%s\"" % (lib, name), 1)


def emit():
    tpos, moved = place_texts()
    out = []
    out.append("(kicad_sch")
    out.append("\t(version 20260306)")
    out.append("\t(generator \"eeschema\")")
    out.append("\t(generator_version \"10.0\")")
    out.append('\t(uuid "%s")' % ROOT)
    out.append('\t(paper "A4")')
    out.append("\t(title_block")
    out.append('\t\t(title "Discrete JFET-Input Op Amp")')
    out.append('\t\t(rev "B")')
    out.append('\t\t(comment 1 "Discrete operational amplifier, +/-15V, Aol>=60dB, GBW=10MHz")')
    out.append('\t\t(comment 2 "Rev B: mirror active load, input buffer, Vos trim, Vbe output bias")')
    out.append("\t)")

    # lib_symbols
    out.append("\t(lib_symbols")
    seen = set()
    for lib, name in [("Device", "R"), ("Device", "C"),
                      ("Device", "R_Potentiometer"), ("Device", "Q_NJFET_DSG"),
                      ("Transistor_BJT", "Q_NPN_BEC"), ("Transistor_BJT", "Q_PNP_BEC"),
                      ("Connector_Generic", "Conn_01x06"),
                      ("power", "+15V"), ("power", "-15V"), ("power", "GND"),
                      ("power", "PWR_FLAG")]:
        if (lib, name) in seen:
            continue
        seen.add((lib, name))
        out.append("\t\t" + sym_block(lib, name).replace("\n\t", "\n\t\t"))
    out.append("\t)")

    # junctions
    for (x, y) in JUNCTIONS:
        out.append("\t(junction (at %s %s) (diameter 0) (color 0 0 0 0)\n\t\t(uuid \"%s\")\n\t)" % (x, y, u()))

    # wires
    for (a, b) in WIRES:
        out.append("\t(wire\n\t\t(pts\n\t\t\t(xy %s %s) (xy %s %s)\n\t\t)\n\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid \"%s\")\n\t)" % (a[0], a[1], b[0], b[1], u()))

    # labels
    for (t, x, y, j) in LABELS:
        out.append('\t(label "%s"\n\t\t(at %s %s 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify %s bottom)\n\t\t)\n\t\t(uuid "%s")\n\t)' % (t, x, y, j, u()))

    # text notes
    for (t, x, y) in TEXTS:
        out.append('\t(text "%s"\n\t\t(exclude_from_sim no)\n\t\t(at %s %s 0)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "%s")\n\t)' % (t, x, y, u()))

    # component symbols
    def place(ref, lib, val, x, y, ang, mir, footprint, dnp=False, is_power=False):
        pins = PINS[lib]
        out.append("\t(symbol")
        out.append('\t\t(lib_id "%s")' % lib)
        out.append("\t\t(at %s %s %s)" % (x, y, ang))
        if mir:
            out.append("\t\t(mirror %s)" % mir)
        out.append("\t\t(unit 1)")
        out.append("\t\t(body_style 1)")
        out.append("\t\t(exclude_from_sim %s)" % ("yes" if ref in NO_SIM else "no"))
        out.append("\t\t(in_bom yes)")
        out.append("\t\t(on_board yes)")
        out.append("\t\t(in_pos_files yes)")
        out.append("\t\t(dnp %s)" % ("yes" if dnp else "no"))
        out.append('\t\t(uuid "%s")' % u())
        if is_power:
            props_list = [("Reference", ref, x, y, True),
                          ("Value", val, x, y, False),
                          ("Footprint", "", x, y, True),
                          ("Datasheet", "", x, y, True)]
        else:
            rx, ry = tpos[(ref, "Reference")]
            vx, vy = tpos[(ref, "Value")]
            props_list = [("Reference", ref, rx, ry, False),
                          ("Value", val, vx, vy, False),
                          ("Footprint", footprint, x, y, True),
                          ("Datasheet", "", x, y, True)]
        for (nm, v) in SIM_FIELDS.get(ref, []):
            props_list.append((nm, v, x, y, True))
        for (nm, v, px, py, hide) in props_list:
            h = "\n\t\t\t\t(hide yes)" if hide else ""
            out.append('\t\t(property "%s" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)%s\n\t\t\t)\n\t\t)' % (nm, v, px, py, h))
        for pnum in pins:
            out.append('\t\t(pin "%s"\n\t\t\t(uuid "%s")\n\t\t)' % (pnum, u()))
        out.append("\t\t(instances")
        out.append('\t\t\t(project "%s"' % PROJECT)
        out.append('\t\t\t\t(path "/%s"' % ROOT)
        out.append('\t\t\t\t\t(reference "%s")' % ref)
        out.append("\t\t\t\t\t(unit 1)")
        out.append("\t\t\t\t)")
        out.append("\t\t\t)")
        out.append("\t\t)")
        out.append("\t)")

    for c in COMPONENTS:
        ref, lib, val, x, y, ang, mir, fp = c[:8]
        dnp = c[8] if len(c) > 8 else False
        place(ref, lib, val, x, y, ang, mir, fp, dnp=dnp, is_power=False)
    for (ref, lib, val, x, y, ang) in POWER:
        place(ref, lib, val, x, y, ang, None, "", dnp=False, is_power=True)

    out.append("\t(sheet_instances")
    out.append('\t\t(path "/"')
    out.append('\t\t\t(page "1")')
    out.append("\t\t)")
    out.append("\t)")
    out.append(")")
    return "\n".join(out) + "\n", moved


if __name__ == "__main__":
    apply_xofs()
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opamp.kicad_sch")
    path = sys.argv[1] if len(sys.argv) > 1 else default
    body, moved = emit()
    with open(path, "w") as f:
        f.write(body)
    print("wrote", path, len(body), "bytes")
    print("--- text placements adjusted: %d" % len(moved))
    for m in moved:
        print("   ", m)
