#!/usr/bin/env python3
"""Render the routed board (tracks, vias, pads, refs) to PNG for review."""
import sys, os, pcbnew
from PIL import Image, ImageDraw, ImageFont
board = pcbnew.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else "opamp.kicad_pcb")
out = sys.argv[2] if len(sys.argv) > 2 else "routed.png"
S = float(sys.argv[3]) if len(sys.argv) > 3 else 24.0
bb = board.GetBoardEdgesBoundingBox()
x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
W, H = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
M = 10
img = Image.new("RGB", (int(W*S)+2*M, int(H*S)+2*M), (20, 20, 20))
d = ImageDraw.Draw(img, "RGBA")
P = lambda x, y: (M+(pcbnew.ToMM(x)-x0)*S, M+(pcbnew.ToMM(y)-y0)*S)
try: font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", int(S*0.55))
except Exception: font = ImageFont.load_default()
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA): continue
    col = (230, 60, 60, 200) if t.GetLayer() == pcbnew.F_Cu else (70, 120, 255, 170)
    d.line([P(t.GetStart().x, t.GetStart().y), P(t.GetEnd().x, t.GetEnd().y)], fill=col,
           width=max(1, int(pcbnew.ToMM(t.GetWidth())*S)))
for fp in board.GetFootprints():
    for p in fp.Pads():
        sh = p.GetEffectivePolygon(pcbnew.F_Cu) if p.IsOnLayer(pcbnew.F_Cu) else None
        if sh is None or sh.OutlineCount() == 0: continue
        o = sh.Outline(0)
        pts = [P(o.CPoint(i).x, o.CPoint(i).y) for i in range(o.PointCount())]
        net = p.GetNetname()
        c = (200, 170, 60, 230) if net not in ("GND", "+15V", "-15V") else \
            {"GND": (140, 140, 140, 230), "+15V": (255, 120, 0, 230), "-15V": (0, 200, 255, 230)}[net]
        if len(pts) > 2: d.polygon(pts, fill=c)
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        c = P(t.GetPosition().x, t.GetPosition().y); r = pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu))/2*S
        d.ellipse([c[0]-r, c[1]-r, c[0]+r, c[1]+r], fill=(230, 230, 230, 230))
for dr in board.GetDrawings():
    if dr.GetLayer() == pcbnew.Edge_Cuts:
        if dr.GetShape() == pcbnew.SHAPE_T_SEGMENT:
            d.line([P(dr.GetStart().x, dr.GetStart().y), P(dr.GetEnd().x, dr.GetEnd().y)], fill=(255, 255, 0), width=2)
        elif dr.GetShape() == pcbnew.SHAPE_T_ARC:
            c=P(dr.GetCenter().x,dr.GetCenter().y); r=pcbnew.ToMM(dr.GetRadius())*S
            d.ellipse([c[0]-r,c[1]-r,c[0]+r,c[1]+r], outline=(255,255,0), width=1)
# ratsnest (MST per signal net) when the board has no tracks yet
if not any(not isinstance(t, pcbnew.PCB_VIA) for t in board.GetTracks()):
    nets = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            n = p.GetNetname()
            if n and n not in ("GND", "+15V", "-15V"):
                nets.setdefault(n, []).append((p.GetPosition().x, p.GetPosition().y))
    for n, pts in nets.items():
        inside, rest = [pts[0]], pts[1:]
        while rest:
            a, b = min(((a, q) for a in inside for q in rest),
                       key=lambda t: abs(t[0][0]-t[1][0]) + abs(t[0][1]-t[1][1]))
            d.line([P(*a), P(*b)], fill=(120, 255, 120, 255), width=1)
            inside.append(b); rest.remove(b)
    for fp in board.GetFootprints():
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        d.rectangle([P(bb.GetLeft(), bb.GetTop()), P(bb.GetRight(), bb.GetBottom())], outline=(90, 90, 200))
for fp in board.GetFootprints():
    c = P(fp.GetPosition().x, fp.GetPosition().y)
    d.text(c, fp.GetReference(), fill=(255, 255, 255), font=font, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
img.save(out)
print(out, img.size)
os._exit(0)
