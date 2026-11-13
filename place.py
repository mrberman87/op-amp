#!/usr/bin/env python3
"""Resize the board to 50 x 40 mm and re-place every unlocked part, in place.

Like rearrange.py this edits the existing board rather than regenerating it:
locked footprints (J1), the design rules, the stackup and the pours are kept.
The outline stays anchored at its current top-left corner, and the four plane
pours are resized to the new outline (In2.Cu keeps its +15 V / -15 V split).

Placement is a simulated anneal on a 0.25 mm grid using real pad positions:

  cost =  sum over signal nets of  weight * half-perimeter of its pads
        + matched pairs (Q1/Q2, Q4/Q6, Q5/Q7, Q9/Q10) kept adjacent and alike
        + C1 / C2 kept by the J1 rail pins, C4 / C5 by their bias divider
        + a penalty for courtyard overlap and for leaving the board

Net weights are the ones rearrange.py and gen_pcb.py use: high-impedance
analog nodes 4x, the I/O 3x, the rails nearly free because they are planes.

Hard rules for the result: courtyards at least GAP apart (room for one 0.2 mm
track between any two parts, since signals route on F.Cu) and at least EDGE
from the outline.

Usage:
    python3 place.py                 resize + place + write opamp.kicad_pcb
    python3 place.py --dry-run       report only, write nothing
    python3 place.py --seed 3        try another anneal seed
    python3 place.py --out X.kicad_pcb   write a candidate elsewhere
"""
import argparse
import math
import os
import random

import pcbnew

import gen_sch_rf as sch

ROOT = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(ROOT, "opamp.kicad_pcb")

W, H = 50.0, 40.0          # board size, mm
EDGE = 1.0                 # courtyard to board edge, mm
GAP = 1.0                  # courtyard to courtyard, mm (a track plus silk labels)
GAP_MIN = 0.8              # what the legality test accepts (the anneal aims for GAP)
GRID = 0.25                # placement grid, mm

POWER = {"+15V", "-15V", "GND"}
RAIL_W = 15.0              # per mm a rail pad sits outside its own In2.Cu pour
THERM_W = 2.0              # thermal-gradient weight across matched pairs

# In2.Cu: +15 V on the top half, -15 V on the bottom half, a GND corridor
# between them (below).  J1 is pinned to match: pin 1 (+15 V) lands in the
# +15 V pour, pin 6 (-15 V) in the -15 V pour, pin 4 (OUT) on the corridor.
# C1/C11 sit in the upper half, over the main +15 V plane.

# J1: 6-way 3.5 mm screw terminal on the left edge, wire entries facing out,
# pin 1 at the top.  (board-local centre of pin 1, rotation)
J1_PLACE = (5.9, 10.5, 270)         # pin-1 arrow silk stays on the board
UPPER = {"C1", "C11"}
EDGE_PARTS = {"J1"}            # edge connector: its courtyard may meet the edge          # must sit wholly in the upper (+15 V) half
TARGET = {
          # power test points near the board edge, easy to probe
          "TP1": (45.5, 5.0), "TP2": (44.0, 32.0), "TP3": (30.0, 35.0)}
# In2.Cu GND corridor between the rail pours, lined up with J1 pin 4 (OUT,
# y = 21.1).  OUTA and OUT run from the output stage to R24 / J1 on B.Cu
# straight along it, so they have a GND reference the whole way and stay
# under In1's solid GND, never beside an F.Cu high-impedance node.
CORR_TOP, CORR_BOT = 19.5, 22.5
SPLIT_TOP, SPLIT_BOT = CORR_TOP - 0.5, CORR_BOT + 0.5   # rail pour edges
CORR_Y = 21.0              # B.Cu track centre line for OUT / OUTA
# In2.Cu also carries a GND frame FRAME mm wide round the board edge: OUT runs
# on B.Cu along the edge, and B.Cu's nearest plane is In2, so the frame gives
# OUT a GND reference instead of the rail pours.  The perimeter stitching vias
# tie the frame to In1 and B.Cu.  The rail pours sit inside it.
FRAME = 2.5
CORNER_R = 2.0             # board corner radius, mm

# Footprints that exist only on the board (not in the schematic).
BOARD_ONLY = {
    "H1": ("MountingHole", "MountingHole_3.2mm_M3"),
    "H2": ("MountingHole", "MountingHole_3.2mm_M3"),
    "FID1": ("Fiducial", "Fiducial_1mm_Mask2mm"),
    "FID2": ("Fiducial", "Fiducial_1mm_Mask2mm"),
    "FID3": ("Fiducial", "Fiducial_1mm_Mask2mm"),
}
HOLES = {"H1", "H2"}

BOARD_ID = "DISCRETE OP AMP REV E"

HIGH_Z = {"c2", "d1", "d2", "d3", "a1", "n1", "n2", "vcp", "e3", "e4", "x8",
          "x9", "xo", "db", "b9", "n8", "n9", "e1", "Tc", "vet", "veb", "T",
          "c2b", "d2b", "d3b"}

# Ratsnest-crossing classes.  On a single signal layer every crossing is a
# B.Cu hop or a jumper: never acceptable on the stage-2 signal / AC-ground
# nets, cheap on the bypassed DC bias lines.  OUT is excluded: it is routed
# round the board edge through the reserved strip, not along its ratsnest.
NO_CROSS = {"e1", "d1", "d2", "c2", "c2b", "d2b", "d3b"}
DC_BIAS = {"vcd", "vcn", "vcp"}
EDGE_ROUTED = {"OUT", "OUTA"}   # B.Cu, along the In2 GND corridor


def cross_factor(net):
    if net in EDGE_ROUTED:
        return 0.0
    if net in NO_CROSS:
        return 5.0
    if net in DC_BIAS:
        return 0.5
    if net in HIGH_Z:
        return 2.0
    return 1.0


# Steady-state dissipation, mW, from sim/stress_two.py.  Used to keep the heat
# sources symmetric about the matched pairs (an uneven gradient is offset).
HEAT = {"R19": 156, "Q10": 75, "Q3": 67, "Q7": 62, "R1": 55, "R18": 51,
        "Q18": 38, "R6": 37, "R9": 32, "Q17": 31, "R11": 31, "R4": 28,
        "R14": 22, "Q2": 20, "R3": 20, "R10": 20, "Q13": 19, "Q15": 18}


def net_weight(net):
    if net in POWER:
        return 0.0
    if net in EDGE_ROUTED:
        return 0.5           # B.Cu along the corridor: length is cheap
    if net == "d2":
        return 6.0           # stage-2 output into Q14's base: keep it short
    if net in HIGH_Z:
        return 4.0
    if net in ("INP", "INN", "OUT"):
        return 3.0
    return 1.0


