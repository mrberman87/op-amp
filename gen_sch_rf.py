#!/usr/bin/env python3
"""Generate the two-stage LCSC op-amp schematic (Rev E).

The sheet is drawn for a human reader:

  * The signal runs left to right along one band:
      STAGE 1 (diff pair + cascode mirror)  ->  STAGE 2 (buffer + Miller CE)
      ->  OUTPUT (buffer, Vbe multiplier, class-AB pair).
    The stage-to-stage nets are drawn wires, not labels, so the eye can
    follow the signal without hunting for a matching name.
  * Inside each stage +15 V is at the top and -15 V / GND at the bottom.
  * Support circuits sit in a lower band: the I/O connector, the two cascode
    bias dividers and the supply decoupling.
  * Only nets that genuinely jump across the sheet carry a label: the
    connector pins (INP, INN, OUT, rails) and the bias lines vcn, vcd, vcp.
  * Every reference and value is placed next to its part, never left to an
    auto-placer.

All coordinates below are in grid units (1 unit = 1.27 mm) so every pin lands
on KiCad's 50 mil grid.  The netlist (NET) is the single source of truth: the
PCB generator reads it too, and _audit() refuses a drawing whose wires do not
realise exactly that netlist.
"""
import os
import sys

import gen_sch as g

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim"))
from rf_lcsc import BFP420 as _M_BFP420, MMBTH81 as _M_MMBTH81  # noqa: E402
from rf_lcsc import MMBT3904 as _M_MMBT3904, MMBT3906 as _M_MMBT3906  # noqa: E402


def _params(model):
    return model[model.index("(") + 1:model.rindex(")")]


_NPN_BFP = [("Sim.Device", "NPN"), ("Sim.Type", "GUMMELPOON"),
            ("Sim.Pins", "1=B 2=E 3=C"), ("Sim.Params", _params(_M_BFP420))]
_PNP_H81 = [("Sim.Device", "PNP"), ("Sim.Type", "GUMMELPOON"),
            ("Sim.Pins", "1=B 2=E 3=C"), ("Sim.Params", _params(_M_MMBTH81))]
_NPN_3904 = [("Sim.Device", "NPN"), ("Sim.Type", "GUMMELPOON"),
             ("Sim.Pins", "1=B 2=E 3=C"), ("Sim.Params", _params(_M_MMBT3904))]
_PNP_3906 = [("Sim.Device", "PNP"), ("Sim.Type", "GUMMELPOON"),
             ("Sim.Pins", "1=B 2=E 3=C"), ("Sim.Params", _params(_M_MMBT3906))]

R = "Resistor_SMD:R_0603_1608Metric"
R1206 = "Resistor_SMD:R_1206_3216Metric"
C = "Capacitor_SMD:C_0603_1608Metric"
C1206 = "Capacitor_SMD:C_1206_3216Metric"
CP = "Capacitor_SMD:CP_Elec_6.3x5.4"
SOT23 = "Package_TO_SOT_SMD:SOT-23"
SOT343 = "Package_TO_SOT_SMD:SOT-343_SC-70-4"
HDR = "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical_SMD_Pin1Left"

NPN = "Transistor_BJT:Q_NPN_BEC"
PNP = "Transistor_BJT:Q_PNP_BEC"
RES = "Device:R"
CAP = "Device:C"
CAPP = "Device:C_Polarized"

# Whole drawing is shifted by this many grid units to centre it on A3.
X0, Y0 = 20, 14


def mm(n):
    """Schematic grid: 1 unit = 1.27 mm, so every pin lands on the KiCad grid."""
    return round(n * 1.27, 2)


def at(x, y):
    """Grid units (before the centring shift) -> sheet millimetres."""
    return (mm(x + X0), mm(y + Y0))


