#!/usr/bin/env python3
"""Re-arrange the placement in place, around the fixed/locked connector.

This does NOT rebuild the board.  The user moved the board and locked J1 in the
layout file, so we load the existing board, keep the outline, the pours, the
design rules and every locked footprint exactly as they are, and only move the
unlocked footprints.  Pad nets come along with the footprints, so connectivity
cannot break.

Scoring is the weighted half-perimeter of every net (the same weights used to
lay out the schematic clusters): high-impedance analog nodes count 4x, the
rails 0.2x because they are poured rather than walked.

Usage:
    python3 rearrange.py --dry-run      score the current placement only
    python3 rearrange.py                optimise, write, report
"""
import argparse
import math
import os
import random

import pcbnew

import gen_sch_rf as sch

ROOT = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(ROOT, "opamp.kicad_pcb")

# cluster-local part offsets, mm; rotation 0 => pin 1/2 on the left, pin 3 right
VP, HP = 4.40, 4.80
BLOCKS = {
    "DIV": {
        "R4": (0.0, 0.0, 90), "R9": (0.0, 3.4, 90), "C4": (3.6, 1.7, 90),
        "R10": (7.4, 0.0, 90), "R11": (7.4, 3.4, 90), "C5": (11.0, 1.7, 90),
    },
    "S1": {
        "R5": (0.0, -VP, 90), "R8": (HP, -VP, 90),
        "Q4": (0.0, 0.0, 270), "Q6": (HP, 0.0, 270),
        "Q5": (0.0, VP, 270), "Q7": (HP, VP, 270),
        "Q8": (2 * HP, VP, 270), "R6": (2 * HP + 3.8, 2.2 * VP, 90),
        "Q3": (0.0, 2 * VP, 90), "Q1": (0.0, 3 * VP, 90), "Q2": (HP, 3 * VP, 90),
        "R18": (HP / 2, 4.15 * VP, 90), "Q10": (HP / 2, 4.95 * VP, 90),
        "R3": (HP / 2, 5.8 * VP, 90),
        "R1": (-4.0, 4.95 * VP, 0), "Q9": (-8.2, 4.95 * VP, 0), "R2": (-8.2, 5.9 * VP, 0),
    },
    "S2": {
        "Q12": (0.0, 0.0, 90), "Q11": (0.0, VP, 90),
        "R19": (HP, -0.9 * VP, 90), "Q13": (HP, 1.1 * VP, 90),
        "C7": (HP / 2 + 0.3, -0.6 * VP, 90),
        "R20": (HP, 2.3 * VP, 90), "C6": (HP + 5.2, 2.4 * VP, 0),
    },
    "OUT": {
        "Q15": (0.0, 0.0, 90), "Q14": (0.0, VP, 90),
        "Q17": (HP, 0.6 * VP, 90), "Q16": (HP, 1.9 * VP, 90),
        "R12": (-4.2, 1.6 * VP, 90), "R13": (-4.2, 2.7 * VP, 90),
        "R14": (-8.0, 3.4 * VP, 90),
        "Q19": (0.6, 3.0 * VP, 0), "C3": (2.5, 2.2 * VP, 0),
        "R15": (HP, 3.0 * VP, 90), "R16": (HP, 4.0 * VP, 90),
        "Q18": (HP, 5.0 * VP, 270),
    },
    # rail decoupling + output isolation: neighbours of the connector pins
    "RAILS": {"C1": (0.0, 0.0, 0), "C2": (0.0, 2.3, 0),
              "R17": (3.2, 0.0, 90), "R7": (6.4, 0.0, 90)},
}
BLOCK_OF = {r: n for n, items in BLOCKS.items() for r in items}
ALL_REFS = set(BLOCK_OF)

COURTYARD = {"SOT23": (3.86, 3.40), "SOT343": (2.90, 2.20), "R": (2.96, 1.46),
             "R1206": (4.56, 2.26), "C": (2.96, 1.46), "CP": (9.60, 7.10),
             "HDR": (6.82, 16.24)}


