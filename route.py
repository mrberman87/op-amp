#!/usr/bin/env python3
"""Route opamp.kicad_pcb: a grid A* router written for this board's policy.

Policy (TODO 2.x, set_stackup.py):
  * signals on F.Cu, at 0/45/90 degrees, over the unbroken In1.Cu GND plane;
    B.Cu (a GND pour) only as a costed hop where a crossing is unavoidable,
    and never for the stage-2 signal / AC-ground nets (place.NO_CROSS);
  * every GND / +15 V / -15 V pad fans out with a short stub to a via; a rail
    via must land inside its own In2.Cu pour (place.rail_miss);
  * OUT runs back to J1 pin 1 through the part-free strip along the bottom
    and left edges, away from the high-impedance nodes;
  * GND stitching vias around the perimeter tie In1.Cu to the B.Cu pour.

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
# copper, then the OUT return (so the edge strip is still free), then the rest
CRITICAL = ["INN", "INP", "e1", "d1", "c2", "c2b", "d2", "d2b", "T", "d3", "d3b", "b9", "db", "a1", "n1", "n2",
            "c1", "e3", "e4", "x8", "x9", "xo", "n8", "n9", "OUTA"]
LATE = ["vcp", "vcn", "vcd", "vref", "veb", "vet", "Tc"]


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
        # connect pads in nearest-first order to the growing tree
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


def edge_cost(r):
    """OUT runs on B.Cu (shielded from the F.Cu high-Z nodes by the In1 GND
    plane) and hugs the board edge so it does not carve the B.Cu GND pour in
    two.  Per-layer cost maps: (F.Cu, B.Cu)."""
    near_edge = r.d_edge <= place.FRAME - 0.6     # inside the In2 GND frame
    out_cost = (np.full(r.d_edge.shape, 8.0), np.where(near_edge, 1.0, 20.0))
    return out_cost, None


def route_all(order, out_cost, board_path):
    board = pcbnew.LoadBoard(board_path)
    r = Router(board)
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
        if net == "OUT":
            ok = r.route_signal(net, out_cost, True, layer_cost=(1.0, 1.0))
        else:
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
        if not pcbnew.SaveBoard(a.post, board):
            raise SystemExit("save failed")
        print("thermal copper on R19 pad 1, pours filled")
        return
    probe = Router(pcbnew.LoadBoard(a.inp))
    out_cost, _ = edge_cost(probe)
    sig_nets = [n for n in probe.pads if n not in POWER and len(probe.pads[n]) > 1]
    order = [n for n in CRITICAL if n in sig_nets] + ["OUT"] + \
        [n for n in LATE if n in sig_nets]
    order += [n for n in sig_nets if n not in order]
    for attempt in range(a.tries):
        board, r, failed, nf = route_all(order, out_cost, a.inp)
        print("attempt %d: incomplete %s, fanout failures %d" % (attempt + 1, failed or "none", nf))
        if not failed and nf == 0:
            break
        # rip up and retry: the nets that failed go first next time
        order = failed + [n for n in order if n not in failed]
    print("longest fanout stubs: %s" % ", ".join(
        "%s %.1f mm" % (p_, L) for L, p_, _n in sorted(r.fan_len, reverse=True)[:5]))
    ns = r.stitch()
    print("stitching vias: %d" % ns)
    r.write()
    if not pcbnew.SaveBoard(a.out, board):
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