# ---- placement -------------------------------------------------------------
# (ref, lib_id, value, x, y, angle, mirror, footprint) in grid units.
#
# Pin geometry, in grid units relative to the symbol origin:
#   NPN, 0 deg          : B (-4, 0)  C (+2, -4)  E (+2, +4)    base left
#   NPN, mirror y       : B (+4, 0)  C (-2, -4)  E (-2, +4)    base right
#   PNP, 0 deg mirror x : B (-4, 0)  E (+2, -4)  C (+2, +4)    base left
#   PNP, 180 deg        : B (+4, 0)  E (-2, -4)  C (-2, +4)    base right
#   R / C, 0 deg        : pin 1 (0, -3)  pin 2 (0, +3)
#   R, 90 deg           : pin 1 (-3, 0)  pin 2 (+3, 0)
_PLACE = [
    # ---- lower band: I/O ----
    ("J1", "Connector_Generic:Conn_01x06", "I/O", 28, 128, 0, "y", HDR),

    # ---- lower band: cascode bias dividers ----
    ("R4", RES, "6.8k", 72, 121, 0, None, R),
    ("R9", RES, "8.2k", 72, 131, 0, None, R),
    ("C4", CAP, "100n", 78, 129, 0, None, C),
    ("R10", RES, "6.8k", 100, 121, 0, None, R),
    ("R11", RES, "11k", 100, 131, 0, None, R),
    ("C5", CAP, "100n", 108, 129, 0, None, C),
    ("C10", CAP, "100n", 116, 129, 0, None, C),

    # ---- lower band: supply decoupling ----
    # C1/C2 + C11/C12 sit at J1; C8/C9 sit at the output collectors (Q17/Q18)
    ("C1", CAP, "100n", 138, 127, 0, None, C),
    ("C11", CAP, "10u", 146, 127, 0, None, C1206),
    ("C8", CAP, "100n", 154, 127, 0, None, C),
    ("C2", CAP, "100n", 164, 127, 0, None, C),
    ("C12", CAP, "10u", 172, 127, 0, None, C1206),
    ("C9", CAP, "100n", 180, 127, 0, None, C),

    # ---- stage 1: mirror on top, cascodes, diff pair, tail at the bottom ----
    # left column (Q1 side) has its leads on x = 42, right column on x = 82
    ("R5", RES, "22", 42, 29, 0, None, R),
    ("R8", RES, "20", 82, 29, 0, None, R),
    ("Q4", PNP, "MMBTH81", 44, 36, 180, None, SOT23),
    ("Q6", PNP, "MMBTH81", 80, 36, 0, "x", SOT23),
    ("Q5", PNP, "MMBTH81", 44, 48, 180, None, SOT23),
    ("Q7", PNP, "MMBTH81", 80, 48, 0, "x", SOT23),
    ("Q8", PNP, "MMBTH81", 92, 42, 0, "x", SOT23),
    ("R6", RES, "22k", 94, 53, 0, None, R),
    ("Q3", NPN, "MMBT3904", 40, 60, 0, None, SOT23),
    ("Q1", NPN, "BFP420", 40, 72, 0, None, SOT343),
    ("Q2", NPN, "BFP420", 80, 72, 0, None, SOT343),
    ("R18", RES, "470", 62, 79, 0, None, R),
    ("Q10", NPN, "MMBT3904", 64, 86, 0, "y", SOT23),
    ("R3", RES, "180", 62, 93, 0, None, R),
    ("R1", RES, "13.7k", 96, 79, 0, None, R),
    ("Q9", NPN, "MMBT3904", 94, 86, 0, None, SOT23),
    ("R2", RES, "1k", 96, 93, 0, None, R),

    # ---- stage 2: cascoded follower into a Miller-compensated CE ----
    ("Q12", NPN, "MMBT3904", 128, 52, 0, None, SOT23),
    ("Q11", NPN, "BFP420", 128, 64, 0, None, SOT343),
    ("C7", CAP, "68p", 140, 65, 0, None, C),
    ("Q13", NPN, "BFP420", 152, 68, 0, None, SOT343),
    ("R19", RES, "1k", 154, 51, 0, None, R1206),
    ("R20", RES, "50", 154, 75, 0, None, R),
    ("C6", CAPP, "220u", 162, 75, 0, None, CP),

    # ---- output: cascoded follower, Vbe multiplier, class-AB pair ----
    ("Q15", NPN, "MMBT3904", 188, 46, 0, None, SOT23),
    ("Q14", NPN, "BFP420", 188, 58, 0, None, SOT343),
    ("R12", RES, "1.8k", 198, 67, 0, None, R),
    ("R13", RES, "1.2k", 198, 77, 0, None, R),
    ("Q19", NPN, "MMBT3904", 206, 72, 0, None, SOT23),
    ("C3", CAP, "100n", 222, 73, 0, None, C),
    ("R14", RES, "10k", 190, 87, 0, None, R),
    ("Q17", NPN, "MMBT3904", 232, 50, 0, None, SOT23),
    ("Q16", NPN, "BFP420", 232, 62, 0, None, SOT343),
    ("R15", RES, "4.7", 234, 69, 0, None, R),
    ("R16", RES, "4.7", 234, 77, 0, None, R),
    ("Q18", PNP, "MMBTH81", 232, 84, 0, "x", SOT23),
    ("R17", RES, "47", 244, 72, 90, None, R),
    ("R7", RES, "10k", 254, 75, 0, None, R),
]

COMPONENTS = [(ref, lib, val) + at(x, y) + (ang, mir, fp)
              for (ref, lib, val, x, y, ang, mir, fp) in _PLACE]
_GRID = {c[0]: (c[3], c[4]) for c in _PLACE}