# Hand floorplan used as the starting point (board-local mm, centre, rotation).
# Signal flow runs left to right along the top and comes back down the middle:
#   * stage 1 (Q1/Q2 pair, Q3 cascode, Q4-Q8 mirror) beside J1's input pins,
#     the tail / bias reference (Q9, Q10) below it on the -15 V side;
#   * stage 2 along the top: Q11 follower -> Q13 CE (R19 load above it) ->
#     R22 -> Q14 follower, all within a few mm so the high-impedance d1/d2
#     nodes stay short.  Q13 faces its pins: base and the Miller cap C7 on
#     the upper left, collector up/right to R19 and R22, emitter down/right to
#     C13, R20 and the 220 uF C6, so e1 never has to cross d1 or d2;
#   * output stage as one column straddling the In2 GND corridor: Q17/Q16
#     (NPN half, +15 V side) above, Q19 (Vbe multiplier) between and touching
#     both output devices so the bias tracks their temperature, Q18 (PNP,
#     -15 V side) below, R15/R16 meeting at OUTA beside them, R17 right there;
#   * OUT and OUTA go back to J1 / R24 on B.Cu along the corridor.
PLAN = {
    # stage 1
    "Q2": (12.5, 16.0, 0), "Q1": (12.5, 18.75, 0),
    "R24": (12.75, 21.75, 180), "R25": (12.75, 24.5, 0),
    "Q7": (18.25, 14.5, 90), "Q8": (17.5, 18.5, 270), "Q6": (27.0, 19.5, 180),
    "R8": (28.0, 15.0, 270),
    "Q3": (17.5, 24.25, 180), "Q5": (22.25, 24.0, 90), "Q4": (27.25, 24.0, 180),
    "R5": (30.75, 17.5, 270), "R6": (22.5, 28.75, 0),
    "C4": (19.5, 28.5, 270), "R4": (33.0, 17.0, 90), "R9": (25.25, 31.75, 0),
    # tail current source and its reference
    "R18": (11.75, 28.0, 270), "Q10": (12.5, 32.5, 90), "Q9": (17.0, 32.5, 90),
    "R1": (24.5, 16.75, 90), "R2": (18.75, 36.25, 0), "R3": (14.25, 36.25, 0),
    "C2": (4.75, 32.25, 180), "C12": (8.5, 33.75, 270),
    # stage 2 along the top
    "C6": (30.0, 14.25, 0),
    "Q12": (13.5, 11.0, 180), "Q11": (17.25, 11.0, 180), "R21": (20.5, 13.25, 180),
    "C10": (16.5, 9.75, 0), "C1": (25.5, 1.75, 0), "C11": (9.25, 4.25, 90),
    "C7": (20.25, 7.75, 270), "Q13": (23.0, 9.5, 90), "R19": (23.5, 4.5, 270),
    "C13": (24.75, 12.75, 270), "R20": (27.0, 11.0, 90),
    "R22": (26.25, 9.0, 0), "Q14": (29.5, 8.5, 90), "Q15": (31.0, 4.0, 0),
    "C14": (28.0, 2.25, 180),
    # vcd divider (DC, bypassed at every cascode base)
    "R10": (34.25, 10.0, 90), "R11": (33.25, 29.5, 90), "TP5": (30.0, 29.5, 0),
    # output stage column on the corridor
    "R23": (34.0, 14.75, 0),
    "Q17": (39.5, 11.5, 0), "C8": (42.5, 11.5, 0), "C5": (36.5, 8.5, 0),
    "Q16": (38.0, 15.75, 90),
    "R12": (34.5, 18.5, 90), "R13": (34.5, 22.75, 90), "C3": (34.5, 26.0, 90),
    "Q19": (38.0, 20.75, 0),
    "Q18": (38.0, 25.75, 180), "C9": (36.0, 29.25, 270), "R14": (40.5, 29.5, 0),
    "R15": (41.75, 17.75, 270), "R16": (41.75, 23.75, 90),
    "R17": (44.5, 21.0, 270), "R7": (47.0, 24.5, 90),
    # test points
    "TP1": (45.5, 6.0, 0), "TP2": (44.5, 31.0, 0), "TP3": (30.0, 35.0, 0),
    "TP4": (28.5, 28.5, 0), "TP6": (45.0, 16.5, 0), "TP7": (47.0, 20.5, 0),
    "TP8": (47.0, 24.0, 0),
    # board-only: mounting holes on the diagonal, fiducials on three corners
    "H1": (3.6, 3.6, 0), "H2": (46.4, 36.4, 0),
    "FID1": (47.5, 2.5, 0), "FID2": (11.0, 35.5, 0), "FID3": (30.0, 36.0, 0),
}
# where the fiducials want to be (corner-ish, asymmetric)
FID_TARGET = {"FID1": (47.5, 2.5), "FID2": (11.0, 36.0), "FID3": (34.0, 36.0)}

# Parts the refine pass may not move.  R17/R7 stay at the bottom-right so OUT
# leaves the output stage and runs back to J1 pin 1 along the board edges; C6
# (the 220 uF can) fills the dead corner above J1 instead of sitting in the
# stage-2 -> output path.
FIXED = {"H1", "H2", "C6", "C11"}   # hand-placed: the 220 uF can below-right of Q13 (its emitter
# side, so e1 never crosses d1/d2), the +15 V bulk cap at J1 pin 1

# Courtyard-free strips (x0, y0, x1, y1).  None now: OUT returns to J1 pin 1
# on B.Cu (J1 is plated-through), shielded from the F.Cu high-Z nodes by the
# In1.Cu GND plane, so no F.Cu edge strip is needed.
KEEPOUT = []

# matched pairs: (a, b, max centre distance mm, weight); same rotation too.
# Q1/Q2 may nearly touch (PAIR_GAP) so their emitters can share one T pad.
# Q5/Q7 are cascodes: their Vbe mismatch barely moves the mirror current, so
# they are only kept loosely together.  Q4/Q6 set the mirror ratio (offset).
PAIRS = [("Q1", "Q2", 2.75, 20.0), ("Q4", "Q6", 3.25, 20.0),
         ("Q5", "Q7", 6.0, 2.0), ("Q9", "Q10", 5.0, 3.0)]
PAIR_GAP = 0.3
# Base stoppers may sit closer to their neighbours than GAP: a stopper only
# works right on its base, and KiCad itself only forbids courtyard overlap.
TIGHT = {"R21", "R22", "R23"}
TIGHT_GAP = 0.25
THERMAL_PAIRS = [("Q1", "Q2"), ("Q4", "Q6")]
# (part, pad, anchor part, anchor pad, weight): decoupling and bypass placement
ATTRACT = [("C2", "1", "J1", "6", 1.0), ("C11", "1", "J1", "1", 1.0),
           ("C12", "1", "J1", "6", 1.0),
           ("C8", "1", "Q17", "3", 4.0), ("C9", "1", "Q18", "3", 8.0),
           ("C10", "1", "Q12", "1", 8.0), ("C5", "1", "Q17", "1", 4.0),
           ("C4", "1", "Q3", "1", 2.0), ("C6", "1", "Q13", "2", 3.0),
           ("C3", "1", "Q19", "3", 6.0), ("C3", "2", "Q19", "2", 3.0),
           # the Vbe multiplier is one tight cell: its divider on Q19's base,
           # R14 (b9 pull-down) at Q18's base
           ("R12", "2", "Q19", "1", 3.0), ("R13", "1", "Q19", "1", 3.0),
           ("R14", "1", "Q18", "1", 3.0),
           # base stoppers belong on the base pad they protect
           ("R21", "2", "Q11", "1", 6.0), ("R22", "2", "Q14", "1", 6.0),
           ("R23", "2", "Q16", "1", 6.0),
           # second bypasses: ceramic at Q13's emitter, local cap at Q15's base
           ("C13", "1", "Q13", "2", 12.0), ("C14", "1", "Q15", "1", 4.0),
           # feedback network at the inverting input (Q1's base): the long
           # run is OUTA (low impedance), not the INN node
           ("R24", "2", "Q1", "1", 4.0), ("R25", "1", "Q1", "1", 4.0),
           # Miller cap straight across Q13's base and collector
           ("C7", "2", "Q13", "1", 2.0), ("C7", "1", "Q13", "3", 2.0),
           # local decoupling of the cascode collectors that carry signal
           # current: C1 at Q12 (C8 / C9 at the output devices are above)
           ("C1", "1", "Q12", "3", 1.5),
           # Vbe multiplier touching both output devices (bias tracks their
           # temperature); emitter resistors on their emitters
           ("Q19", "2", "Q18", "1", 4.0), ("Q19", "3", "Q16", "1", 4.0),
           ("R15", "1", "Q16", "2", 3.0), ("R16", "2", "Q18", "2", 3.0),
           # isolation resistor, load and test points at the OUTA node
           ("R17", "1", "R15", "2", 2.0), ("R17", "1", "R16", "1", 2.0),
           ("TP6", "1", "R17", "1", 1.0), ("TP7", "1", "R17", "2", 1.0),
           ("R7", "1", "R17", "2", 1.0), ("TP8", "1", "TP7", "1", 2.0),
           # mirror emitter resistors on their emitters (both sides alike)
           ("R5", "2", "Q4", "2", 4.0), ("R8", "2", "Q6", "2", 4.0),
           # the follower sits by the node it buffers; the vcd divider together
           ("Q11", "1", "Q7", "3", 2.0), ("R10", "2", "R11", "1", 2.0),
           # tail resistor on the pair's emitters
           ("R18", "1", "Q1", "2", 1.0),
           # bias dividers stay over their own circuit: R1 just above the
           # corridor over Q9 (short +15 V via, short vref), R4 likewise over Q3
           ("R1", "2", "Q9", "3", 3.0), ("R4", "2", "Q3", "1", 6.0),
           ("R9", "1", "Q3", "1", 2.0), ("TP4", "1", "C4", "1", 1.0)]


