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
GRID = 0.25                # placement grid, mm

POWER = {"+15V", "-15V", "GND"}
RAIL_W = 15.0              # per mm a rail pad sits outside its own In2.Cu pour
THERM_W = 2.0              # thermal-gradient weight across matched pairs

# In2.Cu: +15 V on the top half, -15 V on the bottom half, split along y = 20
# with a 1.5 mm gap.  J1 (locked) has its +15 V pin at y = 24.8, in the bottom
# half, so the +15 V pour drops a finger down the left edge to the bottom of
# the board, under J1 pin 5 and C1/C11 (x < FINGER_X); the -15 V pour stays
# 0.5 mm clear of it.
SPLIT_TOP, SPLIT_BOT = H / 2 - 0.75, H / 2 + 0.75
FINGER_X = 5.95

# Footprints that exist only on the board (not in the schematic).
BOARD_ONLY = {
    "H1": ("MountingHole", "MountingHole_3.2mm_M3"),
    "H2": ("MountingHole", "MountingHole_3.2mm_M3"),
    "FID1": ("Fiducial", "Fiducial_1mm_Mask2mm"),
    "FID2": ("Fiducial", "Fiducial_1mm_Mask2mm"),
    "FID3": ("Fiducial", "Fiducial_1mm_Mask2mm"),
}
HOLES = {"H1", "H2"}

BOARD_ID = "DISCRETE OP AMP  REV E  4L 1.6mm"

HIGH_Z = {"c2", "d1", "d2", "d3", "a1", "n1", "n2", "vcp", "e3", "e4", "x8",
          "x9", "xo", "db", "b9", "n8", "n9", "e1", "Tc", "vet", "veb", "vref", "T"}

# Ratsnest-crossing classes.  On a single signal layer every crossing is a
# B.Cu hop or a jumper: never acceptable on the stage-2 signal / AC-ground
# nets, cheap on the bypassed DC bias lines.  OUT is excluded: it is routed
# round the board edge through the reserved strip, not along its ratsnest.
NO_CROSS = {"e1", "d1", "d2", "c2"}
DC_BIAS = {"vcd", "vcn", "vcp"}
EDGE_ROUTED = {"OUT"}


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
    if net == "d2":
        return 6.0           # stage-2 output into Q14's base: keep it short
    if net in HIGH_Z:
        return 4.0
    if net in ("INP", "INN", "OUT"):
        return 3.0
    return 1.0