NET = {
    ("J1", "1"): "OUT", ("J1", "2"): "INP", ("J1", "3"): "INN",
    ("J1", "4"): "GND", ("J1", "5"): "+15V", ("J1", "6"): "-15V",
    # bias
    ("R1", "1"): "+15V", ("R1", "2"): "vref",
    ("Q9", "1"): "vref", ("Q9", "2"): "veb", ("Q9", "3"): "vref",
    ("R2", "1"): "veb", ("R2", "2"): "-15V",
    ("Q10", "1"): "vref", ("Q10", "2"): "vet", ("Q10", "3"): "Tc",
    ("R3", "1"): "vet", ("R3", "2"): "-15V",
    ("R18", "1"): "T", ("R18", "2"): "Tc",
    # dividers
    ("R4", "1"): "+15V", ("R4", "2"): "vcn",
    ("R9", "1"): "vcn", ("R9", "2"): "-15V",
    ("C4", "1"): "vcn", ("C4", "2"): "GND",
    ("R10", "1"): "+15V", ("R10", "2"): "vcd",
    ("R11", "1"): "vcd", ("R11", "2"): "-15V",
    ("C5", "1"): "vcd", ("C5", "2"): "GND",
    ("C10", "1"): "vcd", ("C10", "2"): "GND",
    # stage 1
    ("Q1", "1"): "INN", ("Q1", "2"): "T", ("Q1", "3"): "a1",
    ("Q3", "1"): "vcn", ("Q3", "2"): "a1", ("Q3", "3"): "c1",
    ("Q2", "1"): "INP", ("Q2", "2"): "T", ("Q2", "3"): "c2",
    ("R5", "1"): "+15V", ("R5", "2"): "e3",
    ("R8", "1"): "+15V", ("R8", "2"): "e4",
    ("Q4", "1"): "c1", ("Q4", "2"): "e3", ("Q4", "3"): "n1",
    ("Q5", "1"): "vcp", ("Q5", "2"): "n1", ("Q5", "3"): "c1",
    ("Q6", "1"): "c1", ("Q6", "2"): "e4", ("Q6", "3"): "n2",
    ("Q7", "1"): "vcp", ("Q7", "2"): "n2", ("Q7", "3"): "c2",
    ("Q8", "1"): "n2", ("Q8", "2"): "+15V", ("Q8", "3"): "vcp",
    ("R6", "1"): "vcp", ("R6", "2"): "-15V",
    # buffer 1 + stage 2
    ("Q11", "1"): "c2", ("Q11", "2"): "d1", ("Q11", "3"): "x8",
    ("Q12", "1"): "vcd", ("Q12", "2"): "x8", ("Q12", "3"): "+15V",
    ("Q13", "1"): "d1", ("Q13", "2"): "e1", ("Q13", "3"): "d2",
    ("R19", "1"): "+15V", ("R19", "2"): "d2",
    ("R20", "1"): "e1", ("R20", "2"): "GND",
    ("C6", "1"): "e1", ("C6", "2"): "GND",
    ("C7", "1"): "d2", ("C7", "2"): "d1",
    # buffer 2 + output
    ("Q14", "1"): "d2", ("Q14", "2"): "d3", ("Q14", "3"): "x9",
    ("Q15", "1"): "vcd", ("Q15", "2"): "x9", ("Q15", "3"): "+15V",
    ("Q16", "1"): "d3", ("Q16", "2"): "n8", ("Q16", "3"): "xo",
    ("Q17", "1"): "vcd", ("Q17", "2"): "xo", ("Q17", "3"): "+15V",
    ("Q18", "1"): "b9", ("Q18", "2"): "n9", ("Q18", "3"): "-15V",
    ("Q19", "1"): "db", ("Q19", "2"): "b9", ("Q19", "3"): "d3",
    ("R12", "1"): "d3", ("R12", "2"): "db",
    ("R13", "1"): "db", ("R13", "2"): "b9",
    ("R14", "1"): "b9", ("R14", "2"): "-15V",
    ("R15", "1"): "n8", ("R15", "2"): "OUTA",
    ("R16", "1"): "OUTA", ("R16", "2"): "n9",
    ("C3", "1"): "d3", ("C3", "2"): "b9",
    ("R17", "1"): "OUTA", ("R17", "2"): "OUT",
    ("R7", "1"): "OUT", ("R7", "2"): "GND",
    # decoupling
    ("C1", "1"): "+15V", ("C1", "2"): "GND",
    ("C2", "1"): "-15V", ("C2", "2"): "GND",
    ("C11", "1"): "+15V", ("C11", "2"): "GND",
    ("C12", "1"): "-15V", ("C12", "2"): "GND",
    ("C8", "1"): "+15V", ("C8", "2"): "GND",
    ("C9", "1"): "-15V", ("C9", "2"): "GND",
}

POWER_NETS = {"+15V": ("power:+15V", 0), "-15V": ("power:-15V", 180),
              "GND": ("power:GND", 0)}

# Nets allowed to be drawn in several pieces joined by same-name labels.
# Everything else must be one continuous piece of wire.
CROSS = {"INP", "INN", "OUT", "vcn", "vcd", "vcp"}
# Signal nodes that carry a name tag only, so the drawing can be read against
# the README's topology description.  They must still be one drawn wire.
NAMED = {"c2", "d1", "d2", "d3"}