def key_of(fpid):
    s = fpid.split(":")[-1]
    if s.startswith("SOT-343"):
        return "SOT343"
    if s.startswith("SOT-23"):
        return "SOT23"
    if s.startswith("R_1206"):
        return "R1206"
    if s.startswith("R_0603"):
        return "R"
    if s.startswith("C_0603"):
        return "C"
    if s.startswith("CP_Elec"):
        return "CP"
    if s.startswith("PinHeader"):
        return "HDR"
    raise SystemExit("unknown footprint %s" % s)


def net_weight(net):
    if net in ("+15V", "-15V", "GND"):
        return 0.2
    if net in {"c2", "d1", "d2", "d3", "a1", "n1", "n2", "vcp", "e3", "e4", "x8",
               "x9", "xo", "db", "b9", "n8", "n9", "e1", "Tc", "vet", "veb", "vref", "T"}:
        return 4.0
    if net in ("INP", "INN", "OUT"):
        return 3.0
    return 1.0


class Board:
    def __init__(self, path=BOARD):
        self.b = pcbnew.LoadBoard(path)
        bb = self.b.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = bb.GetX() / 1e6, bb.GetY() / 1e6
        self.W, self.H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
        self.fp = {f.GetReference(): f for f in self.b.GetFootprints()}
        self.pos = {r: (f.GetPosition().x / 1e6 - self.x0, f.GetPosition().y / 1e6 - self.y0)
                    for r, f in self.fp.items()}
        self.rot = {r: f.GetOrientationDegrees() for r, f in self.fp.items()}
        self.locked = {r for r, f in self.fp.items() if f.IsLocked()}
        self.nets = {}
        for (ref, pin), net in sch.NET.items():
            self.nets.setdefault(net, []).append(ref)

    def local(self, ref, rot):
        w, h = COURTYARD[key_of(self.fp[ref].GetFPIDAsString())]
        if rot % 180:
            w, h = h, w
        return (-w / 2, -h / 2, w / 2, h / 2)

    def box(self, ref):
        x, y = self.pos[ref]
        lx0, ly0, lx1, ly1 = self.local(ref, self.rot[ref])
        return (x + lx0, y + ly0, x + lx1, y + ly1)

    def cost(self):
        tot = 0.0
        for net, refs in self.nets.items():
            pts = [self.pos[r] for r in refs if r in self.pos]
            if len(pts) < 2:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            tot += net_weight(net) * (max(xs) - min(xs) + max(ys) - min(ys))
        return tot

    def overlaps(self, clearance=0.30):
        refs = list(self.pos)
        hits = []
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                a, b = self.box(refs[i]), self.box(refs[j])
                ox = min(a[2], b[2]) - max(a[0], b[0])
                oy = min(a[3], b[3]) - max(a[1], b[1])
                if ox > -clearance and oy > -clearance:
                    hits.append((refs[i], refs[j], round(ox, 2), round(oy, 2)))
        return hits

    def out_of_bounds(self, edge=1.5):
        bad = []
        for r in self.pos:
            x0, y0, x1, y1 = self.box(r)
            if x0 < edge or y0 < edge or x1 > self.W - edge or y1 > self.H - edge:
                bad.append(r)
        return bad

    def legalize(self, clearance=0.30, passes=500):
        for _ in range(passes):
            hits = self.overlaps(clearance)
            if not hits:
                return True
            for a, b, ox, oy in hits:
                if a in self.locked and b in self.locked:
                    continue
                if ox < oy:
                    d = (ox + clearance) / 2 + 0.02
                    sgn = 1 if self.pos[a][0] > self.pos[b][0] else -1
                    self._push(a, sgn * d, 0)
                    self._push(b, -sgn * d, 0)
                else:
                    d = (oy + clearance) / 2 + 0.02
                    sgn = 1 if self.pos[a][1] > self.pos[b][1] else -1
                    self._push(a, 0, sgn * d)
                    self._push(b, 0, -sgn * d)
        return not self.overlaps(clearance)

    def _push(self, ref, dx, dy):
        if ref in self.locked:      # locked parts are immovable; push the other one
            return
        x, y = self.pos[ref]
        self.pos[ref] = (x + dx, y + dy)

    def clamp(self):
        for r in self.pos:
            x0, y0, x1, y1 = self.local(r, self.rot[r]), None, None, None
            lx0, ly0, lx1, ly1 = self.local(r, self.rot[r])
            x, y = self.pos[r]
            x = min(max(x, 1.5 - lx0), self.W - 1.5 - lx1)
            y = min(max(y, 1.5 - ly0), self.H - 1.5 - ly1)
            self.pos[r] = (x, y)

    def apply(self, path=None):
        for r, f in self.fp.items():
            if r in self.locked:
                continue
            x, y = self.pos[r]
            f.SetPosition(pcbnew.VECTOR2I(int(round((x + self.x0) * 1e6)),
                                          int(round((y + self.y0) * 1e6))))
        return pcbnew.SaveBoard(path or BOARD, self.b)