# After the anneal: parts placed at the legal spot nearest their anchor pads
# (Placer.snug).  The Vbe multiplier's speed-up cap belongs across Q19, and the
# output-stage rail caps on their transistors' supply pins.
SNUG = [# base stoppers right on the base they protect (their job is undone
        # by any trace between them and the base); lightly pulled towards
        # the node they come from, so they line up without crossing it
        ("R21", [("2", "Q11", "1", 3.0), ("1", "Q7", "3", 1.0)], 6.0),
        # bypass caps on the pins they bypass
        ("C13", [("1", "Q13", "2")], 6.0), ("C10", [("1", "Q12", "1")], 6.0),
        ("C14", [("1", "Q15", "1")], 6.0), ("C5", [("1", "Q17", "1")], 6.0),
        ("C3", [("1", "Q19", "3"), ("2", "Q19", "2")]),
        ("C8", [("1", "Q17", "3")]), ("C9", [("1", "Q18", "3")]),
        # scope ground beside the OUT probe pad
        ("TP8", [("1", "TP7", "1")], 8.0)]

# --polish: hand moves applied to the current placement before SNUG.
#  * Q4 turns to 270 so its emitter faces R5 (e3 was 15 mm round Q6).
POLISH_HAND = {"Q4": (27.25, 24.75, 270)}


def _rect_dist(x, y, r):
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


def rail_miss(net, x, y, m=0.4):
    """How far (mm) a rail pad at (x, y) is from its own In2.Cu pour."""
    if net == "+15V":
        rects = [(FRAME + 0.5 + m, FRAME + 0.5 + m, W - FRAME - 0.5 - m, SPLIT_TOP - m)]
    else:
        rects = [(FRAME + 0.5 + m, SPLIT_BOT + m, W - FRAME - 0.5 - m, H - FRAME - 0.5 - m)]
    return min(_rect_dist(x, y, r) for r in rects)


def _cross(e, f):
    """True if segments e and f properly intersect (shared endpoints do not count)."""
    (a, b), (c, d) = e, f
    if a == c or a == d or b == c or b == d:
        return False
    if max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0]) or \
            max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1]):
        return False

    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 1e-9) - (v < -1e-9)
    return orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0


class Geometry(object):
    """Pad offsets and courtyard boxes per footprint, for each rotation."""

    def __init__(self, fp):
        self.pads = {}
        self.box = {}
        pos = fp.GetPosition()
        orig = fp.GetOrientationDegrees()
        for rot in (0, 90, 180, 270):
            fp.SetOrientationDegrees(rot)
            self.pads[rot] = {}
            for p in fp.Pads():
                q = p.GetPosition()
                self.pads[rot].setdefault(p.GetNumber(), (
                    (q.x - pos.x) / 1e6, (q.y - pos.y) / 1e6))
            cy = fp.GetCourtyard(pcbnew.F_CrtYd)
            bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
            self.box[rot] = ((bb.GetLeft() - pos.x) / 1e6, (bb.GetTop() - pos.y) / 1e6,
                             (bb.GetRight() - pos.x) / 1e6, (bb.GetBottom() - pos.y) / 1e6)
        fp.SetOrientationDegrees(orig)