def _comp(ref):
    for c in COMPONENTS:
        if c[0] == ref:
            return c
    raise KeyError(ref)


def P(ref, pnum):
    """Pin position in sheet millimetres."""
    c = _comp(ref)
    _, lib, _, x, y, ang, mir = c[:7]
    return g.gpin(lib, pnum, x, y, ang, mir)


def _above(ref, up, down):
    a, b = P(ref, up), P(ref, down)
    if not (a[1] < b[1] - 1):
        raise SystemExit("%s pin %s should be above pin %s, got %s %s"
                         % (ref, up, down, a, b))


def _left_of(ref, pin, other):
    a, b = P(ref, pin), P(ref, other)
    if not (a[0] < b[0] - 1):
        raise SystemExit("%s pin %s should be left of pin %s, got %s %s"
                         % (ref, pin, other, a, b))


def _same(ref, pin, other_ref, other_pin, axis):
    a, b = P(ref, pin), P(other_ref, other_pin)
    i = 0 if axis == "x" else 1
    if abs(a[i] - b[i]) > 0.01:
        raise SystemExit("%s.%s and %s.%s should share %s: %s %s"
                         % (ref, pin, other_ref, other_pin, axis, a, b))


def _check_orientation():
    """Catch a transistor that was flipped by a placement edit."""
    for ref in ("Q1", "Q2", "Q3", "Q9", "Q11", "Q12", "Q13",
                "Q14", "Q15", "Q16", "Q17", "Q19"):
        _above(ref, "3", "2")          # NPN: collector above emitter
        _left_of(ref, "1", "3")        # base on the left
    _above("Q10", "3", "2")            # tail sink: base on the right,
    _left_of("Q10", "3", "1")          # facing its reference Q9
    for ref in ("Q4", "Q5"):
        _above(ref, "2", "3")          # PNP: emitter above collector
        _left_of(ref, "2", "1")        # base on the right, facing Q6/Q7
    for ref in ("Q6", "Q7", "Q8", "Q18"):
        _above(ref, "2", "3")          # PNP: emitter above collector
        _left_of(ref, "1", "2")        # base on the left
    _same("Q4", "3", "Q5", "2", "x")
    _same("Q6", "3", "Q7", "2", "x")
    _same("Q1", "2", "Q2", "2", "y")
    _same("Q2", "1", "Q1", "1", "y")
    _same("Q11", "2", "Q13", "1", "y")
    _same("Q14", "2", "Q16", "1", "y")
    _same("Q16", "2", "R15", "1", "x")
    _same("Q18", "2", "R16", "2", "x")


WIRES, LABELS, POWER, GLOBALS = [], [], [], []


def pt(x, y):
    """Grid point -> sheet point."""
    return at(x, y)


def link(points):
    """Orthogonal polyline through sheet points (mm).  Zero-length segments
    (coincident pins) are skipped."""
    for a, b in zip(points, points[1:]):
        if abs(a[0] - b[0]) > 0.01 and abs(a[1] - b[1]) > 0.01:
            raise SystemExit("diagonal wire %s -> %s" % (a, b))
        if abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) < 0.01:
            continue
        WIRES.append((a, b))


def wire(*pts):
    """Polyline whose points are pin tuples ('Q1', '2') or grid (x, y)."""
    out = []
    for p in pts:
        if isinstance(p[0], str):
            out.append(P(*p))
        else:
            out.append(pt(*p))
    link(out)
    return out[-1]


def label(name, gx, gy, justify="left"):
    """Local net label at a grid point (must be on a wire end)."""
    if name not in CROSS and name not in NAMED:
        raise SystemExit("%s is not a labelled net" % name)
    LABELS.append((name,) + pt(gx, gy) + (justify,))


GLOB_SHAPE = {"OUT": "output", "INP": "input", "INN": "input",
              "+15V": "passive", "-15V": "passive", "GND": "passive"}


def port(name, gx, gy, justify="left"):
    """Global label: the connector-facing nets (inputs, output, rails)."""
    GLOBALS.append((name,) + pt(gx, gy) + (justify, GLOB_SHAPE[name]))


# Power symbols.  By default a symbol sits right on the rail pin.  Where a
# wire carries the rail to a common row (so the arrows line up), the pin is
# listed here with the grid point the symbol moves to.
PWR_AT = {
    ("Q8", "2"): (94, 26),      # helper emitter up to the stage-1 +15 V row
    ("Q17", "3"): (234, 42),    # output cascode collector up to Q15's row
    ("Q18", "3"): (234, 90),    # output PNP collector down to R14's row
}


def _power(net, sheet_pt, ang=None):
    lib, a = POWER_NETS[net]
    POWER.append(("#PWR%03d" % (len(POWER) + 1), lib, net,
                  sheet_pt[0], sheet_pt[1], a if ang is None else ang))