# Hand floorplan used as the starting point (board-local mm, centre, rotation).
# Stage 1 is a ring (tail, Q1, Q3, Q5, Q4, mirror, Q6, Q7, Q2) drawn on its side:
# Q2's chain along the top, Q1's along the bottom, the mirror at the far end.
# Both inputs then reach their bases from J1 without crossing the ring.
# Stage 2 sits above it, the output stage takes the right edge (NPN half on the
# +15 V side, PNP half on the -15 V side), and R17/R7 sit bottom-right so the
# long OUT run back to J1 pin 1 follows the bottom and left edges, past the
# tail and bias parts instead of the high-impedance nodes.
PLAN = {
    # stage 1, top chain (Q2 side)
    "Q2": (13.0, 16.0, 0), "Q7": (17.5, 14.5, 180), "Q6": (22.0, 14.5, 180),
    "R8": (26.5, 14.5, 180),
    # stage 1, bottom chain (Q1 side)
    "Q1": (13.0, 19.0, 0), "Q3": (17.5, 24.5, 180), "Q5": (22.0, 24.5, 180),
    "Q4": (26.5, 24.5, 180), "R5": (30.5, 24.5, 180),
    # stage 1, inside the ring: cascode-bias helper
    "Q8": (18.5, 19.5, 0), "R6": (23.0, 19.5, 0),
    # tail and bias reference below the ring
    "R18": (12.5, 29.0, 90), "Q10": (13.0, 33.0, 90), "R3": (13.0, 37.0, 90),
    "R1": (18.0, 29.0, 90), "Q9": (18.0, 33.0, 90), "R2": (18.0, 37.0, 90),
    # vcn divider beside the tail
    "R4": (23.0, 30.0, 90), "R9": (23.0, 34.5, 90), "C4": (26.0, 32.0, 90),
    # rail decoupling right under the J1 rail pins
    # +15 V entry caps stacked under J1, + pads inside the In2.Cu finger
    "C11": (4.75, 31.5, 0), "C1": (3.75, 34.5, 0),
    "C2": (8.0, 31.25, 90), "C12": (9.5, 34.75, 0),
    # stage 2 along the top
    "Q12": (13.0, 4.0, 90), "Q11": (13.0, 8.5, 90), "C7": (17.0, 6.0, 90),
    "Q13": (20.5, 8.5, 90), "R19": (20.5, 3.5, 0), "R20": (23.5, 11.0, 90),
    "C6": (27.5, 6.5, 90), "C10": (9.5, 5.0, 90),
    # vcd divider between stage 2 and the output
    "R10": (32.5, 15.5, 90), "R11": (32.5, 23.5, 90), "C5": (40.5, 3.0, 0),
    # output stage: buffer column, Vbe multiplier, push-pull column
    "Q15": (36.5, 4.0, 90), "Q14": (36.5, 8.5, 90), "R12": (36.5, 13.0, 90),
    "R13": (36.5, 17.5, 90), "Q19": (40.0, 15.0, 0), "C3": (40.0, 10.5, 90),
    "R14": (36.5, 24.0, 90),
    "Q17": (45.0, 4.0, 90), "Q16": (45.0, 8.5, 90), "R15": (45.0, 12.5, 90),
    "R16": (45.0, 16.5, 90), "Q18": (45.0, 23.0, 270),
    "C8": (48.0, 8.0, 90), "C9": (48.0, 26.0, 90),
    "R17": (40.75, 31.0, 270), "R7": (40.75, 35.25, 270),
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
FIXED = {"R17", "R7", "H1", "H2", "C1", "C11"}

# Courtyard-free strips (x0, y0, x1, y1): the OUT return along the bottom
# edge, up the left edge, into J1 pin 1.
KEEPOUT = [(0.0, 37.2, W, H), (0.0, 0.0, 2.2, H)]

# matched pairs: (a, b, max centre distance mm, weight); same rotation too.
# Q1/Q2 may nearly touch (PAIR_GAP) so their emitters can share one T pad.
# Q5/Q7 are cascodes: their Vbe mismatch barely moves the mirror current, so
# they are only kept loosely together.  Q4/Q6 set the mirror ratio (offset).
PAIRS = [("Q1", "Q2", 2.75, 12.0), ("Q4", "Q6", 4.5, 15.0),
         ("Q5", "Q7", 6.0, 2.0), ("Q9", "Q10", 5.0, 3.0)]
PAIR_GAP = 0.3
THERMAL_PAIRS = [("Q1", "Q2"), ("Q4", "Q6")]
# (part, pad, anchor part, anchor pad, weight): decoupling and bypass placement
ATTRACT = [("C1", "1", "J1", "5", 1.0), ("C2", "1", "J1", "6", 1.0),
           ("C11", "1", "J1", "5", 1.0), ("C12", "1", "J1", "6", 1.0),
           ("C8", "1", "Q17", "3", 2.0), ("C9", "1", "Q18", "3", 2.0),
           ("C10", "1", "Q12", "1", 2.0), ("C5", "1", "Q17", "1", 1.5),
           ("C4", "1", "Q3", "1", 2.0), ("C6", "1", "Q13", "2", 3.0),
           ("C3", "1", "Q19", "3", 1.0)]


def _rect_dist(x, y, r):
    dx = max(r[0] - x, 0.0, x - r[2])
    dy = max(r[1] - y, 0.0, y - r[3])
    return math.hypot(dx, dy)


def rail_miss(net, x, y, m=0.4):
    """How far (mm) a rail pad at (x, y) is from its own In2.Cu pour."""
    if net == "+15V":
        rects = [(0, 0, W, SPLIT_TOP - m), (0, 0, FINGER_X - m, H)]
    else:
        rects = [(FINGER_X + 0.5 + m, SPLIT_BOT + m, W, H)]
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
        self.pair_set = {(a, b) for a, b, _d, _w in PAIRS} | \
            {(b, a) for a, b, _d, _w in PAIRS if (a, b) == ("Q1", "Q2")}
        self.pair_set = {p for p in self.pair_set if set(p) == {"Q1", "Q2"}}
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
        if ref not in HOLES:
            v = max(0.0, EDGE - x0) + max(0.0, EDGE - y0) + \
                max(0.0, x1 - (W - EDGE)) + max(0.0, y1 - (H - EDGE))
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
    if len(edges) != 4:
        raise SystemExit("expected a 4-segment rectangular outline, found %d" % len(edges))
    corners = [(0, 0, W, 0), (W, 0, W, H), (W, H, 0, H), (0, H, 0, 0)]
    for d, (a, b, c, e) in zip(edges, corners):
        d.SetStart(P(a, b))
        d.SetEnd(P(c, e))

    m = 0.3
    gx = FINGER_X + 0.5                       # -15 V keeps 0.5 mm off the finger
    shapes = {
        ("GND", "In1.Cu"): [(m, m), (W - m, m), (W - m, H - m), (m, H - m)],
        ("GND", "B.Cu"): [(m, m), (W - m, m), (W - m, H - m), (m, H - m)],
        ("+15V", "In2.Cu"): [(m, m), (W - m, m), (W - m, SPLIT_TOP),
                             (FINGER_X, SPLIT_TOP), (FINGER_X, H - m), (m, H - m)],
        ("-15V", "In2.Cu"): [(gx, SPLIT_BOT), (W - m, SPLIT_BOT), (W - m, H - m),
                             (gx, H - m)],
    }
    rects = shapes
    done = set()
    for z in board.Zones():
        key = (z.GetNetname(), board.GetLayerName(z.GetFirstLayer()))
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


def sync_parts(board):
    """Make the board's footprint set match the schematic table plus the
    board-only parts (holes, fiducials): add what is missing with its nets,
    replace a footprint whose library part changed, drop what is gone.
    New parts start at the board origin; the placer moves them."""
    want = {c[0]: tuple(c[7].split(":")) for c in sch.COMPONENTS}
    want.update(BOARD_ONLY)
    have = {f.GetReference(): f for f in board.GetFootprints()}
    added, removed = [], []
    for ref, f in have.items():
        name = f.GetFPID().GetLibItemName().wx_str()
        if ref not in want or name != want[ref][1]:
            if f.IsLocked():
                raise SystemExit("locked part %s differs from the schematic" % ref)
            board.Remove(f)
            removed.append(ref)
    # stamp the library link (gen_pcb.py left the nickname empty), so KiCad's
    # "update footprints from library" and its library checks can find them
    for f in board.GetFootprints():
        lib, name = want[f.GetReference()]
        f.SetFPID(pcbnew.LIB_ID(lib, name))
    have = {f.GetReference() for f in board.GetFootprints()}
    eb = board.GetBoardEdgesBoundingBox()
    for ref, (lib, name) in sorted(want.items()):
        if ref in have:
            continue
        fp = pcbnew.FootprintLoad(os.path.join("/usr/share/kicad/footprints", lib + ".pretty"), name)
        if fp is None:
            raise SystemExit("cannot load %s:%s" % (lib, name))
        fp.SetReference(ref)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        val = {c[0]: c[2] for c in sch.COMPONENTS}.get(ref, name.split("_")[0])
        fp.SetValue(val)
        fp.SetPosition(pcbnew.VECTOR2I(eb.GetX() + pcbnew.FromMM(10), eb.GetY() + pcbnew.FromMM(10)))
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
            ni = board.FindNet(net)
            if ni is None:
                raise SystemExit("net %s is not on the board" % net)
            pad.SetNet(ni)
        if ref in BOARD_ONLY:
            fp.Reference().SetVisible(False)
            fp.Value().SetVisible(False)
        added.append(ref)
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
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(1.5), pcbnew.FromMM(1.5)))
    t.SetTextThickness(pcbnew.FromMM(0.25))
    t.SetPosition(pcbnew.VECTOR2I(int(round((x0 + W / 2) * 1e6)), int(round((y0 + H / 2) * 1e6))))
    board.Add(t)