class Placer(object):
    def __init__(self, board):
        self.board = board
        bb = board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = round(bb.GetX() / 1e6 + 0.05, 2), round(bb.GetY() / 1e6 + 0.05, 2)
        self.fp = {f.GetReference(): f for f in board.GetFootprints()}
        self.geo = {r: Geometry(f) for r, f in self.fp.items()}
        self.locked = {r for r, f in self.fp.items() if f.IsLocked()}
        self.pos = {r: (f.GetPosition().x / 1e6 - self.x0, f.GetPosition().y / 1e6 - self.y0)
                    for r, f in self.fp.items()}
        self.rot = {r: int(round(f.GetOrientationDegrees())) % 360 for r, f in self.fp.items()}
        self.movable = sorted(set(self.fp) - self.locked)
        # nets as lists of (ref, pad); SOT-343 pad 4 follows pad 2's net
        self.nets = {}
        for (ref, pin), net in sch.NET.items():
            if net_weight(net) > 0:
                self.nets.setdefault(net, []).append((ref, pin))
        self.rail_pads = [(r, p, 1 if n == "+15V" else -1)
                          for (r, p), n in sch.NET.items()
                          if n in ("+15V", "-15V") and r not in self.locked]
        self.cross_w = 0.0
        self.edges = {}
        # matched pairs may sit PAIR_GAP apart (closer = better matched)
        self.pair_set = {p for a, b, _d, _w in PAIRS for p in ((a, b), (b, a))
                         if {a, b} in ({"Q1", "Q2"}, {"Q4", "Q6"})}
        self.nets_of = {}
        for net, pins in self.nets.items():
            for ref, _ in pins:
                self.nets_of.setdefault(ref, set()).add(net)

    # ---- geometry ----
    def pad(self, ref, num):
        ox, oy = self.geo[ref].pads[self.rot[ref]][num]
        x, y = self.pos[ref]
        return x + ox, y + oy

    def cbox(self, ref):
        bx0, by0, bx1, by1 = self.geo[ref].box[self.rot[ref]]
        x, y = self.pos[ref]
        return x + bx0, y + by0, x + bx1, y + by1

    # ---- cost terms ----
    def net_cost(self, net):
        pts = [self.pad(r, p) for r, p in self.nets[net]]
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        return net_weight(net) * (max(xs) - min(xs) + max(ys) - min(ys))

    def pair_cost(self):
        tot = 0.0
        for a, b, dmax, w in PAIRS:
            (ax, ay), (bx, by) = self.pos[a], self.pos[b]
            tot += w * max(0.0, math.hypot(ax - bx, ay - by) - dmax)
            if self.rot[a] != self.rot[b]:
                tot += 6.0
        for a, b in THERMAL_PAIRS:
            (ax, ay), (bx, by) = self.pos[a], self.pos[b]
            for h, mw in HEAT.items():
                if h in (a, b):
                    continue
                hx, hy = self.pos[h]
                da = max(math.hypot(hx - ax, hy - ay), 2.5)
                db = max(math.hypot(hx - bx, hy - by), 2.5)
                tot += THERM_W * mw * abs(1.0 / da - 1.0 / db)
        for r, (tx, ty) in TARGET.items():
            x, y = self.pos[r]
            tot += 0.5 * (abs(x - tx) + abs(y - ty))
        for r in UPPER:
            tot += RAIL_W * max(0.0, self.cbox(r)[3] - (SPLIT_TOP - 0.3))
        for r, (tx, ty) in FID_TARGET.items():
            if r in self.pos:
                x, y = self.pos[r]
                tot += 1.0 * (abs(x - tx) + abs(y - ty))
        for r, p, ar, ap, w in ATTRACT:
            (x, y), (ax, ay) = self.pad(r, p), self.pad(ar, ap)
            tot += w * (abs(x - ax) + abs(y - ay))
        # a rail pad wants to sit over its own half of the In2.Cu split, so its
        # via drops straight into the right pour
        for r, p, sign in self.rail_pads:
            x, y = self.pad(r, p)
            tot += RAIL_W * rail_miss("+15V" if sign > 0 else "-15V", x, y)
        return tot

    # ---- ratsnest crossings: a proxy for single-layer (F.Cu) routability ----
    def mst(self, net):
        pts = [self.pad(r, p) for r, p in self.nets[net]]
        inside, rest, edges = [pts[0]], pts[1:], []
        while rest:
            a, b = min(((a, q) for a in inside for q in rest),
                       key=lambda t: abs(t[0][0] - t[1][0]) + abs(t[0][1] - t[1][1]))
            edges.append((a, b))
            inside.append(b)
            rest.remove(b)
        return edges

    def crossings(self, nets):
        """Weighted count of ratsnest crossings involving any net in `nets`."""
        if not self.cross_w:
            return 0.0
        tot = 0.0
        for n in nets:
            for m, other in self.edges.items():
                if m == n or (m in nets and m < n):
                    continue
                w = self.cross_w * min(cross_factor(n), cross_factor(m)) \
                    if 0.0 in (cross_factor(n), cross_factor(m)) else \
                    self.cross_w * max(cross_factor(n), cross_factor(m))
                for e in self.edges[n]:
                    for f in other:
                        if _cross(e, f):
                            tot += w
        return tot

    def part_violation(self, ref):
        """Overlap (with GAP) against every other part plus edge excursion."""
        x0, y0, x1, y1 = self.cbox(ref)
        v = 0.0
        if ref not in HOLES and ref not in EDGE_PARTS:
            v = max(0.0, EDGE - x0) + max(0.0, EDGE - y0) + \
                max(0.0, x1 - (W - EDGE)) + max(0.0, y1 - (H - EDGE))
            # rounded corners: the box corner nearest each board corner must
            # stay EDGE inside the arc
            R = CORNER_R
            for (cx, cy, px, py) in ((R, R, x0, y0), (W - R, R, x1, y0),
                                     (W - R, H - R, x1, y1), (R, H - R, x0, y1)):
                if (px - cx) * (cx - W / 2) > 0 and (py - cy) * (cy - H / 2) > 0:
                    v += max(0.0, math.hypot(px - cx, py - cy) - (R - EDGE))
            v *= 4.0
        for (k0, l0, k1, l1) in KEEPOUT:
            if ref in self.locked or ref in HOLES:
                break
            ox = min(x1, k1) - max(x0, k0)
            oy = min(y1, l1) - max(y0, l0)
            if ox > 0 and oy > 0:
                v += 4.0 * ox * oy + 2.0 * min(ox, oy)
        for other in self.fp:
            if other == ref:
                continue
            a0, b0, a1, b1 = self.cbox(other)
            g = PAIR_GAP if (ref, other) in self.pair_set else GAP
            if ref in TIGHT or other in TIGHT:
                g = min(g, TIGHT_GAP)
            ox = min(x1, a1) - max(x0, a0) + g
            oy = min(y1, b1) - max(y0, b0) + g
            if ox > 0 and oy > 0:
                v += ox * oy + 0.5 * min(ox, oy)
        return v

    def total_violation(self):
        return sum(self.part_violation(r) for r in self.fp) / 2.0

    def wire_cost(self):
        self.edges = {n: self.mst(n) for n in self.nets}
        return sum(self.net_cost(n) for n in self.nets) + self.pair_cost() + \
            self.crossings(set(self.nets)) / 1.0

    def crossing_count(self):
        w, self.cross_w = self.cross_w, 1.0
        self.edges = {n: self.mst(n) for n in self.nets}
        tot = 0
        for n in self.nets:
            for m in self.nets:
                if m <= n:
                    continue
                if n in EDGE_ROUTED or m in EDGE_ROUTED:
                    continue
                tot += sum(1 for e in self.edges[n] for f in self.edges[m] if _cross(e, f))
        self.cross_w = w
        return tot

    # ---- anneal ----
    def snap(self, v):
        return round(round(v / GRID) * GRID, 3)

    def anneal(self, iters, seed, T0=6.0, step0=6.0, swaps=True, lam0=2.0):
        rnd = random.Random(seed)
        lam1 = 400.0
        T1 = 0.02
        wire = self.wire_cost()
        viol = self.total_violation()
        best = None
        same_fp = {}
        for r in self.movable:
            same_fp.setdefault(self.fp[r].GetFPIDAsString(), []).append(r)
        swappable = [v for v in same_fp.values() if len(v) > 1]
        for it in range(iters):
            if it % 5000 == 0:
                viol = self.total_violation()           # stop float drift
            f = it / float(iters)
            T = T0 * (T1 / T0) ** f
            lam = lam0 * (lam1 / lam0) ** f
            step = max(GRID, step0 * (1 - f) ** 1.5)
            kind = rnd.random()
            saved_pos, saved_rot = {}, {}
            if kind < 0.70:
                r = rnd.choice(self.movable)
                saved_pos[r] = self.pos[r]
                x, y = self.pos[r]
                self.pos[r] = (self.snap(x + rnd.gauss(0, step)),
                               self.snap(y + rnd.gauss(0, step)))
            elif kind < 0.85:
                r = rnd.choice(self.movable)
                saved_rot[r] = self.rot[r]
                self.rot[r] = (self.rot[r] + rnd.choice((90, 180, 270))) % 360
                for a, b, _d, _w in PAIRS:  # matched pairs rotate together
                    o = b if r == a else a if r == b else None
                    if o is not None and o not in self.locked:
                        saved_rot[o] = self.rot[o]
                        self.rot[o] = self.rot[r]
            else:
                if not swappable or not swaps:
                    continue
                grp = rnd.choice(swappable)
                a, b = rnd.sample(grp, 2)
                saved_pos[a], saved_pos[b] = self.pos[a], self.pos[b]
                saved_rot[a], saved_rot[b] = self.rot[a], self.rot[b]
                self.pos[a], self.pos[b] = self.pos[b], self.pos[a]
                self.rot[a], self.rot[b] = self.rot[b], self.rot[a]
            touched = set(saved_pos) | set(saved_rot)
            # incremental: wire cost of touched nets, violation of touched parts
            nets = set()
            for r in touched:
                nets |= self.nets_of.get(r, set())
            new_pos, new_rot = dict(self.pos), dict(self.rot)
            for r, v in saved_pos.items():
                self.pos[r] = v
            for r, v in saved_rot.items():
                self.rot[r] = v
            old_w = sum(self.net_cost(n) for n in nets) + self.pair_cost() + \
                self.crossings(nets)
            old_v = sum(self.part_violation(r) for r in touched)
            old_edges = {n: self.edges[n] for n in nets}
            self.pos, self.rot = new_pos, new_rot
            if self.cross_w:
                for n in nets:
                    self.edges[n] = self.mst(n)
            new_w = sum(self.net_cost(n) for n in nets) + self.pair_cost() + \
                self.crossings(nets)
            new_v = sum(self.part_violation(r) for r in touched)
            delta = (new_w - old_w) + lam * (new_v - old_v)
            if delta <= 0 or rnd.random() < math.exp(-delta / T):
                wire += new_w - old_w
                viol += new_v - old_v
                if viol < 1e-6 and (best is None or wire < best[0]):
                    viol = self.total_violation()       # resync the running sum
                    if viol < 1e-9:
                        best = (wire, dict(self.pos), dict(self.rot))
            else:
                for r, v in saved_pos.items():
                    self.pos[r] = v
                for r, v in saved_rot.items():
                    self.rot[r] = v
                self.edges.update(old_edges)
        if best is not None:
            self.pos, self.rot = best[1], best[2]
        return self.wire_cost(), self.total_violation()

    def legal_violation(self):
        """Violation measured against GAP_MIN rather than the GAP target."""
        global GAP
        keep, GAP = GAP, GAP_MIN
        try:
            return self.total_violation()
        finally:
            GAP = keep

    def nocross(self, nets):
        """Crossings involving `nets` where either net is a no-cross net."""
        for n in nets:
            self.edges[n] = self.mst(n)
        k = 0
        for n in nets:
            for m, other in self.edges.items():
                if m == n or (m in nets and m < n) or not ({n, m} & NO_CROSS) \
                        or {n, m} & EDGE_ROUTED:
                    continue
                k += sum(1 for e in self.edges[n] for f in other if _cross(e, f))
        return k

    def snug(self, ref, links, radius=7.0):
        """Put `ref` at the legal spot (any rotation) nearest its anchor pads:
        minimise the summed pad-to-pad distance of `links` [(pad, anchor ref,
        anchor pad)].  For parts the anneal cannot thread through a crowd."""
        global GAP
        keep, GAP = GAP, GAP_MIN
        try:
            links = [l_ if len(l_) == 4 else l_ + (1.0,) for l_ in links]
            ax = [self.pad(a, ap) for _p, a, ap, _w in links]
            cx = sum(x for x, _y in ax) / len(ax)
            cy = sum(y for _x, y in ax) / len(ax)
            best = None
            saved = (self.pos[ref], self.rot[ref])
            self.edges = {n: self.mst(n) for n in self.nets}
            mynets = sorted(self.nets_of.get(ref, ()))
            base_x = self.nocross(mynets)
            n = int(radius / GRID)
            for rot in (0, 90, 180, 270):
                self.rot[ref] = rot
                for i in range(-n, n + 1):
                    for j in range(-n, n + 1):
                        self.pos[ref] = (self.snap(cx + i * GRID), self.snap(cy + j * GRID))
                        d = sum(w_ * math.hypot(self.pad(ref, p)[0] - self.pad(a, ap)[0],
                                                self.pad(ref, p)[1] - self.pad(a, ap)[1])
                                for p, a, ap, w_ in links)
                        if best is not None and d >= best[0]:
                            continue
                        if self.part_violation(ref) > 1e-9:
                            continue
                        # a rail pad must leave room for its via inside
                        # its own In2.Cu pour
                        if any(rail_miss(sch.NET[(ref, p)], *self.pad(ref, p), m=0.9) > 0
                               for p in self.geo[ref].pads[0]
                               if sch.NET.get((ref, p)) in ("+15V", "-15V")):
                            continue
                        # never trade a shorter link for a new crossing on
                        # a no-cross net
                        if self.nocross(mynets) > base_x:
                            continue
                        best = (d, self.pos[ref], rot)
            if best is None:
                self.pos[ref], self.rot[ref] = saved
                self.edges = {n: self.mst(n) for n in self.nets}
                return None
            self.pos[ref], self.rot[ref] = best[1], best[2]
            self.edges = {n: self.mst(n) for n in self.nets}
            return best[0]
        finally:
            GAP = keep

    def legalize_local(self, rounds=400, seed=0):
        """Clear small residual overlaps left by the anneal: move only parts
        that are still in violation, in small steps, accepting a move when it
        lowers the violation (wire cost may rise a little)."""
        rnd = random.Random(seed)
        steps = [(dx, dy) for dx in (-1.0, -0.5, -0.25, 0, 0.25, 0.5, 1.0)
                 for dy in (-1.0, -0.5, -0.25, 0, 0.25, 0.5, 1.0) if dx or dy]
        for _ in range(rounds):
            bad = [r for r in self.movable if self.part_violation(r) > 1e-9]
            if not bad:
                return True
            r = rnd.choice(bad)
            v0 = self.part_violation(r)
            nets = self.nets_of.get(r, set())
            w0 = sum(self.net_cost(n) for n in nets)
            best = None
            x, y = self.pos[r]
            for dx, dy in steps:
                self.pos[r] = (self.snap(x + dx), self.snap(y + dy))
                v = self.part_violation(r)
                if v < v0 - 1e-9:
                    w = sum(self.net_cost(n) for n in nets)
                    score = v * 1000 + (w - w0)
                    if best is None or score < best[0]:
                        best = (score, self.pos[r])
            self.pos[r] = best[1] if best else (x, y)
        return self.total_violation() < 1e-9

    # ---- report / write ----
    def spans(self):
        rows = []
        for net, pins in self.nets.items():
            pts = [self.pad(r, p) for r, p in pins]
            xs = [q[0] for q in pts]
            ys = [q[1] for q in pts]
            rows.append((net, max(xs) - min(xs) + max(ys) - min(ys), len(pts)))
        return sorted(rows, key=lambda r: -r[1])

    def apply(self):
        for r in self.movable:
            f = self.fp[r]
            x, y = self.pos[r]
            f.SetOrientationDegrees(self.rot[r])
            f.SetPosition(pcbnew.VECTOR2I(int(round((x + self.x0) * 1e6)),
                                          int(round((y + self.y0) * 1e6))))