def _build():
    _check_orientation()

    # ======================= lower band: I/O ==========================
    # Every connector pin gets a stub of the same length and a port label,
    # so the pin functions read as a column next to the header.
    for pin in "123456":
        x, y = P("J1", pin)
        end = (round(x + mm(6), 2), y)
        link([(x, y), end])
        GLOBALS.append((NET[("J1", pin)], end[0], end[1], "left",
                        GLOB_SHAPE[NET[("J1", pin)]]))

    # =================== lower band: cascode bias =====================
    for top, bot, caps, name in (("R4", "R9", ("C4",), "vcn"),
                                 ("R10", "R11", ("C5", "C10"), "vcd")):
        x = _GRID[top][0]
        wire((top, "2"), (bot, "1"))
        end = _GRID[caps[-1]][0] + 6
        wire(*([(x, 126)] + [(c, "1") for c in caps] + [(end, 126)]))
        label(name, end, 126)

    # ===================== lower band: supply =========================
    # Each rail: symbol, a short bus, its caps hanging off it, a PWR_FLAG.
    for net, caps, flag_x in (("+15V", ("C1", "C11", "C8"), 150),
                              ("-15V", ("C2", "C12", "C9"), 176)):
        x0 = _GRID[caps[0]][0]
        _power(net, pt(x0, 117), ang=0)        # both arrows up: rails on top
        wire((x0, 117), (caps[0], "1"))
        wire((x0, 121), (_GRID[caps[-1]][0], 121))
        for c in caps[1:]:
            wire((_GRID[c][0], 121), (c, "1"))
        POWER.append(("#FLG%02d" % (len(POWER) + 1), "power:PWR_FLAG", "PWR_FLAG")
                     + pt(flag_x, 121) + (0,))
    wire(("C9", "2"), (186, 130))
    POWER.append(("#FLG%02d" % (len(POWER) + 1), "power:PWR_FLAG", "PWR_FLAG")
                 + pt(186, 130) + (0,))

    # ========================== stage 1 ===============================
    # PNP mirror: Q4/Q5 (reference side) and Q6/Q7 (output side)
    wire(("Q4", "3"), ("Q5", "2"))                     # n1
    wire(("Q6", "3"), ("Q7", "2"))                     # n2
    wire((82, 42), ("Q8", "1"))                        # n2 -> helper base
    wire(("Q4", "1"), ("Q6", "1"))                     # mirror base bus, c1
    wire((52, 36), (52, 54), (42, 54))                 # c1 strap to Q5.C / Q3.C
    wire(("Q5", "3"), ("Q3", "3"))
    # cascode base line vcp; Q8/R6 generate it on the right
    wire(("Q5", "1"), (64, 48), ("Q7", "1"))
    label("vcp", 64, 48)
    wire(("Q8", "3"), ("R6", "1"))
    wire((94, 48), (100, 48))
    label("vcp", 100, 48)
    # input pair with Q3 cascoding Q1
    wire(("Q3", "2"), ("Q1", "3"))                     # a1
    wire(("Q7", "3"), ("Q2", "3"))                     # c2 column
    wire(("Q1", "2"), ("Q2", "2"))                     # emitter bus, T
    wire(("Q1", "1"), (30, 72))
    port("INN", 30, 72, "right")
    wire(("Q2", "1"), (68, 72))
    port("INP", 68, 72, "right")
    wire(("Q3", "1"), (30, 60))
    label("vcn", 30, 60, "right")
    # tail: R18 off the middle of the emitter bus, Q10 sink, Q9 reference
    wire(("Q10", "1"), ("Q9", "1"))                    # vref base line
    wire(("Q9", "3"), (88, 82), (88, 86))              # Q9 diode strap

    # ===================== stage 1 -> stage 2: c2 =====================
    wire((82, 64), ("Q11", "1"))
    label("c2", 100, 64)

    # ========================== stage 2 ===============================
    wire(("Q12", "2"), ("Q11", "3"))                   # x8
    wire(("Q11", "2"), ("Q13", "1"))                   # d1
    label("d1", 132, 68)
    wire(("R19", "2"), ("Q13", "3"))                   # d2 column
    wire(("C7", "1"), (154, 62))                       # Miller cap top -> d2
    wire(("Q13", "2"), ("C6", "1"))                    # e1 -> bypass cap
    wire(("Q12", "1"), (118, 52))
    label("vcd", 118, 52, "right")

    # ===================== stage 2 -> output: d2 ======================
    wire((154, 58), ("Q14", "1"))
    label("d2", 164, 58)

    # ========================== output ================================
    wire(("Q15", "2"), ("Q14", "3"))                   # x9
    wire(("Q17", "2"), ("Q16", "3"))                   # xo
    wire(("Q15", "1"), (182, 46))
    label("vcd", 182, 46, "right")
    wire(("Q17", "1"), (222, 50))
    label("vcd", 222, 50, "right")
    # d3: one horizontal from Q14's emitter to Q16's base, with three drops
    wire(("Q14", "2"), ("Q16", "1"))
    label("d3", 192, 62)
    wire((198, 62), ("R12", "1"))
    wire((208, 62), ("Q19", "3"))
    wire((222, 62), ("C3", "1"))
    # Vbe multiplier tap
    wire(("R12", "2"), ("R13", "1"))
    wire((198, 72), ("Q19", "1"))
    # b9: one horizontal from R14 to Q18's base, with three risers
    wire(("R14", "1"), ("Q18", "1"))
    wire(("R13", "2"), (198, 84))
    wire(("Q19", "2"), (208, 84))
    wire(("C3", "2"), (222, 84))
    # emitter resistors meet at OUTA, then R17 and the load to OUT
    wire(("R15", "2"), ("R16", "1"))
    wire((234, 72), ("R17", "1"))
    wire(("R17", "2"), ("R7", "1"), (260, 72))
    port("OUT", 260, 72)

    # ---- rail symbols on every rail pin except the connector ----
    for (ref, pnum), net in NET.items():
        if net not in POWER_NETS or ref == "J1":
            continue
        if (ref, pnum) in PWR_AT:
            dest = pt(*PWR_AT[(ref, pnum)])
            link([P(ref, pnum), dest])
            _power(net, dest)
        elif ref in ("C1", "C2", "C8", "C9", "C11", "C12") and pnum == "1":
            continue                                   # drawn with the supply
        else:
            _power(net, P(ref, pnum))


