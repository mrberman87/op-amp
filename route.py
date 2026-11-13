#!/usr/bin/env python3
"""Route opamp.kicad_pcb: a grid A* router written for this board's policy.

Policy (TODO 2.x, set_stackup.py):
  * signals on F.Cu, at 0/45/90 degrees, over the unbroken In1.Cu GND plane;
    B.Cu (a GND pour) only as a costed hop where a crossing is unavoidable,
    and never for the stage-2 signal / AC-ground nets (place.NO_CROSS);
  * every GND / +15 V / -15 V pad fans out with a short stub to a via; a rail
    via must land inside its own In2.Cu pour (place.rail_miss);
  * OUT and OUTA run on B.Cu straight along the In2.Cu GND corridor
    (corridor()): OUT to J1 pin 4, OUTA to the feedback resistor R24;
  * GND stitching vias around the perimeter tie In1.Cu to the B.Cu pour;
  * afterwards every net is ripped up and rerouted alone against the finished
    board, kept if shorter (improve()), and every chain is redrawn with as
    few 0/45/90-degree segments as clear the other nets (tidy()).

Clearances come from the real copper of other nets (distance transform on a
0.1 mm grid) with the net-class rules from set_rules.py plus a margin, and the
result is checked by KiCad's own DRC (kicad-cli), which is the final word.

Usage:  python3 route.py [--out file.kicad_pcb]
"""
import argparse
import heapq
import math
import os

import numpy as np
import pcbnew
from scipy import ndimage

import gen_sch_rf as sch
import place

ROOT = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(ROOT, "opamp.kicad_pcb")

G = 0.1                       # routing grid, mm
MARGIN = 0.06                 # extra clearance over the rules (grid error)
EDGE_CLR = 0.5                # copper to board edge (rule is 0.3)
F, B = 0, 1
LAYER_ID = {F: pcbnew.F_Cu, B: pcbnew.B_Cu}

POWER = {"+15V", "-15V", "GND"}
W_SIG, W_PWR = 0.25, 0.5      # track widths (Power class default 0.5)
CLR_SIG, CLR_PWR = 0.2, 0.25  # net-class clearances (set_rules.py)
VIA_SIG = (0.6, 0.3)          # (diameter, drill)
VIA_PWR = (0.8, 0.4)
VIA_COST = 25.0               # in grid steps (2.5 mm of track)
B_COST = 4.0                  # B.Cu step multiplier (it is the GND pour)

# routing order: the stage-2 loop and the high-Z nodes get first pick of the
# copper, then the rest
# vcp (the undecoupled 22k cascode-base line) and the mirror emitters e3/e4
# go early too: routed late they detoured round the output stage.
CRITICAL = ["INN", "INP", "e1", "d1", "c2", "c2b", "d2", "d2b", "T", "vcp", "e3", "e4",
            "d3", "d3b", "b9", "db", "a1", "n1", "n2", "c1", "x8", "x9", "xo", "n8", "n9", "OUTA"]
LATE = ["vcn", "vcd", "vref", "veb", "vet", "Tc"]


def mm2(v):
    return int(round(v * 1e6))