def resize_outline_and_pours(board, x0, y0):
    def P(x, y):
        return pcbnew.VECTOR2I(int(round((x0 + x) * 1e6)), int(round((y0 + y) * 1e6)))

    edges = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    width = edges[0].GetWidth() if edges else pcbnew.FromMM(0.05)
    for d in edges:
        board.Remove(d)
    R = CORNER_R
    k = R * (1 - math.sqrt(0.5))          # arc midpoint inset from the corner
    lines = [(R, 0, W - R, 0), (W, R, W, H - R), (W - R, H, R, H), (0, H - R, 0, R)]
    arcs = [((W - R, 0), (W - k, k), (W, R)), ((W, H - R), (W - k, H - k), (W - R, H)),
            ((R, H), (k, H - k), (0, H - R)), ((0, R), (k, k), (R, 0))]
    for (a, b, c, e) in lines:
        sh = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
        sh.SetStart(P(a, b))
        sh.SetEnd(P(c, e))
        sh.SetLayer(pcbnew.Edge_Cuts)
        sh.SetWidth(width)
        board.Add(sh)
    for (st, mid, en) in arcs:
        sh = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_ARC)
        sh.SetArcGeometry(P(*st), P(*mid), P(*en))
        sh.SetLayer(pcbnew.Edge_Cuts)
        sh.SetWidth(width)
        board.Add(sh)

    m = 0.3
    f = FRAME + 0.5                           # rails keep 0.5 mm off the GND frame
    shapes = {
        ("GND", "In1.Cu"): [(m, m), (W - m, m), (W - m, H - m), (m, H - m)],
        ("GND", "B.Cu"): [(m, m), (W - m, m), (W - m, H - m), (m, H - m)],
        ("+15V", "In2.Cu"): [(f, f), (W - f, f), (W - f, SPLIT_TOP), (f, SPLIT_TOP)],
        ("-15V", "In2.Cu"): [(f, SPLIT_BOT), (W - f, SPLIT_BOT), (W - f, H - f), (f, H - f)],
    }
    frame_outer = [(m, m), (W - m, m), (W - m, H - m), (m, H - m)]
    # two holes: the GND frame plus the corridor band across the middle
    frame_holes = [[(FRAME, FRAME), (W - FRAME, FRAME), (W - FRAME, CORR_TOP), (FRAME, CORR_TOP)],
                   [(FRAME, CORR_BOT), (W - FRAME, CORR_BOT), (W - FRAME, H - FRAME),
                    (FRAME, H - FRAME)]]
    have_frame = False
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        if z.GetNetname() == "GND" and board.GetLayerName(z.GetFirstLayer()) == "In2.Cu":
            have_frame = True
            frame = z
    if not have_frame:
        tmpl = [z for z in board.Zones() if z.GetNetname() == "+15V"][0]
        frame = pcbnew.ZONE(board)
        frame.SetLayer(pcbnew.In2_Cu)
        frame.SetNet(board.FindNet("GND"))
        frame.SetLocalClearance(tmpl.GetLocalClearance())
        frame.SetMinThickness(tmpl.GetMinThickness())
        frame.SetPadConnection(tmpl.GetPadConnection())
        frame.SetThermalReliefGap(tmpl.GetThermalReliefGap())
        frame.SetThermalReliefSpokeWidth(tmpl.GetThermalReliefSpokeWidth())
        board.Add(frame)
    fpoly = frame.Outline()
    fpoly.RemoveAllContours()
    fpoly.NewOutline()
    for (x, y) in frame_outer:
        fpoly.Append(P(x, y).x, P(x, y).y)
    for frame_hole in frame_holes:
        hole = fpoly.NewHole()
        for (x, y) in frame_hole:
            fpoly.Append(P(x, y).x, P(x, y).y, 0, hole)
    frame.UnFill()
    rects = shapes
    done = set()
    for z in board.Zones():
        if z.GetIsRuleArea() or z.GetZoneName().startswith("thermal_"):
            continue                          # keepouts / local copper: not planes
        key = (z.GetNetname(), board.GetLayerName(z.GetFirstLayer()))
        if key == ("GND", "In2.Cu"):
            continue                          # the edge frame, shaped above
        if key not in rects:
            raise SystemExit("unexpected pour %s" % (key,))
        poly = z.Outline()
        poly.RemoveAllContours()
        poly.NewOutline()
        for (x, y) in shapes[key]:
            poly.Append(P(x, y))
        z.UnFill()
        done.add(key)
    if done != set(rects):
        raise SystemExit("pours missing: %s" % (set(rects) - done))
    # explicit priorities on In2: the rails win over the GND frame where they
    # meet (otherwise a UUID tie-break decides)
    for z in board.Zones():
        if not z.GetIsRuleArea() and board.GetLayerName(z.GetFirstLayer()) == "In2.Cu":
            z.SetAssignedPriority(1 if z.GetNetname() in ("+15V", "-15V") else 0)
    hole_keepouts(board, x0, y0)


