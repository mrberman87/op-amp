#!/usr/bin/env python3
"""Render opamp.kicad_pcb placement to a PNG using real pad geometry.

KiCad's own plot goes to an A4 page and is hard to read at board scale, so this
draws the board extents directly: outline, copper pours, courtyards tinted by
functional cluster, and every pad.  For eyeballing placement only.
"""
import math
import os

import pcbnew
from PIL import Image, ImageDraw, ImageFont

import gen_sch_rf as sch

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = "/tmp/opencode/board_placement.png"
SCALE = 14.0          # px per mm
MARGIN_PX = 18

BLOCK_OF = {}
try:
    import gen_pcb as G
    for n, items in G.BLOCKS.items():
        for r in items:
            BLOCK_OF[r] = n
except Exception:
    pass

BLOCK_FILL = {"IO": (200, 160, 255), "DIV": (160, 220, 255), "S1": (255, 210, 150),
              "S2": (170, 255, 180), "OUT": (255, 150, 150)}
NET_FILL = {"+15V": (200, 40, 40), "-15V": (40, 40, 200), "GND": (90, 90, 90)}


def local_courtyard(fp):
    pts = []
    for g in fp.GraphicalItems():
        if g.GetLayer() != pcbnew.F_CrtYd:
            continue
        for n in ("GetStart", "GetEnd", "GetCenter"):
            f = getattr(g, n, None)
            if f:
                try:
                    v = f()
                    pts.append((v.x / 1e6, v.y / 1e6))
                except Exception:
                    pass
    if not pts:
        for p in fp.Pads():
            pts.append((p.pos.x / 1e6, p.pos.y / 1e6))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def main(path=os.path.join(ROOT, "opamp.kicad_pcb")):
    board = pcbnew.LoadBoard(path)
    W = board.GetCopperLayerCount()
    bw = board.GetBoardEdgesBoundingBox()
    x0, y0 = bw.GetX() / 1e6, bw.GetY() / 1e6
    x1, y1 = bw.GetRight() / 1e6, bw.GetBottom() / 1e6
    # fall back to the pad extent if the outline is missing
    if x1 <= x0:
        allp = [p.GetPosition() for f in board.GetFootprints() for p in f.Pads()]
        x0, y0 = min(p.x for p in allp) / 1e6 - 2, min(p.y for p in allp) / 1e6 - 2
        x1, y1 = max(p.x for p in allp) / 1e6 + 2, max(p.y for p in allp) / 1e6 + 2

    def px(x, y):
        return (MARGIN_PX + (x - x0) * SCALE, MARGIN_PX + (y - y0) * SCALE)

    img = Image.new("RGB", (int((x1 - x0) * SCALE) + 2 * MARGIN_PX,
                            int((y1 - y0) * SCALE) + 2 * MARGIN_PX), (250, 249, 246))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 11)
    except OSError:
        font = ImageFont.load_default()

    # copper pours — KiCad 10 zones are multi-layer, so ask which layer each one
    # actually covers instead of trusting GetLayerName()
    seen = set()
    for z in board.Zones():
        lay = next((board.GetLayerName(i) for i in range(40)
                    if (board.GetLayerName(i) or "").endswith(".Cu") and z.IsOnLayer(i)), "?")
        zb = z.GetBoundingBox()
        col = NET_FILL.get(z.GetNetname(), (170, 200, 170))
        a = px(zb.GetX() / 1e6, zb.GetY() / 1e6)
        b = px(zb.GetRight() / 1e6, zb.GetBottom() / 1e6)
        tag = "%s on %s" % (z.GetNetname(), lay)
        if tag in seen:
            continue
        seen.add(tag)
        d.rectangle([a, b], outline=col, width=2)
        d.text((a[0] + 5, a[1] + 3 + 14 * len(seen)), tag, fill=col, font=font)

    # board outline
    d.rectangle([px(x0, y0), px(x1, y1)], outline=(20, 20, 20), width=3)

    for fp in board.GetFootprints():
        cx, cy = fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6
        rot = fp.GetOrientationDegrees()
        blk = BLOCK_OF.get(fp.GetReference(), "")
        fill = BLOCK_FILL.get(blk, (220, 220, 220))
        lx0, ly0, lx1, ly1 = local_courtyard(fp)
        corners = []
        for lx, ly in [(lx0, ly0), (lx1, ly0), (lx1, ly1), (lx0, ly1)]:
            a = math.radians(rot)
            corners.append(px(cx + lx * math.cos(a) - ly * math.sin(a),
                              cy + lx * math.sin(a) + ly * math.cos(a)))
        d.polygon(corners, fill=fill + (70,), outline=(120, 120, 120))
        for pad in fp.Pads():
            p = pad.GetPosition()
            sz = pad.GetSize()
            pw, ph = sz.x / 1e6 / 2, sz.y / 1e6 / 2
            ang = math.radians(rot)
            pts = []
            for lx, ly in [(-pw, -ph), (pw, -ph), (pw, ph), (-pw, ph)]:
                qx = p.x / 1e6 + lx * math.cos(ang) - ly * math.sin(ang)
                qy = p.y / 1e6 + lx * math.sin(ang) + ly * math.cos(ang)
                pts.append(px(qx, qy))
            net = pad.GetNetname()
            d.polygon(pts, fill=NET_FILL.get(net, (30, 140, 60)))
        c = px(cx, cy)
        d.text((c[0] - 8, c[1] - 5), fp.GetReference(), fill=(10, 10, 10), font=font)

    d.text((6, img.height - 16),
           "opamp.kicad_pcb  %.1f x %.1f mm   %d copper layers   %d parts   "
           "green = signal pad, red = +15V, blue = -15V, grey = GND"
           % (x1 - x0, y1 - y0, W, len(board.GetFootprints())),
           fill=(40, 40, 40), font=font)
    img.save(OUT)
    print("wrote", OUT, "%dx%d" % img.size)


if __name__ == "__main__":
    main()