class Router(object):
    def __init__(self, board):
        self.b = board
        bb = board.GetBoardEdgesBoundingBox()
        self.x0 = bb.GetX() / 1e6 + 0.05
        self.y0 = bb.GetY() / 1e6 + 0.05
        self.nx = int(round(place.W / G)) + 1
        self.ny = int(round(place.H / G)) + 1
        names = sorted(set(sch.NET.values()))
        self.net_id = {n: i for i, n in enumerate(names)}
        self.net_name = names
        self.owner = np.full((2, self.ny, self.nx), -1, np.int32)   # copper
        self.padmask = np.zeros((self.ny, self.nx), bool)           # F.Cu pads
        self.tree = {}            # net -> set of (layer, iy, ix) on its copper
        self.pads = {}            # net -> list of (ref, num, x, y, cells)
        self.added = []           # (net, kind, data) for writing
        ys, xs = np.mgrid[0:self.ny, 0:self.nx]
        self.cx = xs * G          # cell-centre coordinates, board-local mm
        self.cy = ys * G
        d_edge = np.minimum.reduce([self.cx, self.cy, place.W - self.cx, place.H - self.cy])
        R = place.CORNER_R                      # rounded corners
        for (ccx, ccy) in ((R, R), (place.W - R, R), (place.W - R, place.H - R), (R, place.H - R)):
            inq = ((self.cx - ccx) * (ccx - place.W / 2) > 0) & ((self.cy - ccy) * (ccy - place.H / 2) > 0)
            d_c = R - np.hypot(self.cx - ccx, self.cy - ccy)
            d_edge = np.where(inq, np.minimum(d_edge, d_c), d_edge)
        self.d_edge = d_edge
        self.tht = set()          # (net, ref, num) of plated-through pads
        self.holes = []           # (x, y, radius) of every drilled hole
        self.fan_len = []         # (stub length, pad, net) per fanout
        self.seeded = {}          # nid -> (done points, pads already connected)
        self._load_copper()

    # ---- geometry -------------------------------------------------------
    def loc(self, v):
        return v.x / 1e6 - self.x0, v.y / 1e6 - self.y0

    def cell(self, x, y):
        return int(round(y / G)), int(round(x / G))

    def _win(self, x0, y0, x1, y1):
        i0, i1 = max(int(y0 / G) - 1, 0), min(int(y1 / G) + 2, self.ny)
        j0, j1 = max(int(x0 / G) - 1, 0), min(int(x1 / G) + 2, self.nx)
        return slice(i0, i1), slice(j0, j1)

    def paint_rect(self, layer, net, x0, y0, x1, y1, pad=False):
        sl = self._win(x0, y0, x1, y1)
        m = (self.cx[sl] >= x0) & (self.cx[sl] <= x1) & (self.cy[sl] >= y0) & (self.cy[sl] <= y1)
        self._paint(layer, net, sl, m)
        if pad:
            self.padmask[sl] |= m
        return sl, m

    def paint_disk(self, layers, net, x, y, r):
        sl = self._win(x - r, y - r, x + r, y + r)
        m = (self.cx[sl] - x) ** 2 + (self.cy[sl] - y) ** 2 <= r * r
        for l in layers:
            self._paint(l, net, sl, m)

    def paint_seg(self, layer, net, a, b, w):
        (ax, ay), (bx, by) = a, b
        r = w / 2.0
        sl = self._win(min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r)
        px, py = self.cx[sl] - ax, self.cy[sl] - ay
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.clip((px * dx + py * dy) / L2, 0, 1) if L2 > 0 else 0 * px
        d2 = (px - t * dx) ** 2 + (py - t * dy) ** 2
        self._paint(layer, net, sl, d2 <= r * r)

    def _paint(self, layer, net, sl, m):
        o = self.owner[layer][sl]
        clash = m & (o != -1) & (o != net)
        o[m & (o == -1)] = net
        o[clash] = -2

    def _load_copper(self):
        self.thermal = {}         # ref -> [(pad number, bbox ints, NETINFO)]
        for f in self.b.GetFootprints():
            ref = f.GetReference()
            if ref in self.HOT:
                self.thermal[ref] = [(p.GetNumber(),
                                      (p.GetBoundingBox().GetLeft(), p.GetBoundingBox().GetTop(),
                                       p.GetBoundingBox().GetRight(), p.GetBoundingBox().GetBottom()),
                                      p.GetNet()) for p in f.Pads()]
            if ref in place.HOLES:
                x, y = self.loc(f.GetPosition())
                self.paint_disk((F, B), -2, x, y, place.HOLE_KEEPOUT_D / 2)   # copper keepout
                self.holes.append((x, y, 1.6))
                continue
            for p in f.Pads():
                x0, y0 = self.loc(pcbnew.VECTOR2I(p.GetBoundingBox().GetLeft(), p.GetBoundingBox().GetTop()))
                x1, y1 = self.loc(pcbnew.VECTOR2I(p.GetBoundingBox().GetRight(), p.GetBoundingBox().GetBottom()))
                net = p.GetNetname()
                if not net:                                    # fiducial: keep its mask opening clear
                    cx, cy = self.loc(p.GetPosition())
                    self.paint_disk((F,), -2, cx, cy, 1.5)   # mask 2 mm + clear zone
                    continue
                nid = self.net_id[net]
                tht = p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                # exact pad outline: pcbnew's own hit test on every cell of
                # the pad's bounding box (round J1 pads are not squares)
                sl = self._win(x0, y0, x1, y1)
                m = np.zeros((sl[0].stop - sl[0].start, sl[1].stop - sl[1].start), bool)
                for a_ in range(m.shape[0]):
                    for b_ in range(m.shape[1]):
                        px = (sl[1].start + b_) * G + self.x0
                        py = (sl[0].start + a_) * G + self.y0
                        m[a_, b_] = p.HitTest(pcbnew.VECTOR2I(mm2(px), mm2(py)))
                self._paint(F, nid, sl, m)
                self.padmask[sl] |= m
                cx, cy = self.loc(p.GetPosition())
                if tht:
                    self._paint(B, nid, sl, m)
                    self.tht.add((net, ref, p.GetNumber()))
                    self.holes.append((cx, cy, p.GetDrillSize().x / 2e6))
                idx = list(zip(*np.nonzero(m)))
                cells = {(F, int(i) + sl[0].start, int(j) + sl[1].start) for i, j in idx}
                if tht:
                    cells |= {(B, int(i) + sl[0].start, int(j) + sl[1].start) for i, j in idx}
                self.pads.setdefault(net, []).append((ref, p.GetNumber(), cx, cy, cells))

    # ---- cost shaping ---------------------------------------------------
    HOT = {"R19": 156}          # mW; keep foreign tracks out from under it

    def hot_cost(self, net):
        """Per-layer cost maps: F.Cu cells under a hot part cost 6x for nets
        that do not belong to it (156 mW in a 1206 heats what runs beneath)."""
        if not hasattr(self, "_hot_box"):
            self._hot_box = {}
            for f in self.b.GetFootprints():
                if f.GetReference() in self.HOT:
                    c = f.GetCourtyard(pcbnew.F_CrtYd).BBox()
                    x0, y0 = self.loc(pcbnew.VECTOR2I(c.GetLeft(), c.GetTop()))
                    x1, y1 = self.loc(pcbnew.VECTOR2I(c.GetRight(), c.GetBottom()))
                    nets = {p.GetNetname() for p in f.Pads()}
                    self._hot_box[f.GetReference()] = ((x0, y0, x1, y1), nets)
        cf = np.ones((self.ny, self.nx))
        for (x0, y0, x1, y1), nets in self._hot_box.values():
            if net in nets:
                continue
            m = (self.cx >= x0) & (self.cx <= x1) & (self.cy >= y0) & (self.cy <= y1)
            cf[m] = 6.0
        return (cf, np.ones((self.ny, self.nx)))

    # ---- free space -----------------------------------------------------
    def free_map(self, nid, w, clr, cost_map=None):
        """Cells a track of width w on net nid may run through, per layer."""
        out = []
        for l in (F, B):
            other = (self.owner[l] != -1) & (self.owner[l] != nid)
            d = ndimage.distance_transform_edt(~other) * G
            ok = d >= clr + w / 2.0 + G / 2.0 + MARGIN
            ok &= self.d_edge >= EDGE_CLR + w / 2.0
            out.append(ok)
        return out

    def via_map(self, nid, via, clr):
        """Cells where a via of net nid fits (clear on both outer layers, not in a pad)."""
        r = via[0] / 2.0
        ok = np.ones((self.ny, self.nx), bool)
        for l in (F, B):
            other = (self.owner[l] != -1) & (self.owner[l] != nid)
            d = ndimage.distance_transform_edt(~other) * G
            ok &= d >= clr + r + G / 2.0 + MARGIN
        dpad = ndimage.distance_transform_edt(~self.padmask) * G
        ok &= dpad >= r + 0.15
        # hole-to-hole rule (0.5 mm edge to edge) against every drill so far
        for (hx, hy, hr) in self.holes:
            lim = hr + via[1] / 2.0 + 0.5 + MARGIN
            sl = self._win(hx - lim, hy - lim, hx + lim, hy + lim)
            ok[sl] &= (self.cx[sl] - hx) ** 2 + (self.cy[sl] - hy) ** 2 > lim * lim
        ok &= self.d_edge >= EDGE_CLR + r
        return ok

    # ---- search ---------------------------------------------------------
    def astar(self, nid, sources, goal, h_target, w, clr, via, cost_map=None,
              allow_b=True, max_expand=600000, layer_cost=(1.0, B_COST)):
        free = self.free_map(nid, w, clr)
        self._free = free
        vok = self.via_map(nid, via, clr) if allow_b else None
        ny, nx = self.ny, self.nx
        dirs = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
        g = {}
        came = {}
        heap = []
        for s in sources:
            l, i, j = s
            g[s] = 0.0
            heapq.heappush(heap, (h_target(i, j), 0.0, s))
        expanded = 0
        while heap:
            f_, gc, s = heapq.heappop(heap)
            if gc > g.get(s, 1e18):
                continue
            l, i, j = s
            if goal(s):
                path = [s]
                while path[-1] in came:
                    path.append(came[path[-1]])
                return path[::-1]
            expanded += 1
            if expanded > max_expand:
                return None
            for di, dj, c in dirs:
                ii, jj = i + di, j + dj
                if not (0 <= ii < ny and 0 <= jj < nx):
                    continue
                if not free[l][ii, jj] and (l, ii, jj) not in self.tree.get(nid, ()):
                    continue
                if di and dj and not (free[l][i, jj] or free[l][ii, j]):
                    continue
                step = c * layer_cost[l]
                if cost_map is not None:
                    step *= cost_map[l][ii, jj]
                ng = gc + step
                t = (l, ii, jj)
                if ng < g.get(t, 1e18):
                    g[t] = ng
                    came[t] = s
                    heapq.heappush(heap, (ng + h_target(ii, jj), ng, t))
            if vok is not None and vok[i, j]:
                t = (1 - l, i, j)
                if free[1 - l][i, j]:
                    ng = gc + VIA_COST
                    if ng < g.get(t, 1e18):
                        g[t] = ng
                        came[t] = s
                        heapq.heappush(heap, (ng + h_target(i, j), ng, t))
        return None

    # ---- commit ---------------------------------------------------------
    def smooth(self, nid, path):
        """String-pull a cell path: replace staircase jogs with the longest
        straight 0/45/90-degree runs that stay in free space.  Layer changes
        (vias) are kept exactly where they were."""
        free = getattr(self, "_free", None)
        if free is None or len(path) < 3:
            return path
        tree = self.tree.get(nid, set())

        def ok(l, i, j):
            return free[l][i, j] or (l, i, j) in tree

        def line(a, b):
            (l, i0, j0), (_l, i1, j1) = a, b
            di, dj = i1 - i0, j1 - j0
            if not (di == 0 or dj == 0 or abs(di) == abs(dj)):
                return None
            n = max(abs(di), abs(dj))
            si, sj = (di > 0) - (di < 0), (dj > 0) - (dj < 0)
            cells = []
            for k in range(1, n + 1):
                i, j = i0 + si * k, j0 + sj * k
                if not ok(l, i, j):
                    return None
                if si and sj and not (ok(l, i - si, j) or ok(l, i, j - sj)):
                    return None
                cells.append((l, i, j))
            return cells
        out = [path[0]]
        k = 0
        while k < len(path) - 1:
            if path[k + 1][0] != path[k][0]:          # via: keep it
                out.append(path[k + 1])
                k += 1
                continue
            best = k + 1
            m = k + 2
            while m < len(path) and path[m][0] == path[k][0]:
                if line(path[k], path[m]) is not None:
                    best = m
                m += 1
            seg = line(path[k], path[best]) or [path[best]]
            out.extend(seg)
            k = best
        return out

    def commit(self, net, path, w, via, start_pt=None, end_pt=None):
        """Turn a cell path into segments + vias and paint it."""
        nid = self.net_id[net]
        path = self.smooth(nid, path)
        pts = []
        for (l, i, j) in path:
            pts.append((l, j * G, i * G))
        segs, vias = [], []
        if start_pt is not None:
            segs.append((pts[0][0], start_pt, (pts[0][1], pts[0][2])))
        run = [pts[0]]
        for p in pts[1:]:
            if p[0] != run[-1][0]:
                vias.append((run[-1][1], run[-1][2]))
                segs += self._compress(run)
                run = [p]
            else:
                run.append(p)
        segs += self._compress(run)
        if end_pt is not None:
            segs.append((pts[-1][0], (pts[-1][1], pts[-1][2]), end_pt))
        for (l, a, b) in segs:
            if abs(a[0] - b[0]) < 1e-9 and abs(a[1] - b[1]) < 1e-9:
                continue
            self.paint_seg(l, nid, a, b, w)
            self.added.append((net, "seg", (l, a, b, w)))
        for (x, y) in vias:
            self.paint_disk((F, B), nid, x, y, via[0] / 2.0)
            self.added.append((net, "via", (x, y, via)))
            self.holes.append((x, y, via[1] / 2.0))
        self.tree.setdefault(nid, set()).update(path)
        return segs, vias

    @staticmethod
    def _compress(run):
        if len(run) < 2:
            return []
        out = []
        a = run[0]
        prev = run[0]
        d0 = None
        for p in run[1:]:
            d = (round((p[1] - prev[1]) / G), round((p[2] - prev[2]) / G))
            if d0 is not None and d != d0:
                out.append((a[0], (a[1], a[2]), (prev[1], prev[2])))
                a = prev
            d0 = d
            prev = p
        out.append((a[0], (a[1], a[2]), (prev[1], prev[2])))
        return out

    # ---- nets -----------------------------------------------------------
    def route_signal(self, net, cost_map=None, allow_b=True, layer_cost=(1.0, B_COST)):
        nid = self.net_id[net]
        pads = list(self.pads[net])
        w, clr, via = W_SIG, CLR_SIG, VIA_SIG
        # connect pads in nearest-first order to the growing tree; a net with
        # fixed copper already down (corridor()) grows from that copper
        pre = self.seeded.get(nid)
        if pre:
            done = list(pre[0])
            pads = [p_ for p_ in pads if (p_[0], p_[1]) not in pre[1]]
        else:
            done = [pads.pop(0)]
            self.tree.setdefault(nid, set()).update(done[0][4])
        fails = 0
        while pads:
            # next pad: the one nearest the connected set
            k = min(range(len(pads)), key=lambda q: min(
                abs(pads[q][2] - d[2]) + abs(pads[q][3] - d[3]) for d in done))
            ref, num, tx, ty, cells = pads.pop(k)
            ti, tj = self.cell(tx, ty)

            def h(i, j, ti=ti, tj=tj):
                di, dj = abs(i - ti), abs(j - tj)
                return (max(di, dj) + 0.4142 * min(di, dj)) * 1.0

            goal = (lambda s, cells=cells: s in cells)
            sources = list(self.tree[nid])
            path = self.astar(nid, sources, goal, h, w, clr, via, cost_map, allow_b,
                              layer_cost=layer_cost)
            if path is None:
                fails += 1
                print("   ! %s: could not reach %s.%s" % (net, ref, num))
                continue
            self.commit(net, path, w, via, end_pt=(tx, ty))
            self.tree[nid].update(cells)
            done.append((ref, num, tx, ty, cells))
        return fails == 0

    def fanout(self, net, ref, num, x, y, cells):
        """Stub from a rail/GND pad to the nearest legal via spot."""
        nid = self.net_id[net]
        for w, via in ((W_PWR, VIA_PWR), (0.4, VIA_PWR), (0.3, VIA_PWR), (0.25, VIA_SIG)):
            vok = self.via_map(nid, via, CLR_PWR)
            if net != "GND":
                legal = np.vectorize(lambda xx, yy: place.rail_miss(net, xx, yy, m=via[0] / 2 + 0.35) == 0)
                # evaluate the region test on a coarse window only (cheap)
                region = np.zeros_like(vok)
                sl = self._win(0, 0, place.W, place.H)
                region[sl] = legal(self.cx[sl], self.cy[sl])
                vok = vok & region
            if not vok.any():
                continue
            self.tree[nid] = self.tree.get(nid, set()) | cells
            goal = (lambda s, vok=vok: s[0] == F and vok[s[1], s[2]])
            path = self.astar(nid, list(cells), goal, lambda i, j: 0.0, w, CLR_PWR, via,
                              allow_b=False, max_expand=200000)
            if path is None:
                continue
            segs, _v = self.commit(net, path, w, via, start_pt=(x, y))
            L = sum(math.hypot(bb[0] - aa[0], bb[1] - aa[1]) for (_l, aa, bb) in segs)
            self.fan_len.append((L, "%s.%s" % (ref, num), net))
            vx, vy = path[-1][2] * G, path[-1][1] * G
            self.paint_disk((F, B), nid, vx, vy, via[0] / 2.0)
            self.added.append((net, "via", (vx, vy, via)))
            self.holes.append((vx, vy, via[1] / 2.0))
            return True
        print("   ! fanout failed for %s.%s (%s)" % (ref, num, net))
        return False

    def stitch(self, pitch=3.0, inset=1.3):
        """GND vias around the perimeter, wherever one fits."""
        nid = self.net_id["GND"]
        vok = self.via_map(nid, VIA_SIG, CLR_PWR)
        n = 0
        W_, H_ = place.W, place.H
        pts = []
        t = inset
        while t <= W_ - inset:
            pts += [(t, inset), (t, H_ - inset)]
            t += pitch
        t = inset + pitch
        while t <= H_ - inset - pitch / 2:
            pts += [(inset, t), (W_ - inset, t)]
            t += pitch
        for (x, y) in pts:
            # nearest legal spot within 1 mm of the nominal point
            best = None
            for dx in np.arange(-1.0, 1.01, G):
                for dy in np.arange(-1.0, 1.01, G):
                    i, j = self.cell(x + dx, y + dy)
                    if 0 <= i < self.ny and 0 <= j < self.nx and vok[i, j]:
                        d = dx * dx + dy * dy
                        if best is None or d < best[0]:
                            best = (d, i, j)
            if best is None:
                continue
            _d, i, j = best
            vx, vy = j * G, i * G
            self.paint_disk((F, B), nid, vx, vy, VIA_SIG[0] / 2.0)
            self.added.append(("GND", "via", (vx, vy, VIA_SIG)))
            self.holes.append((vx, vy, VIA_SIG[1] / 2.0))
            vok = self.via_map(nid, VIA_SIG, CLR_PWR)
            n += 1
        return n

    def stitch_corridor(self):
        """GND vias along both edges of the In2.Cu GND corridor, every
        CORR_STITCH_PITCH mm where one fits (within 1 mm along the row)."""
        nid = self.net_id["GND"]
        n = 0
        for y in CORR_STITCH_Y:
            x = 3.0
            while x <= place.W - 3.0:
                vok = self.via_map(nid, VIA_SIG, CLR_PWR)
                i = int(round(y / G))
                best = None
                for dx in np.arange(-1.0, 1.01, G):
                    j = int(round((x + dx) / G))
                    if 0 <= j < self.nx and vok[i, j]:
                        if best is None or abs(dx) < abs(best[0]):
                            best = (dx, j)
                if best is not None:
                    vx, vy = best[1] * G, i * G
                    self.paint_disk((F, B), nid, vx, vy, VIA_SIG[0] / 2.0)
                    self.added.append(("GND", "via", (vx, vy, VIA_SIG)))
                    self.holes.append((vx, vy, VIA_SIG[1] / 2.0))
                    n += 1
                x += CORR_STITCH_PITCH
        return n

    # ---- write ----------------------------------------------------------
    def write(self):
        for t in list(self.b.GetTracks()):
            self.b.Remove(t)
        for net, kind, d in self.added:
            ni = self.b.FindNet(net)
            if kind == "seg":
                l, a, bb, w = d
                t = pcbnew.PCB_TRACK(self.b)
                t.SetStart(pcbnew.VECTOR2I(mm2(a[0] + self.x0), mm2(a[1] + self.y0)))
                t.SetEnd(pcbnew.VECTOR2I(mm2(bb[0] + self.x0), mm2(bb[1] + self.y0)))
                t.SetWidth(mm2(w))
                t.SetLayer(LAYER_ID[l])
                t.SetNet(ni)
                self.b.Add(t)
            else:
                x, y, via = d
                v = pcbnew.PCB_VIA(self.b)
                v.SetPosition(pcbnew.VECTOR2I(mm2(x + self.x0), mm2(y + self.y0)))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetWidth(mm2(via[0]))
                v.SetDrill(mm2(via[1]))
                v.SetNet(ni)
                self.b.Add(v)