HOLE_KEEPOUT_D = 7.0       # mm: no copper near a metal screw / standoff


def hole_keepouts(board, x0, y0):
    """A round copper keepout (rule area, every copper layer) on each mounting
    hole, so no rail copper sits 0.3 mm of resin away from an M3 screw.
    Idempotent: existing keepouts are reshaped, never removed."""
    have = {z.GetZoneName(): z for z in board.Zones() if z.GetIsRuleArea()}
    for ref, (hx, hy, _r) in (("H1", PLAN["H1"]), ("H2", PLAN["H2"])):
        name = "keepout_%s" % ref
        z = have.get(name)
        if z is None:
            z = pcbnew.ZONE(board)
            z.SetIsRuleArea(True)
            z.SetZoneName(name)
            board.Add(z)
        ls = pcbnew.LSET()
        for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            ls.AddLayer(l)
        z.SetLayerSet(ls)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        poly = z.Outline()
        poly.RemoveAllContours()
        poly.NewOutline()
        r = HOLE_KEEPOUT_D / 2
        for k in range(24):
            a = 2 * math.pi * k / 24
            px = int(round((x0 + hx + r * math.cos(a)) * 1e6))
            py = int(round((y0 + hy + r * math.sin(a)) * 1e6))
            poly.Append(px, py)


def _wanted():
    want = {c[0]: tuple(c[7].split(":")) for c in sch.COMPONENTS}
    want.update(BOARD_ONLY)
    return want


def strip_stale_footprints(path):
    """Return the board text with every footprint removed whose part no longer
    matches the schematic (or that is gone from it).  Done on the text, before
    pcbnew loads the board: BOARD.Remove() corrupts pcbnew's SWIG type table
    for the rest of the process.  The caller re-adds the parts via sync_parts."""
    import re
    src = open(path).read()
    want = _wanted()
    out, i, stripped = [], 0, []
    while True:
        k = src.find("\n\t(footprint ", i)
        if k < 0:
            out.append(src[i:])
            break
        depth, e = 0, k + 1
        while True:
            c = src[e]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            e += 1
        blk = src[k:e + 1]
        name = re.match(r'\n\t\(footprint "([^"]+)"', blk).group(1).split(":")[-1]
        ref = re.search(r'\(property "Reference" "([^"]+)"', blk).group(1)
        out.append(src[i:k])
        if ref in want and name == want[ref][1]:
            out.append(blk)
        else:
            stripped.append(ref)
        i = e + 1
    return "".join(out), stripped


def strip_routing(src):
    """Board text without tracks, arcs or vias (a new placement invalidates
    them).  Text-level for the same SWIG reason as strip_stale_footprints."""
    out, i, n = [], 0, 0
    heads = ("\n\t(segment", "\n\t(via", "\n\t(arc")
    while True:
        ks = [k for k in (src.find(h, i) for h in heads) if k >= 0]
        if not ks:
            out.append(src[i:])
            break
        k = min(ks)
        depth, e = 0, k + 1
        while True:
            c = src[e]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            e += 1
        out.append(src[i:k])
        n += 1
        i = e + 1
    return "".join(out), n


def _load_fp(lib, name):
    """Load a library footprint through the KiCad s-expression plugin directly
    (pcbnew.FootprintLoad's plugin lookup breaks once a board is loaded)."""
    fp = pcbnew.FootprintLoad(os.path.join("/usr/share/kicad/footprints", lib + ".pretty"), name)
    if fp is None:
        raise SystemExit("cannot load %s:%s" % (lib, name))
    return fp


def _net(board, name):
    ni = board.FindNet(name)
    if ni is None:                         # a net new in the schematic
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
    return ni


def stamp_nets(board):
    """Every pad gets the net the schematic table gives its pin (SOT-343 pad 4
    follows pad 2).  Returns the pads whose net changed."""
    changed = []
    for f in board.GetFootprints():
        ref = f.GetReference()
        if ref in BOARD_ONLY:
            continue
        pins = {pin: net for (r, pin), net in sch.NET.items() if r == ref}
        for pad in f.Pads():
            net = pins.get(pad.GetNumber())
            if net is None and pad.GetNumber() == "4" and "2" in pins:
                net = pins["2"]
            if net is None:
                raise SystemExit("%s pad %s has no net" % (ref, pad.GetNumber()))
            if pad.GetNetname() != net:
                changed.append("%s.%s %s->%s" % (ref, pad.GetNumber(), pad.GetNetname(), net))
                pad.SetNet(_net(board, net))
    return changed