def _split(wires, points):
    out, changed = [], False
    for (a, b) in wires:
        (x1, y1), (x2, y2) = a, b
        pts = [a, b]
        for (px, py) in points:
            if abs(px - x1) < 0.01 and abs(py - y1) < 0.01:
                continue
            if abs(px - x2) < 0.01 and abs(py - y2) < 0.01:
                continue
            if abs(x1 - x2) < 0.01 and abs(px - x1) < 0.01 and min(y1, y2) < py < max(y1, y2):
                pts.append((px, py))
                changed = True
            elif abs(y1 - y2) < 0.01 and abs(py - y1) < 0.01 and min(x1, x2) < px < max(x1, x2):
                pts.append((px, py))
                changed = True
        pts = sorted(set(pts))
        for i in range(len(pts) - 1):
            if pts[i] != pts[i + 1]:
                out.append((pts[i], pts[i + 1]))
    return out, changed


def _finish_wires():
    """Split every T-junction, every pin and every label the wire passes
    through, and return the points that need a junction dot."""
    global WIRES
    labels = {(x, y) for (_n, x, y, _j) in LABELS}
    labels |= {(x, y) for (_n, x, y, _j, _s) in GLOBALS}
    labels |= {(x, y) for (_r, _l, _n, x, y, _a) in POWER}   # rail symbols, flags
    for _ in range(8):
        pts = {P(r, p) for (r, p) in NET} | labels
        for (a, b) in WIRES:
            pts.add(a)
            pts.add(b)
        WIRES, changed = _split(WIRES, pts)
        if not changed:
            break
    seen = set()
    uniq = []
    for (a, b) in WIRES:
        key = tuple(sorted((a, b)))
        if key in seen or a == b:
            continue
        seen.add(key)
        uniq.append((a, b))
    WIRES = uniq
    # A point joining three or more things (wire ends plus pins) gets a dot,
    # so a T where a wire meets two touching pins still reads as a junction.
    ends = {}
    for (a, b) in WIRES:
        ends[a] = ends.get(a, 0) + 1
        ends[b] = ends.get(b, 0) + 1
    for (r, p) in NET:
        q = P(r, p)
        if q in ends:
            ends[q] += 1
    return [p for p, n in ends.items() if n >= 3]


def _on_grid(pt_):
    return abs(pt_[0] / 1.27 - round(pt_[0] / 1.27)) < 1e-6 and \
        abs(pt_[1] / 1.27 - round(pt_[1] / 1.27)) < 1e-6