def seed_from_blocks(board, anchors):
    """Place each cluster so its origin sits at a chosen anchor point."""
    for name, (ax, ay) in anchors.items():
        for ref, (lx, ly, rot) in BLOCKS[name].items():
            if ref in board.locked:
                continue
            board.pos[ref] = (ax + lx, ay + ly)
            board.rot[ref] = rot
    board.clamp()
    board.legalize()
    return board


def anneal(board, iters=4000, seed=1):
    """Move whole clusters (never individual parts, never locked ones) to reduce
    the weighted net cost, legalising after every accepted move."""
    rnd = random.Random(seed)
    names = list(BLOCKS)
    cur = board.cost()
    T0, T1 = 12.0, 0.25
    best = (cur, {k: v for k, v in board.pos.items()})
    for it in range(iters):
        T = T0 * (T1 / T0) ** (it / iters)
        n = rnd.choice(names)
        refs = [r for r in BLOCKS[n] if r not in board.locked]
        if not refs:
            continue
        dx, dy = rnd.gauss(0, 6), rnd.gauss(0, 6)
        before = {r: board.pos[r] for r in refs}
        for r in refs:
            x, y = board.pos[r]
            board.pos[r] = (x + dx, y + dy)
        board.clamp()
        if board.overlaps():
            for r, v in before.items():
                board.pos[r] = v
            continue
        new = board.cost()
        if new < cur or rnd.random() < math.exp((cur - new) / max(T, 1e-6)):
            cur = new
        else:
            for r, v in before.items():
                board.pos[r] = v
        if cur < best[0]:
            best = (cur, {k: v for k, v in board.pos.items()})
    board.pos = best[1]
    return board, best[0]


def report(board, label=""):
    print("\n%s placement: cost %.1f | overlaps %d | out of bounds %d"
          % (label, board.cost(), len(board.overlaps()), len(board.out_of_bounds())))
    for net in sorted(board.nets):
        if net in ("+15V", "-15V", "GND"):
            continue
        pts = [board.pos[r] for r in board.nets[net] if r in board.pos]
        if len(pts) < 2:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        sp = max(max(xs) - min(xs), max(ys) - min(ys))
        if sp > 12:
            print("   wide: %-5s %.1f mm  %s" % (net, sp,
                  [(r, round(p[0], 1), round(p[1], 1)) for r, p in zip(board.nets[net], pts)]))
    for h in board.overlaps()[:8]:
        print("   overlap: %s" % (h,))
    for r in board.out_of_bounds()[:8]:
        print("   near edge: %s at (%.1f,%.1f)" % (r, *board.pos[r]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--iters", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    board = Board()
    print("board %.1f x %.1f mm, locked: %s" % (board.W, board.H, sorted(board.locked)))
    report(board, "current")
    if a.dry_run:
        return

    anchors = {
        "RAILS": (12.0, 14.0),     # by the OUT / top connector pins
        "DIV":   (14.0, 38.0),     # below the rail pins, feeds vcn/vcd rightward
        "S1":    (26.0, 16.0),     # immediately right of INP/INN
        "S2":    (44.0, 12.0),
        "OUT":   (40.0, 34.0),
    }
    seed_from_blocks(board, anchors)
    report(board, "seeded")
    board, cost = anneal(board, iters=a.iters, seed=a.seed)
    board.legalize()
    report(board, "annealed")
    if board.overlaps():
        raise SystemExit("legalisation failed: %d overlaps remain" % len(board.overlaps()))
    print("\nsaving", BOARD)
    if not board.apply():
        raise SystemExit("save failed")


if __name__ == "__main__":
    main()