def sync_parts(board):
    """Make the board's footprint set match the schematic table plus the
    board-only parts (holes, fiducials): add what is missing with its nets,
    replace a footprint whose library part changed, drop what is gone.
    New parts start at the board origin; the placer moves them."""
    want = _wanted()
    have = {f.GetReference(): f for f in board.GetFootprints()}
    stale = [r for r, f in have.items()
             if r not in want or f.GetFPID().GetLibItemName().wx_str() != want[r][1]]
    if stale:
        raise SystemExit("stale footprints %s: strip them before loading" % stale)
    loaded = {ref: _load_fp(*want[ref]) for ref in want if ref not in have}
    eb = board.GetBoardEdgesBoundingBox()
    ex, ey = eb.GetX(), eb.GetY()
    added, removed = [], []
    # stamp the library link (gen_pcb.py left the nickname empty), so KiCad's
    # "update footprints from library" and its library checks can find them
    for f in board.GetFootprints():
        lib, name = want[f.GetReference()]
        f.SetFPID(pcbnew.LIB_ID(lib, name))
    have = {f.GetReference() for f in board.GetFootprints()}
    for ref, (lib, name) in sorted(want.items()):
        if ref in have:
            continue
        fp = loaded[ref]
        if fp is None:
            raise SystemExit("cannot load %s:%s" % (lib, name))
        fp.SetReference(ref)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        val = {c[0]: c[2] for c in sch.COMPONENTS}.get(ref, name.split("_")[0])
        fp.SetValue(val)
        fp.SetPosition(pcbnew.VECTOR2I(ex + pcbnew.FromMM(10), ey + pcbnew.FromMM(10)))
        board.Add(fp)
        pins = {pin: net for (r, pin), net in sch.NET.items() if r == ref}
        for pad in fp.Pads():
            net = pins.get(pad.GetNumber())
            if net is None and pad.GetNumber() == "4" and "2" in pins:
                net = pins["2"]                  # SOT-343 second emitter
            if net is None:
                if ref in BOARD_ONLY:
                    continue
                raise SystemExit("%s pad %s has no net" % (ref, pad.GetNumber()))
            pad.SetNet(_net(board, net))
        if ref in BOARD_ONLY:
            fp.Reference().SetVisible(False)
            fp.Value().SetVisible(False)
        if ref == "J1":
            x, y, rot = J1_PLACE
            ox, oy = ex / 1e6 + 0.05, ey / 1e6 + 0.05
            fp.SetOrientationDegrees(rot)
            fp.SetPosition(pcbnew.VECTOR2I(int(round((ox + x) * 1e6)), int(round((oy + y) * 1e6))))
            fp.SetLocked(True)
        added.append(ref)
    # J1's position is owned by J1_PLACE (locked edge connector)
    for f in board.GetFootprints():
        if f.GetReference() == "J1":
            x, y, rot = J1_PLACE
            ox, oy = ex / 1e6 + 0.05, ey / 1e6 + 0.05
            f.SetOrientationDegrees(rot)
            f.SetPosition(pcbnew.VECTOR2I(int(round((ox + x) * 1e6)), int(round((oy + y) * 1e6))))
            f.SetLocked(True)
    return added, removed


def board_id(board, x0, y0):
    """Board name and revision on the bottom silkscreen (B.Cu is part-free)."""
    for d in list(board.GetDrawings()):
        if d.GetClass() == "PCB_TEXT" and d.GetText().startswith(BOARD_ID.split()[0]):
            board.Remove(d)
    t = pcbnew.PCB_TEXT(board)
    t.SetText(BOARD_ID)
    t.SetLayer(pcbnew.B_SilkS)
    t.SetMirrored(True)
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.2), pcbnew.FromMM(1.2)))
    t.SetTextThickness(pcbnew.FromMM(0.2))
    # right of J1's plated pins (x < 9), clear of exposed copper on the back
    t.SetPosition(pcbnew.VECTOR2I(int(round((x0 + 30.0) * 1e6)), int(round((y0 + H / 2) * 1e6))))
    board.Add(t)


def _bb(item, grow=0.0):
    b = item.GetBoundingBox()
    return (b.GetLeft() / 1e6 - grow, b.GetTop() / 1e6 - grow,
            b.GetRight() / 1e6 + grow, b.GetBottom() / 1e6 + grow)


def _hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _place_refs(board, size, thick, tries, seed, only=None, taken0=()):
    """Put every silkscreen reference in a spot that clears all pads, all
    silkscreen outlines, the other references and the board edge, and that is
    closer to its own part than to any other.  Greedy placement depends on the
    order, so several orders are tried and the least ambiguous result kept."""
    eb = board.GetBoardEdgesBoundingBox()
    bx0, by0 = eb.GetLeft() / 1e6 + 0.6, eb.GetTop() / 1e6 + 0.6
    bx1, by1 = eb.GetRight() / 1e6 - 0.6, eb.GetBottom() / 1e6 - 0.6
    fixed_obs = []
    for f in board.GetFootprints():
        for p in f.Pads():
            fixed_obs.append(_bb(p, 0.15))
        for g in f.GraphicalItems():
            if g.GetLayer() == pcbnew.F_SilkS and g.GetClass() != "PCB_TEXT":
                fixed_obs.append(_bb(g, 0.1))
    parts = [f for f in board.GetFootprints() if f.GetReference() not in BOARD_ONLY
             and (only is None or f.GetReference() in only)]
    yards, bodies = {}, {}
    for f in board.GetFootprints():
        c = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
        yards[f.GetReference()] = (c.GetLeft() / 1e6, c.GetTop() / 1e6,
                                   c.GetRight() / 1e6, c.GetBottom() / 1e6)
        # what a reader associates a label with: the part's pads
        pb = [_bb(p) for p in f.Pads()] or [yards[f.GetReference()]]
        bodies[f.GetReference()] = (min(b[0] for b in pb), min(b[1] for b in pb),
                                    max(b[2] for b in pb), max(b[3] for b in pb))

    def gap(box, yard):
        dx = max(yard[0] - box[2], box[0] - yard[2], 0.0)
        dy = max(yard[1] - box[3], box[1] - yard[3], 0.0)
        return math.hypot(dx, dy)

    def ambiguity(ref, box):
        own = gap(box, bodies[ref])
        other = min(gap(box, y) for k, y in bodies.items()
                    if k != ref and k not in BOARD_ONLY)
        return max(0.0, own - other + 0.25) + 0.3 * own

    # candidate boxes per part, computed once (text geometry from KiCad itself)
    cands = {}
    for f in parts:
        r = f.Reference()
        r.SetTextHeight(pcbnew.FromMM(size))
        r.SetTextWidth(pcbnew.FromMM(size))
        r.SetTextThickness(pcbnew.FromMM(thick))
        x0, y0, x1, y1 = yards[f.GetReference()]
        cx, cyy = (x0 + x1) / 2, (y0 + y1) / 2
        pts = [(cx, cyy, 0), (cx, cyy, 90)]
        for d in (0.6, 0.9, 1.3, 1.8, 2.4, 3.0, 3.6, 4.2):
            for sx in (0.0, -0.75, 0.75, -1.5, 1.5, -2.25, 2.25):
                pts += [(cx + sx, y0 - d, 0), (cx + sx, y1 + d, 0)]
            for sy in (0.0, -0.75, 0.75, -1.5, 1.5, -2.25, 2.25):
                pts += [(x0 - d - 0.6, cyy + sy, 0), (x1 + d + 0.6, cyy + sy, 0),
                        (x0 - d, cyy + sy, 90), (x1 + d, cyy + sy, 90)]
        lst = []
        for (x, y, ang) in pts:
            r.SetTextAngleDegrees(ang)
            r.SetPosition(pcbnew.VECTOR2I(int(round(x * 1e6)), int(round(y * 1e6))))
            box = _bb(r, 0.05)
            if box[0] < bx0 or box[1] < by0 or box[2] > bx1 or box[3] > by1:
                continue
            hits = sum(1 for o in fixed_obs if _hit(box, o))
            lst.append((10 * hits + ambiguity(f.GetReference(), box), x, y, ang, box))
        lst.sort(key=lambda t: t[0])
        cands[f.GetReference()] = lst

    rnd = random.Random(seed)
    refs = [f.GetReference() for f in parts]
    # crowded parts (fewest good spots) first, then random orders
    base = sorted(refs, key=lambda k: sum(1 for c in cands[k] if c[0] < 0.6))
    best = None
    for t in range(tries):
        order = base if t == 0 else rnd.sample(refs, len(refs))
        taken, pick, score = list(taken0), {}, 0.0
        for ref in order:
            choice = None
            for c in cands[ref]:
                if not any(_hit(c[4], o) for o in taken):
                    choice = c
                    break
            if choice is None:
                score += 100
                continue
            pick[ref] = choice
            taken.append(choice[4])
            score += choice[0]
        if best is None or score < best[0]:
            best = (score, pick)
    failed, boxes = [], []
    for f in parts:
        ref = f.GetReference()
        r = f.Reference()
        c = best[1].get(ref)
        if c is None:
            failed.append(ref)
            continue
        if c[0] >= 0.6:
            failed.append(ref)
        r.SetTextAngleDegrees(c[3])
        r.SetPosition(pcbnew.VECTOR2I(int(round(c[1] * 1e6)), int(round(c[2] * 1e6))))
        boxes.append(c[4])
    return failed, boxes