class _UF(object):
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def _audit():
    """Refuse a schematic whose wires short two nets or leave a pin hanging."""
    errors = []
    for (ref, pnum), net in NET.items():
        if not _on_grid(P(ref, pnum)):
            errors.append("off grid %s.%s %s" % (ref, pnum, P(ref, pnum)))
    for (a, b) in WIRES:
        if not _on_grid(a) or not _on_grid(b):
            errors.append("off-grid wire %s %s" % (a, b))

    uf = _UF()
    for (a, b) in WIRES:
        uf.union(a, b)

    # what each connected piece carries: pin nets, labels, rail symbols
    piece_nets = {}
    for (ref, pnum), net in NET.items():
        piece_nets.setdefault(uf.find(P(ref, pnum)), set()).add(net)
    named = {}
    for (name, x, y, _j) in LABELS:
        named.setdefault(uf.find((x, y)), set()).add(name)
    for (name, x, y, _j, _s) in GLOBALS:
        named.setdefault(uf.find((x, y)), set()).add(name)
    for (_r, lib, name, x, y, _a) in POWER:
        if lib != "power:PWR_FLAG":
            named.setdefault(uf.find((x, y)), set()).add(name)

    for root, nets in piece_nets.items():
        names = named.get(root, set())
        if len(nets | names) > 1:
            errors.append("short between %s" % ", ".join(sorted(nets | names)))
    for root, names in named.items():
        if root not in piece_nets:
            errors.append("label/symbol %s touches no pin" % sorted(names))
    # every symbol (flags included) must sit on a pin or a wire end
    ends = {q for w in WIRES for q in w} | {P(r, p) for (r, p) in NET}
    for (ref, _lib, name, x, y, _a) in POWER:
        if (x, y) not in ends:
            errors.append("%s (%s) is not on a wire end or pin" % (ref, name))

    groups = {}
    for (ref, pnum), net in NET.items():
        groups.setdefault(net, []).append((ref, pnum))
    for net, pins in groups.items():
        roots = {}
        for (ref, pnum) in pins:
            roots.setdefault(uf.find(P(ref, pnum)), []).append((ref, pnum))
        if net in POWER_NETS:
            for root, members in roots.items():
                if net not in named.get(root, ()):
                    errors.append("rail %s pins %s have no symbol" % (net, members))
        elif net in CROSS:
            for root, members in roots.items():
                if net not in named.get(root, ()):
                    errors.append("labelled net %s piece %s has no label" % (net, members))
        elif len(roots) != 1:
            errors.append("open net %s: %d pieces %s" % (net, len(roots), roots))
    return errors


_build()
JUNCTIONS = _finish_wires()
_AUDIT = _audit()

SIM_FIELDS = {}
# MPNs recorded on the symbols so sourcing tools can act on them.  The LCSC
# carrier codes are the ones documented in README.md.
MPN = {"BFP420": ("BFP420", "NXP", "C412737"),
       "MMBTH81": ("MMBTH81", "onsemi", "C190349"),
       "MMBT3904": ("MMBT3904", "onsemi", "C20526"),
       "MMBT3906": ("MMBT3906", "onsemi", "C20527")}
for c in COMPONENTS:
    ref, val = c[0], c[2]
    f = {"BFP420": _NPN_BFP, "MMBTH81": _PNP_H81,
         "MMBT3904": _NPN_3904, "MMBT3906": _PNP_3906}.get(val)
    if f:
        SIM_FIELDS[ref] = list(f)
    if val in MPN:
        m, maker, lcsc = MPN[val]
        SIM_FIELDS.setdefault(ref, []).extend(
            [("MPN", m), ("Manufacturer", maker), ("LCSC", lcsc)])
NO_SIM = {"J1"}


# ---- blocks, titles and notes ----------------------------------------------
# (title, subtitle, x1, y1, x2, y2) in grid units
BLOCKS = [
    ("STAGE 1", "differential input, cascoded PNP mirror load", 18, 13, 108, 104),
    ("STAGE 2", "buffer + Miller-compensated gain", 112, 13, 172, 104),
    ("OUTPUT", "buffer, Vbe multiplier, class-AB push-pull", 176, 13, 268, 104),
    ("I/O", "", 18, 110, 58, 146),
    ("CASCODE BIAS", "", 62, 110, 128, 146),
    ("SUPPLY", "decoupling + ERC flags", 132, 110, 192, 146),
]

TITLE_SIZE = 2.0
NOTE_X, NOTE_Y = 198, 114
NOTES = [
    "NOTES",
    "1. Signal path: INP/INN  ->  Q1/Q2 diff pair  ->  Q11 buffer  ->  Q13 CE gain",
    "    ->  Q14 buffer  ->  Q16/Q18 class-AB  ->  R17 47R  ->  OUT.",
    "2. C7 68p (Miller, Q13 base to collector) sets the dominant pole: 11.5 MHz at 60 dB.",
    "3. BFP420 (VCEO 4.5 V) is cascoded wherever it would see more than ~4 V:",
    "    Q3 over Q1, Q12 over Q11, Q15 over Q14, Q17 over Q16.",
    "4. Gain is set externally: non-inverting, Rf 10k / Rg 10R = 60 dB.",
    "    Keep the feedback network low impedance.",
    "5. Q19 / R12 / R13 Vbe multiplier sets the output-pair bias; R15/R16 degenerate it.",
    "6. R19 is 1206 (156 mW).  R7 10k is the on-board load.",
    "7. BFP420 is SOT-343: pad 4 is a second emitter, tie it to pad 2.",
    "8. LCSC: BFP420 C412737, MMBTH81 C190349, MMBT3904 C20526.",
    "9. Place C8/C9 at the Q17/Q18 collectors, C10 at Q12's base, C4 at Q3's base,",
    "    C5 at Q15/Q17's bases; C11/C12 (10u, 25 V min) at J1.",
]