def _bb(item, grow=0.0):
    b = item.GetBoundingBox()
    return (b.GetLeft() / 1e6 - grow, b.GetTop() / 1e6 - grow,
            b.GetRight() / 1e6 + grow, b.GetBottom() / 1e6 + grow)


def _hit(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def place_refs(board, size=1.0, thick=0.15, tries=60, seed=1):
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
    parts = [f for f in board.GetFootprints() if f.GetReference() not in BOARD_ONLY]
    yards = {}
    for f in board.GetFootprints():
        c = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
        yards[f.GetReference()] = (c.GetLeft() / 1e6, c.GetTop() / 1e6,
                                   c.GetRight() / 1e6, c.GetBottom() / 1e6)

    def gap(box, yard):
        dx = max(yard[0] - box[2], box[0] - yard[2], 0.0)
        dy = max(yard[1] - box[3], box[1] - yard[3], 0.0)
        return math.hypot(dx, dy)

    def ambiguity(ref, box):
        own = gap(box, yards[ref])
        other = min(gap(box, y) for k, y in yards.items()
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
        for d in (0.6, 0.9, 1.3, 1.8, 2.4, 3.0):
            for sx in (0.0, -0.75, 0.75, -1.5, 1.5):
                pts += [(cx + sx, y0 - d, 0), (cx + sx, y1 + d, 0)]
            for sy in (0.0, -0.75, 0.75, -1.5, 1.5):
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
        taken, pick, score = [], {}, 0.0
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
    failed = []
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
    return failed


def report(pl, label):
    print("\n== %s ==" % label)
    print("wire cost %.1f   overlap/edge violation %.3f   ratsnest crossings %d"
          % (pl.wire_cost(), pl.total_violation(), pl.crossing_count()))
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
    ap.add_argument("--free", action="store_true",
                    help="ignore the hand floorplan and anneal from scratch")
    ap.add_argument("--cross", type=float, default=4.0,
                    help="cost per ratsnest crossing (doubled for high-Z nets)")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(BOARD)
    if not a.dry_run:
        added, removed = sync_parts(board)
        print("parts added: %s   removed/replaced: %s" % (added or "none", removed or "none"))
    pl = Placer(board)
    print("locked (kept in place): %s" % sorted(pl.locked))
    report(pl, "before (old outline)")
    if a.dry_run:
        return

    resize_outline_and_pours(board, pl.x0, pl.y0)
    for r in pl.locked:
        x0, y0, x1, y1 = pl.cbox(r)
        if x0 < EDGE or y0 < EDGE or x1 > W - EDGE or y1 > H - EDGE:
            raise SystemExit("locked part %s would sit outside the new outline" % r)
    if a.free:
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
    report(pl, "after (50 x 40 mm)")
    if viol > 1e-9:
        raise SystemExit("placement not legal (violation %.3f) - try another --seed" % viol)
    pl.movable = sorted(set(pl.fp) - pl.locked)
    pl.apply()
    failed = place_refs(board)
    print("silkscreen references with no clear spot: %s" % (failed or "none"))
    board_id(board, pl.x0, pl.y0)
    # pours are left unfilled: with no vias yet every fill is "isolated
    # copper"; KiCad refills them (B) once the board is routed
    if not pcbnew.SaveBoard(a.out, board):
        raise SystemExit("save failed")
    print("\nwrote %s" % a.out)


if __name__ == "__main__":
    main()