def place_refs(board, size=1.0, thick=0.15, tries=60, seed=1):
    """1.0 mm references everywhere they fit; 0.8 mm for the few that do not
    (crowded corners), placed around the 1.0 mm ones."""
    failed, boxes = _place_refs(board, size, thick, tries, seed)
    if not failed:
        return []
    keep = [b for b in boxes]
    # drop the failed ones' boxes and retry them smaller
    fp = {f.GetReference(): f for f in board.GetFootprints()}
    fail_boxes = [_bb(fp[r].Reference(), 0.05) for r in failed]
    keep = [b for b in keep if b not in fail_boxes]
    still, _b = _place_refs(board, 0.8, 0.15, tries, seed, only=set(failed), taken0=keep)
    return still


def report(pl, label):
    print("\n== %s ==" % label)
    print("wire cost %.1f   overlap/edge violation %.3f   ratsnest crossings %d"
          % (pl.wire_cost(), pl.total_violation(), pl.crossing_count()))
    pl.cross_w, keep = 1.0, pl.cross_w
    pl.edges = {n: pl.mst(n) for n in pl.nets}
    bad = sorted({"%s x %s" % (n, m) for n in pl.nets for m in pl.nets
                  if n < m and {n, m} & NO_CROSS and not {n, m} & EDGE_ROUTED
                  and any(_cross(e, f) for e in pl.edges[n] for f in pl.edges[m])})
    pl.cross_w = keep
    print("crossings on no-cross nets: %s" % (", ".join(bad) or "none"))
    print("widest signal nets (half-perimeter, mm):")
    for net, hp, n in pl.spans()[:10]:
        tag = "  high-Z" if net in HIGH_Z else ""
        print("   %-5s pads=%-2d  %5.1f%s" % (net, n, hp, tag))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--iters", type=int, default=250000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=BOARD, help="write here instead of opamp.kicad_pcb")
    ap.add_argument("--polish", action="store_true",
                    help="keep the current placement; apply POLISH_HAND and SNUG only")
    ap.add_argument("--force", action="store_true",
                    help="write the result even if it is not legal (for inspection)")
    ap.add_argument("--free", action="store_true",
                    help="ignore the hand floorplan and anneal from scratch")
    ap.add_argument("--cross", type=float, default=4.0,
                    help="cost per ratsnest crossing (doubled for high-Z nets)")
    a = ap.parse_args()

    # SaveBoard rewrites opamp.kicad_pro from the loaded board's settings, and
    # a board loaded via a temp copy loses the net-class patterns: keep the
    # project file as it was and put it back after saving
    pro_path = os.path.join(ROOT, "opamp.kicad_pro")
    pro_text = open(pro_path).read()
    src, stripped = strip_stale_footprints(BOARD)
    unrouted = 0
    if not a.dry_run:
        src, unrouted = strip_routing(src)
        if unrouted:
            print("removed %d tracks / vias (placement changes; re-route after)" % unrouted)
    if (stripped or unrouted) and not a.dry_run:
        tmp = os.path.join(ROOT, ".place_tmp_%d.kicad_pcb" % os.getpid())
        open(tmp, "w").write(src)
        # the project file must sit beside it, or pcbnew loads default rules
        # and SaveBoard later writes those defaults over opamp.kicad_pro
        import shutil
        shutil.copy(os.path.join(ROOT, "opamp.kicad_pro"), tmp[:-10] + ".kicad_pro")
        board = pcbnew.LoadBoard(tmp)
        os.remove(tmp)
        os.remove(tmp[:-10] + ".kicad_pro")
        if stripped:
            print("replacing stale footprints: %s" % stripped)
    else:
        board = pcbnew.LoadBoard(BOARD)
    if not a.dry_run:
        added, removed = sync_parts(board)
        print("parts added: %s   removed/replaced: %s" % (added or "none", removed or "none"))
        changed = stamp_nets(board)
        print("pad nets updated: %s" % (changed or "none"))
    pl = Placer(board)
    print("locked (kept in place): %s" % sorted(pl.locked))
    report(pl, "before (old outline)")
    if a.dry_run:
        return

    resize_outline_and_pours(board, pl.x0, pl.y0)
    for r in pl.locked - EDGE_PARTS:
        x0, y0, x1, y1 = pl.cbox(r)
        if x0 < EDGE or y0 < EDGE or x1 > W - EDGE or y1 > H - EDGE:
            raise SystemExit("locked part %s would sit outside the new outline" % r)
    if a.polish:
        pl.movable = [r for r in pl.movable if r not in FIXED]
        for r, (x, y, rot) in POLISH_HAND.items():
            pl.pos[r] = (pl.snap(x), pl.snap(y))
            pl.rot[r] = rot
        viol = 0.0
    elif a.free:
        for r in pl.movable:
            x, y = pl.pos[r]
            pl.pos[r] = (pl.snap(min(max(x, 3), W - 3)), pl.snap(min(max(y, 3), H - 3)))
        wire, viol = pl.anneal(a.iters, a.seed)
    else:
        missing = set(pl.movable) - set(PLAN)
        if missing:
            raise SystemExit("no floorplan entry for %s" % sorted(missing))
        for r in pl.movable:
            x, y, rot = PLAN[r]
            pl.pos[r] = (pl.snap(x), pl.snap(y))
            pl.rot[r] = rot
        report(pl, "floorplan seed")
        pl.movable = [r for r in pl.movable if r not in FIXED]
        # refine: the floorplan fixes the structure, the anneal only tidies it
        pl.cross_w = a.cross
        pl.wire_cost()
        wire, viol = pl.anneal(a.iters, a.seed, T0=3.0, step0=4.0, swaps=False, lam0=80.0)
        if viol > 1e-9:
            pl.legalize_local(seed=a.seed)
            viol = pl.legal_violation()
    for ref, links, *rad in SNUG:
        d = pl.snug(ref, links, *rad)
        print("snug %s: %s" % (ref, "no legal spot" if d is None else "%.1f mm to its anchors" % d))
        if os.environ.get("SNUG_DEBUG"):
            pl.cross_w, keep_w = 1.0, pl.cross_w
            pl.edges = {n: pl.mst(n) for n in pl.nets}
            print("   no-cross after: %s" % sorted({"%s x %s" % (n, m) for n in pl.nets for m in pl.nets
                  if n < m and {n, m} & NO_CROSS and not {n, m} & EDGE_ROUTED
                  and any(_cross(e, f) for e in pl.edges[n] for f in pl.edges[m])}))
            pl.cross_w = keep_w
    viol = pl.legal_violation()
    report(pl, "after (50 x 40 mm)")
    if viol > 1e-9:
        global GAP
        keep, GAP = GAP, GAP_MIN
        print("still in violation: %s" % ", ".join(
            "%s %.2f" % (r, pl.part_violation(r)) for r in sorted(pl.fp)
            if pl.part_violation(r) > 1e-9))
        GAP = keep
    if viol > 1e-9 and not a.force:
        raise SystemExit("placement not legal (violation %.3f) - try another --seed" % viol)
    pl.movable = sorted(set(pl.fp) - pl.locked)
    pl.apply()
    failed = place_refs(board)
    print("silkscreen references with no clear spot: %s" % (failed or "none"))
    board_id(board, pl.x0, pl.y0)
    # pours are left unfilled: with no vias yet every fill is "isolated
    # copper"; KiCad refills them (B) once the board is routed
    ok = pcbnew.SaveBoard(a.out, board)
    open(pro_path, "w").write(pro_text)
    if not ok:
        raise SystemExit("save failed")
    print("\nwrote %s" % a.out)


if __name__ == "__main__":
    main()
    # pcbnew's SWIG destructors can crash at interpreter teardown; the board
    # is already saved, so leave without running them
    import sys
    sys.stdout.flush()
    os._exit(0)