# small italic annotations naming sub-circuits: (text, grid x, grid y)
ANNOT = [
    ("mirror", 56, 33),
    ("cascodes", 56, 46),
    ("input pair", 46, 80),
    ("tail sink", 65, 99),
    ("bias ref", 99, 99),
    ("Miller", 136, 71),
    ("Vbe multiplier", 196, 93),
]


def _texts():
    t = []
    for (title, sub, x1, y1, _x2, _y2) in BLOCKS:
        tx, ty = at(x1 + 1.5, y1 + 3)
        t.append((title, tx, ty, TITLE_SIZE, "bold"))
        if sub:
            t.append((sub, round(tx + mm(len(title) * 1.25 + 2), 2), ty, 1.27, "italic"))
    for i, line in enumerate(NOTES):
        x, y = at(NOTE_X, NOTE_Y + i * 2.5 + (1 if i else 0))
        if i == 0:
            t.append((line, x, y, TITLE_SIZE, "bold"))
        else:
            t.append((line, x, y))
    for (txt, x, y) in ANNOT:
        sx, sy = at(x, y)
        t.append((txt, sx, sy, 1.27, "italic"))
    return t


TEXTS = _texts()


# ---- reference / value placement -------------------------------------------
CH = 0.87          # average glyph advance at 1.27 mm, in grid units


def _side(ref):
    """Which side of the part its text goes on."""
    left = {"R5", "Q4", "Q5", "Q10", "R4", "R9", "R10", "R11",
            "R12", "R13", "R20", "J1", "C1", "C11", "C8", "C2", "C12", "C9"}
    return "left" if ref in left else "right"


def _clearance(lib, ang, mir):
    """Distance in grid units from the symbol origin to the text edge."""
    if lib.startswith("Transistor"):
        # body circle is centred 1 unit toward the leads, radius 2.2
        faces_left = (ang == 180) or (mir == "y")
        return 3.8 if not faces_left else 3.8
    if lib == CAPP:
        return 2.6
    if lib == CAP:
        return 2.4
    if lib.startswith("Connector"):
        return 2.4
    return 1.8


def _text_pos():
    tp = {}
    for (ref, lib, val, x, y, ang, mir, _fp) in _PLACE:
        if ang in (90, 270):
            # horizontal resistor: reference above, value below, centred
            tp[(ref, "Reference")] = at(x, y - 2.2) + (ang,)
            tp[(ref, "Value")] = at(x, y + 2.2) + (ang,)
            continue
        side = _side(ref)
        d = _clearance(lib, ang, mir)
        dy = 1.0
        if lib.startswith("Connector"):
            y = y + 1          # centre on the pin column
        for name, txt, oy in (("Reference", ref, -dy), ("Value", val, dy)):
            w = len(txt) * CH
            cx = x + d + w / 2.0 if side == "right" else x - d - w / 2.0
            # snap to 0.01 mm; text need not sit on the grid
            sx, sy = at(cx, y + oy)
            tp[(ref, name)] = (round(sx, 2), round(sy, 2))
    return tp


def main():
    if _AUDIT:
        print("AUDIT FAILED:")
        for e in _AUDIT:
            print("  ", e)
        raise SystemExit(1)
    g.COMPONENTS = COMPONENTS
    g.SHEET_W, g.SHEET_H = 420, 297
    g.TEXT_POS = _text_pos()
    g.POWER = POWER
    g.WIRES = WIRES
    g.JUNCTIONS = JUNCTIONS
    g.LABELS = LABELS
    g.GLOBALS = GLOBALS
    g.TEXTS = TEXTS
    g.SIM_FIELDS = SIM_FIELDS
    g.NO_SIM = NO_SIM
    g.HIDE_PIN_NUMBERS = {"Q_NPN_BEC", "Q_PNP_BEC"}
    g.RECTS = [at(x1, y1) + at(x2, y2) for (_t, _s, x1, y1, x2, y2) in BLOCKS]

    body, _moved = g.emit()
    body = body.replace('(paper "A4")', '(paper "A3")')
    body = body.replace('Discrete JFET-Input Op Amp', 'Discrete Two-Stage Op Amp (Rev E)')
    body = body.replace('Discrete operational amplifier, +/-15V, Aol>=60dB, GBW=10MHz',
                        'Discrete op amp, +/-15V, two-stage, 60dB closed loop, 11.5MHz')
    body = body.replace('Rev B: mirror active load, input buffer, Vos trim, Vbe output bias',
                        'Rev E: two-stage Miller-compensated, cascoded BFP420, class-AB output')
    body = body.replace('(rev "B")', '(rev "E")')

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opamp.kicad_sch")
    with open(out, "w") as f:
        f.write(body)
    print("wrote", out, len(body), "bytes")
    print("components=%d power=%d wires=%d labels=%d globals=%d junctions=%d"
          % (len(COMPONENTS), len(POWER), len(WIRES), len(LABELS), len(GLOBALS), len(JUNCTIONS)))


if __name__ == "__main__":
    main()