def thermal_pad(board, pads, num, ref):
    """A small F.Cu copper area on the rail side of a hot resistor (TODO 2.10),
    on the pad's own net, kept off the other pad.  Its fanout via ties it to
    the In2.Cu pour.  `pads` was captured when the board was first loaded
    (pcbnew's SWIG wrappers degrade after several boards have been loaded)."""
    pd = {n: (bb, net) for n, bb, net in pads}
    (b, net) = pd[num]
    qb = [v[0] for k, v in pd.items() if k != num][0]
    x0, y0, x1, y1 = b
    g = pcbnew.FromMM(1.4)
    x0, y0, x1, y1 = x0 - g, y0 - g, x1 + g, y1 + g
    # stop short of the other pad (the d2 node): clip on its side
    lim = pcbnew.FromMM(0.4)
    if qb[0] >= b[2]:
        x1 = b[2] + lim
    elif qb[2] <= b[0]:
        x0 = b[0] - lim
    elif qb[1] >= b[3]:
        y1 = b[3] + lim
    else:
        y0 = b[1] - lim
    old = [x for x in board.Zones() if x.GetZoneName() == "thermal_%s" % ref]
    z = old[0] if old else pcbnew.ZONE(board)
    z.SetLayer(pcbnew.F_Cu)
    z.SetNet(net)
    z.SetZoneName("thermal_%s" % ref)
    z.SetAssignedPriority(1)
    z.SetLocalClearance(pcbnew.FromMM(0.25))
    z.SetMinThickness(pcbnew.FromMM(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    poly = z.Outline()
    poly.RemoveAllContours()
    poly.NewOutline()
    for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        poly.Append(int(x), int(y))
    if not old:
        board.Add(z)


# OUT and OUTA: B.Cu runs straight along the In2.Cu GND corridor
# (place.CORR_TOP .. CORR_BOT), board-local mm.  OUT: from a via beside its
# output-stage pads (R17 / R7 / TP7) to J1 pin 4 (plated through, no via).
# OUTA: from a via beside the output node (R15 / R16 / R17 / TP6) to a via
# beside R24 pad 1.  Under In1's solid GND the whole way, never beside an
# F.Cu high-impedance node.  Via spots are chosen per placement: the legal
# spot on the run's centre line nearest the pads it serves.
OUT_Y, OUTA_Y = 20.65, 21.6
# GND stitching rows along both edges of the corridor (In2 GND strip <-> In1
# <-> B.Cu), clear of OUT / OUTA and of the rail pours
CORR_STITCH_Y = (19.7, 22.35)
CORR_STITCH_PITCH = 3.5
OUT_J1 = (6.0, 21.1)
CORR_X_MIN = 9.0           # corridor vias stay right of J1's pin row
W_OUT, W_OUTA = 0.5, 0.3


def corridor(r):
    """Lay the OUT / OUTA corridor runs and seed both nets from them, so the
    remaining pads connect to the nearest corridor via on F.Cu."""
    def seg(n, a, b, w):
        r.paint_seg(B, r.net_id[n], a, b, w)
        r.added.append((n, "seg", (B, a, b, w)))

    def spot(n, y, near):
        # 0.4 mm instead of the 0.2 mm rule where it fits: the corridor vias
        # carry the output swing, keep them off neighbouring nets (T, at
        # R24).  Never left of J1's pin row (the run would cross pin 4).
        i = int(round(y / G))
        cx = sum(px for px, _py in near) / len(near)
        for clr in (0.4, 0.3, CLR_SIG):
            vm = r.via_map(r.net_id[n], VIA_SIG, clr)
            js = [j_ for j_ in np.nonzero(vm[i])[0] if j_ * G >= CORR_X_MIN]
            if not js:
                continue
            j = min(js, key=lambda j_: sum(math.hypot(j_ * G - px, y - py) for px, py in near))
            if abs(j * G - cx) <= 4.0 or clr == CLR_SIG:
                return (j * G, y)
        raise SystemExit("no via spot for %s on y = %.1f" % (n, y))

    def via(n, at):
        r.paint_disk((F, B), r.net_id[n], at[0], at[1], VIA_SIG[0] / 2)
        r.added.append((n, "via", (at[0], at[1], VIA_SIG)))
        r.holes.append((at[0], at[1], VIA_SIG[1] / 2))
        i, j = r.cell(*at)
        cells = {(F, i, j), (B, i, j)}
        r.tree.setdefault(r.net_id[n], set()).update(cells)
        return ("via", "", at[0], at[1], cells)

    def pads(n, keep):
        return [(x, y) for (ref, _num, x, y, _c) in r.pads[n] if keep(ref)]

    out_at = spot("OUT", OUT_Y, pads("OUT", lambda ref: ref != "J1"))
    o = via("OUT", out_at)
    seg("OUT", out_at, (OUT_J1[0] + 0.6, OUT_Y), W_OUT)
    seg("OUT", (OUT_J1[0] + 0.6, OUT_Y), OUT_J1, W_OUT)
    j1 = [p_ for p_ in r.pads["OUT"] if p_[0] == "J1"][0]
    r.tree[r.net_id["OUT"]].update(j1[4])
    r.seeded[r.net_id["OUT"]] = ([o, j1], {("J1", "4")})
    right = spot("OUTA", OUTA_Y, pads("OUTA", lambda ref: ref != "R24"))
    a1 = via("OUTA", right)
    left = spot("OUTA", OUTA_Y, pads("OUTA", lambda ref: ref == "R24"))
    a2 = via("OUTA", left)
    seg("OUTA", right, left, W_OUTA)
    r.seeded[r.net_id["OUTA"]] = ([a1, a2], set())
    r.corridor_vias = {"OUT": out_at, "OUTA": (right, left)}




def _cost(items):
    """Track length plus 2.5 mm per via: what the improvement pass minimises."""
    L = 0.0
    for _n, kind, d in items:
        if kind == "seg":
            _l, a, b, _w = d
            L += math.hypot(b[0] - a[0], b[1] - a[1])
        else:
            L += VIA_COST * G
    return L


def _painted(board, items):
    """A fresh Router with `items` (another run's tracks / vias) on it."""
    r = Router(board)
    for net, kind, d in items:
        nid = r.net_id[net]
        if kind == "seg":
            l, a, b, w = d
            r.paint_seg(l, nid, a, b, w)
        else:
            x, y, via = d
            r.paint_disk((F, B), nid, x, y, via[0] / 2.0)
            r.holes.append((x, y, via[1] / 2.0))
        r.added.append((net, kind, d))
    return r


def improve(board, items, nets, passes=2):
    """Rip-up and reroute, one net at a time against the finished board: the
    first routing pass is order-dependent (early nets take the straight
    paths, later ones detour round them).  A net's new route is kept only if
    it is shorter (vias counted as 2.5 mm)."""
    for p_ in range(passes):
        gained = 0.0
        for net in nets:
            mine = [it for it in items if it[0] == net]
            if not mine:
                continue
            rest = [it for it in items if it[0] != net]
            r = _painted(board, rest)
            if net in ("OUT", "OUTA"):
                continue
            n0 = len(r.added)
            if not r.route_signal(net, r.hot_cost(net), net not in place.NO_CROSS):
                continue
            new = r.added[n0:]
            if _cost(new) < _cost(mine) - 0.05:
                gained += _cost(mine) - _cost(new)
                items = rest + new
        print("improvement pass %d: %.1f mm shorter" % (p_ + 1, gained))
        if gained < 0.5:
            break
    return items


def _octi(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) < 1e-6 or abs(dy) < 1e-6:
        return True
    return abs(abs(dx) - abs(dy)) < 1e-6


def _elbows(a, b):
    """The two 0/45/90-degree two-segment routes from a to b (diagonal leg
    first, or straight leg first)."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    m = min(abs(dx), abs(dy))
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    c1 = (a[0] + sx * m, a[1] + sy * m)          # diagonal, then straight
    c2 = (b[0] - sx * m, b[1] - sy * m)          # straight, then diagonal
    return [c1, c2]


def tidy(board, items):
    """Redraw every routed chain with as few 0/45/90-degree segments as fit.

    The grid router leaves staircases of 0.1 mm steps and odd-angle stubs at
    off-grid pad centres.  Per net and layer, the segments are joined into
    chains between fixed points (pads, vias, junctions of three or more
    segments); each chain is string-pulled: from each point, jump to the
    farthest later point reachable by one straight 0/45/90 segment or a
    two-segment elbow whose copper clears every other net (the router's own
    clearance map).  The first and last legs may be at any angle (the pad
    entry), but only if short (< 0.6 mm)."""
    pad_pts = {}
    for f in board.GetFootprints():
        for pd in f.Pads():
            pad_pts.setdefault(pd.GetNetname(), []).append(pd.GetPosition())
    out = []
    nets = sorted({it[0] for it in items})
    for net in nets:
        mine = [it for it in items if it[0] == net]
        segs = [it for it in mine if it[1] == "seg"]
        if len(segs) < 2:
            out += mine
            continue
        rest = [it for it in items if it[0] != net]
        r = _painted(board, rest)
        nid = r.net_id[net]
        key = lambda p_: (round(p_[0], 3), round(p_[1], 3))
        fixed = set()
        for _n, kind, d in mine:
            if kind == "via":
                fixed.add(key((d[0], d[1])))
        for v in pad_pts.get(net, []):
            x, y = r.loc(v)
            fixed.add(key((x, y)))
        new = [it for it in mine if it[1] != "seg"]
        for layer in (F, B):
            ls = [d for _n, _k, d in segs if d[0] == layer]
            if not ls:
                continue
            # a branch may join mid-segment: split there so the joint becomes
            # a vertex (a fixed point) before any chain is simplified
            joints = [p_ for (_l, a, b, _w) in ls for p_ in (a, b)] + \
                [(d[0], d[1]) for _n, k_, d in mine if k_ == "via"]
            changed = True
            while changed:
                changed = False
                nxt = []
                for (l_, a, b, w_) in ls:
                    cut = None
                    for p_ in joints:
                        if key(p_) in (key(a), key(b)):
                            continue
                        ab = (b[0] - a[0], b[1] - a[1])
                        L2 = ab[0] ** 2 + ab[1] ** 2
                        if L2 < 1e-12:
                            continue
                        t = ((p_[0] - a[0]) * ab[0] + (p_[1] - a[1]) * ab[1]) / L2
                        if 0 < t < 1:
                            qx, qy = a[0] + t * ab[0], a[1] + t * ab[1]
                            if math.hypot(qx - p_[0], qy - p_[1]) < 2e-3:
                                cut = p_
                                break
                    if cut is None:
                        nxt.append((l_, a, b, w_))
                    else:
                        nxt += [(l_, a, cut, w_), (l_, cut, b, w_)]
                        changed = True
                ls = nxt
            widths = {}
            adj = {}
            for (_l, a, b, w) in ls:
                ka, kb = key(a), key(b)
                if ka == kb:
                    continue
                adj.setdefault(ka, []).append(kb)
                adj.setdefault(kb, []).append(ka)
                widths[frozenset((ka, kb))] = w
            stops = {k for k, v in adj.items() if len(v) != 2 or k in fixed}
            seen = set()
            chains = []
            for st in list(stops) + list(adj):
                for nb in adj.get(st, []):
                    e = frozenset((st, nb))
                    if e in seen:
                        continue
                    ch, prev, cur = [st], st, nb
                    seen.add(e)
                    while cur not in stops and (cur != st):
                        ch.append(cur)
                        nxt = [q for q in adj[cur] if q != prev]
                        if not nxt:
                            break
                        prev, cur = cur, nxt[0]
                        seen.add(frozenset((prev, cur)))
                    ch.append(cur)
                    w = max(widths.get(frozenset((ch[i], ch[i + 1])), W_SIG)
                            for i in range(len(ch) - 1))
                    chains.append((ch, w))
            for ch, w in chains:
                clr = CLR_PWR if net in POWER else (0.25 if net in place.HIGH_Z else CLR_SIG)
                free = r.free_map(nid, w, clr)[layer]

                def clear(a, b):
                    L = math.hypot(b[0] - a[0], b[1] - a[1])
                    n = max(2, int(L / 0.04) + 1)
                    for t in range(n + 1):
                        x = a[0] + (b[0] - a[0]) * t / n
                        y = a[1] + (b[1] - a[1]) * t / n
                        i, j = int(round(y / G)), int(round(x / G))
                        if not (0 <= i < r.ny and 0 <= j < r.nx):
                            return False
                        if not free[i, j]:
                            # own copper already there (the old chain, a pad)
                            if r.owner[layer][i, j] != nid:
                                return False
                    return True

                pts = ch
                res = [pts[0]]
                i = 0
                last = len(pts) - 1
                while i < last:
                    step = None
                    for k in range(last, i, -1):
                        a, b = pts[i], pts[k]
                        end_leg = (i == 0 or k == last) and \
                            math.hypot(b[0] - a[0], b[1] - a[1]) < 0.6
                        if (_octi(a, b) or end_leg) and clear(a, b):
                            step = [b]
                            break
                        for c in _elbows(a, b):
                            if clear(a, c) and clear(c, b):
                                step = [c, b]
                                break
                        if step:
                            break
                    if step is None:
                        step = [pts[i + 1]]
                        k = i + 1
                    res += step
                    i = k
                # drop collinear interior points
                clean = [res[0]]
                for q in res[1:]:
                    if len(clean) >= 2:
                        a, b = clean[-2], clean[-1]
                        if abs((b[0] - a[0]) * (q[1] - b[1]) - (b[1] - a[1]) * (q[0] - b[0])) < 1e-6 \
                                and ((b[0] - a[0]) * (q[0] - b[0]) + (b[1] - a[1]) * (q[1] - b[1])) >= 0:
                            clean[-1] = q
                            continue
                    if q != clean[-1]:
                        clean.append(q)
                for a, b in zip(clean, clean[1:]):
                    new.append((net, "seg", (layer, a, b, w)))
                    r.paint_seg(layer, nid, a, b, w)
        out += new
    return out


def route_all(order, board_path):
    board = pcbnew.LoadBoard(board_path)
    r = Router(board)
    corridor(r)
    failed = []
    nf = 0

    done_fan = set()

    def do_fanouts(only_far=False):
        n = 0
        for net in ("+15V", "-15V", "GND"):
            for (ref, num, x, y, cells) in r.pads[net]:
                if (net, ref, num) in r.tht or (ref, num) in done_fan:
                    continue      # plated-through: connects to the planes itself
                far = net != "GND" and place.rail_miss(net, x, y, m=0.0) > 0
                if only_far and not far:
                    continue
                n += 0 if r.fanout(net, ref, num, x, y, cells) else 1
                done_fan.add((ref, num))
        return n

    # rail pads sitting over the other rail's pour need the longest stubs:
    # give them first pick of the board, before any signal
    nf = do_fanouts(only_far=True)

    # critical nets and OUT first, then every rail/GND fanout (so each pad
    # gets a short stub to its own pour before the board fills up), then the
    # remaining signals
    early = [n for n in order if n in CRITICAL or n == "OUT" or order.index(n) < 3]
    for net in order:
        if net not in early:
            continue
        ok = r.route_signal(net, r.hot_cost(net), net not in place.NO_CROSS)
        if not ok:
            failed.append(net)
    nf += do_fanouts()
    for net in order:
        if net in early:
            continue
        ok = r.route_signal(net, r.hot_cost(net), net not in place.NO_CROSS)
        if not ok:
            failed.append(net)
    return board, r, failed, nf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=BOARD, help="board to route")
    ap.add_argument("--out", default=BOARD)
    ap.add_argument("--tries", type=int, default=8)
    ap.add_argument("--post", help="(internal) thermal copper + pour fill on this board")
    a = ap.parse_args()
    if a.post:
        board = pcbnew.LoadBoard(a.post)
        for f in board.GetFootprints():
            if f.GetReference() == "R19":
                pads = [(p.GetNumber(), (p.GetBoundingBox().GetLeft(), p.GetBoundingBox().GetTop(),
                         p.GetBoundingBox().GetRight(), p.GetBoundingBox().GetBottom()), p.GetNet())
                        for p in f.Pads()]
        thermal_pad(board, pads, "1", "R19")
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pro_path = os.path.join(ROOT, "opamp.kicad_pro")
        pro_text = open(pro_path).read()
        ok = pcbnew.SaveBoard(a.post, board)
        open(pro_path, "w").write(pro_text)
        if not ok:
            raise SystemExit("save failed")
        print("thermal copper on R19 pad 1, pours filled")
        return
    # start from the board with any old routing stripped (text level: see
    # place.strip_routing), the project file beside it for the real rules
    pro_path = os.path.join(ROOT, "opamp.kicad_pro")
    pro_text = open(pro_path).read()
    src, nold = place.strip_routing(open(a.inp).read())
    clean = os.path.join(ROOT, ".route_tmp_%d.kicad_pcb" % os.getpid())
    open(clean, "w").write(src)
    import shutil
    shutil.copy(pro_path, clean[:-10] + ".kicad_pro")
    if nold:
        print("stripped %d old tracks / vias" % nold)
    a.inp = clean
    probe = Router(pcbnew.LoadBoard(a.inp))
    sig_nets = [n for n in probe.pads if n not in POWER and len(probe.pads[n]) > 1]
    order = [n for n in CRITICAL if n in sig_nets] + ["OUT"] + \
        [n for n in LATE if n in sig_nets]
    order += [n for n in sig_nets if n not in order]
    for attempt in range(a.tries):
        board, r, failed, nf = route_all(order, a.inp)
        print("attempt %d: incomplete %s, fanout failures %d" % (attempt + 1, failed or "none", nf))
        if not failed and nf == 0:
            break
        # rip up and retry: the nets that failed go first next time
        order = failed + [n for n in order if n not in failed]
    print("longest fanout stubs: %s" % ", ".join(
        "%s %.1f mm" % (p_, L) for L, p_, _n in sorted(r.fan_len, reverse=True)[:5]))
    items = improve(board, list(r.added),
                    [n for n in order if n not in ("OUT", "OUTA")])
    n0 = sum(1 for it in items if it[1] == "seg")
    items = tidy(board, items)
    print("tidy: %d segments -> %d" % (n0, sum(1 for it in items if it[1] == "seg")))
    r = _painted(board, items)
    ns = r.stitch()
    nc = r.stitch_corridor()
    print("stitching vias: %d perimeter, %d along the corridor" % (ns, nc))
    r.write()
    ok = pcbnew.SaveBoard(a.out, board)
    os.remove(clean)
    os.remove(clean[:-10] + ".kicad_pro")
    open(pro_path, "w").write(pro_text)
    if not ok:
        raise SystemExit("save failed")
    # thermal copper + pour fill in a fresh process: after several boards have
    # been loaded here, pcbnew's SWIG wrappers return untyped objects
    import subprocess
    import sys
    subprocess.run([sys.executable, os.path.abspath(__file__), "--post", a.out], check=True)
    nseg = sum(1 for x in r.added if x[1] == "seg")
    nvia = sum(1 for x in r.added if x[1] == "via")
    print("wrote %s: %d segments, %d vias; incomplete nets: %s"
          % (a.out, nseg, nvia, failed or "none"))


if __name__ == "__main__":
    main()
    # pcbnew's SWIG destructors can crash at interpreter teardown; the board
    # is already saved, so leave without running them
    import sys
    sys.stdout.flush()
    os._exit(0)
