#!/usr/bin/env python3
"""Generate opamp.kicad_pcb for the Rev E discrete op-amp.

Board policy (agreed):
  * 4 copper layers, 1.6 mm, **all components on the top side**
  * L1 F.Cu   : components + all signal routing
  * L2 In1.Cu : solid undivided GND plane  (return path under every top trace)
  * L3 In2.Cu : +15 V and -15 V pours      (no signals)
  * L4 B.Cu   : GND pour, component-free

Two-stage construction, because KiCad's Python bindings will place footprints
but will not register a netlist programmatically:

  1. pcbnew instantiates the footprints (real pad geometry from the installed
     libraries) at the floorplan positions and writes a scratch board.
  2. A text pass stamps the netlist, the board outline, the copper pours and
     the design rules into that file.

Nets come from gen_sch_rf.NET — the same table that draws the schematic — so
the board cannot silently drift from the drawing.

SOT-343 (BFP420) is a 4-lead part: pad 4 is the second emitter and is tied to
pad 2 (datasheet, TODO 2.2).

Run:  python3 gen_pcb.py        writes opamp.kicad_pcb and prints the report
"""
import math
import os
import re
import uuid as uuidlib

import pcbnew

import gen_sch_rf as sch

ROOT = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(ROOT, "opamp.kicad_pcb")
SCRATCH = "/tmp/opencode/pcb_stage1.kicad_pcb"
TEMPLATE = "/tmp/opencode/refboard/ref4l.kicad_pcb"
FP_DIR = "/usr/share/kicad/footprints"

STACKUP_TEXT = ("4 layer 1.6mm: F.Cu signal+components / In1.Cu GND / "
                "In2.Cu +15V,-15V / B.Cu GND. Order as the fab's JLC0004-100L "
                "controlled stackup.")

HIGH_Z = {"c2", "d1", "d2", "d3", "a1", "n1", "n2", "vcp", "e3", "e4",
          "x8", "x9", "xo", "db", "b9", "n8", "n9", "e1", "Tc", "vet", "veb",
          "vref", "T"}
POWER = {"+15V", "-15V", "GND"}

FOOT = {
    "R":      ("Resistor_SMD", "R_0603_1608Metric"),
    "R1206":  ("Resistor_SMD", "R_1206_3216Metric"),
    "C":      ("Capacitor_SMD", "C_0603_1608Metric"),
    "CP":     ("Capacitor_SMD", "CP_Elec_6.3x5.4"),
    "SOT23":  ("Package_TO_SOT_SMD", "SOT-23"),
    "SOT343": ("Package_TO_SOT_SMD", "SOT-343_SC-70-4"),
    "HDR":    ("Connector_PinHeader_2.54mm",
               "PinHeader_1x06_P2.54mm_Vertical_SMD_Pin1Left"),
}

# courtyard extents (w x h at rotation 0), measured from the installed libraries
COURTYARD = {
    "SOT23":  (3.86, 3.40),
    "SOT343": (2.90, 2.20),
    "R":      (2.96, 1.46),
    "R1206":  (4.56, 2.26),
    "C":      (2.96, 1.46),
    "CP":     (9.60, 7.10),
    "HDR":    (6.82, 16.24),
}

FOOT_OF = {c[0]: c[7] for c in sch.COMPONENTS}
VALUE_OF = {c[0]: c[2] for c in sch.COMPONENTS}


def fp_key(footprint_id):
    for k, (lib, name) in FOOT.items():
        if footprint_id == "%s:%s" % (lib, name):
            return k
    raise SystemExit("unmapped footprint: %s" % footprint_id)


def ref_pins(ref):
    return {pin: net for (r, pin), net in sch.NET.items() if r == ref}


def new_uuid():
    return str(uuidlib.uuid4())


# ---- floorplan -------------------------------------------------------------
# Compact functional clusters (local mm offsets), placed in signal order.
# Rotation 0 puts pins 1/2 on the left and 3 on the right; 90 puts pin 3 up;
# 270 puts pin 3 down.  A rotated SOT-23 is 3.86 mm tall, so VP must clear that.
VP = 4.40
HP = 4.80

BLOCKS = {
    # input connector + rail decoupling, right at the entry
    "IO": {
        "J1": (0.0, 0.0, 90),
        "C1": (-3.0, -7.9, 0),
        "C2": (-3.0, -5.6, 0),
        "R17": (6.2, -7.9, 90),
        "R7": (9.4, -7.9, 90),
    },
    # cascode bias ladders
    "DIV": {
        "R4": (0.0, 0.0, 90),
        "R9": (0.0, 3.4, 90),
        "C4": (3.6, 1.7, 90),
        "R10": (7.4, 0.0, 90),
        "R11": (7.4, 3.4, 90),
        "C5": (11.0, 1.7, 90),
    },
    # stage 1: mirror column above the diff pair, tail and bias reference below
    "S1": {
        "R5": (0.0, -VP, 90),
        "R8": (HP, -VP, 90),
        "Q4": (0.0, 0.0, 270),
        "Q6": (HP, 0.0, 270),
        "Q5": (0.0, VP, 270),
        "Q7": (HP, VP, 270),
        "Q8": (2 * HP, VP, 270),
        "R6": (2 * HP + 3.8, 2.2 * VP, 90),
        "Q3": (0.0, 2 * VP, 90),
        "Q1": (0.0, 3 * VP, 90),
        "Q2": (HP, 3 * VP, 90),
        "R18": (HP / 2, 4.15 * VP, 90),
        "Q10": (HP / 2, 4.95 * VP, 90),
        "R3": (HP / 2, 5.8 * VP, 90),
        "R1": (-4.0, 4.95 * VP, 0),
        "Q9": (-8.2, 4.95 * VP, 0),
        "R2": (-8.2, 5.9 * VP, 0),
    },
    # stage 2: follower into Miller-compensated CE
    "S2": {
        "Q12": (0.0, 0.0, 90),
        "Q11": (0.0, VP, 90),
        "R19": (HP, -0.9 * VP, 90),
        "Q13": (HP, 1.1 * VP, 90),
        "C7": (HP / 2 + 0.3, -0.6 * VP, 90),
        "R20": (HP, 2.3 * VP, 90),
        "C6": (HP + 5.2, 2.4 * VP, 0),
    },
    # output: follower, Vbe bias, class-AB pair, isolation, load
    "OUT": {
        "Q15": (0.0, 0.0, 90),
        "Q14": (0.0, VP, 90),
        "Q17": (HP, 0.6 * VP, 90),
        "Q16": (HP, 1.9 * VP, 90),
        "R12": (-4.2, 1.6 * VP, 90),
        "R13": (-4.2, 2.7 * VP, 90),
        "R14": (-8.0, 3.4 * VP, 90),
        "Q19": (0.6, 3.0 * VP, 0),
        "C3": (2.5, 2.2 * VP, 0),
        "R15": (HP, 3.0 * VP, 90),
        "R16": (HP, 4.0 * VP, 90),
        "Q18": (HP, 5.0 * VP, 270),
    },
}
ORDER = ["IO", "DIV", "S1", "S2", "OUT"]
BLOCK_OF = {r: n for n, items in BLOCKS.items() for r in items}


def local_box(ref, rot):
    w, h = COURTYARD[fp_key(FOOT_OF[ref])]
    if rot in (90, 270):
        w, h = h, w
    return (-w / 2, -h / 2, w / 2, h / 2)


def block_box(items):
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    for ref, (dx, dy, rot) in items.items():
        lx0, ly0, lx1, ly1 = local_box(ref, rot)
        x0, y0 = min(x0, lx0 + dx), min(y0, ly0 + dy)
        x1, y1 = max(x1, lx1 + dx), max(y1, ly1 + dy)
    return x0, y0, x1, y1


def expand(offs):
    out = {}
    for n, (ox, oy) in offs.items():
        for ref, (lx, ly, rot) in BLOCKS[n].items():
            out[ref] = (round(ox + lx, 2), round(oy + ly, 2), rot)
    return out


def net_weight(net):
    if net in POWER:
        return 0.2
    if net in HIGH_Z:
        return 4.0
    if net in ("INP", "INN", "OUT"):
        return 3.0
    return 1.0


def net_cost(placement):
    tot = 0.0
    by_net = {}
    for (ref, _pin), net in sch.NET.items():
        if ref in placement:
            by_net.setdefault(net, []).append(placement[ref])
    for net, pts in by_net.items():
        if len(pts) < 2:
            continue
        xs = [q[0] for q in pts]
        ys = [q[1] for q in pts]
        tot += net_weight(net) * (max(xs) - min(xs) + max(ys) - min(ys))
    return tot


def bbox_size(placement):
    xs = [v[0] for v in placement.values()]
    ys = [v[1] for v in placement.values()]
    return max(xs) - min(xs) + 4, max(ys) - min(ys) + 4


def layout_rows(split, gap, rowgap, serpentine=True):
    """Two shelf rows.  With serpentine=True the second row runs right-to-left,
    so a chained signal path folds back on itself instead of stretching the
    whole board width."""
    rows = [ORDER[:split], ORDER[split:]]
    offs, y, x = {}, rowgap, rowgap
    for k, row in enumerate(rows):
        if not row:
            continue
        h = max(block_box(BLOCKS[n])[3] - block_box(BLOCKS[n])[1] for n in row)
        seq = list(row)
        reverse = serpentine and k % 2 == 1
        if reverse:
            seq = seq[::-1]
        cx = rowgap
        for n in seq:
            bx0, by0, bx1, _by1 = block_box(BLOCKS[n])
            offs[n] = (cx - bx0, y - by0)
            cx += (bx1 - bx0) + gap
        y += h + rowgap
    return offs


def legalize(placement, clearance=0.30, passes=600):
    """Push overlapping courtyards apart along their minor axis."""
    def box(ref):
        x, y, rot = placement[ref]
        lx0, ly0, lx1, ly1 = local_box(ref, rot)
        return (x + lx0, y + ly0, x + lx1, y + ly1)

    refs = list(placement)
    for _ in range(passes):
        hits = 0
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                a, b = box(refs[i]), box(refs[j])
                ox = min(a[2], b[2]) - max(a[0], b[0])
                oy = min(a[3], b[3]) - max(a[1], b[1])
                if ox <= 0.0 or oy <= 0.0:
                    continue          # not overlapping
                hits += 1
                if ox < oy:
                    d = (ox + clearance) / 2.0 + 0.01
                    s = 1 if a[0] > b[0] else -1
                    for ref, sign in ((refs[i], s), (refs[j], -s)):
                        x, y, r = placement[ref]
                        placement[ref] = (round(x + sign * d, 2), y, r)
                else:
                    d = (oy + clearance) / 2.0 + 0.01
                    s = 1 if a[1] > b[1] else -1
                    for ref, sign in ((refs[i], s), (refs[j], -s)):
                        x, y, r = placement[ref]
                        placement[ref] = (x, round(y + sign * d, 2), r)
        if not hits:
            break
    return placement


def part_box_of(ref, x, y, rot):
    lx0, ly0, lx1, ly1 = local_box(ref, rot)
    return (x + lx0, y + ly0, x + lx1, y + ly1)


def choose_layout():
    """Search the split point and the inter-cluster gaps for the cheapest wiring."""
    best = None
    for split in range(1, len(ORDER)):
        for gap in (2.4, 3.2, 4.2, 5.2):
            for rowgap in (2.4, 3.2, 4.2):
                for serp in (True, False):
                 pl = legalize(expand(layout_rows(split, gap, rowgap, serp)))
                 w, h = bbox_size(pl)
                 score = net_cost(pl) + 0.8 * math.sqrt(w * h)
                 if best is None or score < best[0]:
                     best = (score, split, gap, rowgap, pl, w, h, serp)
    score, split, gap, rowgap, pl, w, h, serp = best
    print("  split after %s, gap %.1f, rowgap %.1f, serpentine=%s  ->  %.1f x %.1f mm"
          % (ORDER[split - 1], gap, rowgap, serp, w, h))
    return pl, w, h


PLACEMENT, _w, _h = choose_layout()
# shift so the outermost COURTYARD sits at the margin, then size the outline
MARGIN = 2.0
_bx0 = min(part_box_of(k, *v)[0] for k, v in PLACEMENT.items())
_by0 = min(part_box_of(k, *v)[1] for k, v in PLACEMENT.items())
_bx1 = max(part_box_of(k, *v)[2] for k, v in PLACEMENT.items())
_by1 = max(part_box_of(k, *v)[3] for k, v in PLACEMENT.items())
_dx, _dy = MARGIN - _bx0, MARGIN - _by0
PLACEMENT = {k: (round(v[0] + _dx, 2), round(v[1] + _dy, 2), v[2]) for k, v in PLACEMENT.items()}
BOARD_W = round(_bx1 - _bx0 + 2 * MARGIN, 1)
BOARD_H = round(_by1 - _by0 + 2 * MARGIN, 1)


def part_box(ref):
    return part_box_of(ref, *PLACEMENT[ref])


# ---- stage 1: footprints via pcbnew ---------------------------------------
def pad_net(ref, pad_no, pins):
    if pad_no in pins:
        return pins[pad_no]
    if pad_no == "4" and "2" in pins:
        return pins["2"]        # SOT-343 second emitter
    return None


def net_index_tables():
    names = sorted({n for n in sch.NET.values()})
    return {n: i + 1 for i, n in enumerate(names)}, names


def stage_one_footprints():
    board = pcbnew.LoadBoard(TEMPLATE)
    board.GetDesignSettings().SetCopperLayerCount(4)
    try:
        board.GetDesignSettings().SetStackupDescriptor(STACKUP_TEXT)
    except AttributeError:
        pass
    tb = board.GetTitleBlock()
    tb.SetTitle("Discrete Two-Stage Op Amp (Rev E)")
    tb.SetRevision("E")
    tb.SetComment(1, "4 layer, 1.6 mm, all components on top")
    tb.SetComment(2, "placement and netlist generated from the schematic table")

    for ref in PLACEMENT:
        if ref not in FOOT_OF:
            raise SystemExit("part %s is not in the schematic" % ref)
        lib, name = FOOT[fp_key(FOOT_OF[ref])]
        fp = pcbnew.FootprintLoad(os.path.join(FP_DIR, lib + ".pretty"), name)
        if fp is None:
            raise SystemExit("cannot load %s:%s" % (lib, name))
        x, y, rot = PLACEMENT[ref]
        fp.SetReference(ref)
        fp.SetValue(VALUE_OF[ref])
        fp.SetLayer(pcbnew.F_Cu)                  # components on top, always
        fp.SetPosition(pcbnew.VECTOR2I(int(round(x * 1e6)), int(round(y * 1e6))))
        fp.SetOrientationDegrees(rot)
        board.Add(fp)
    counts = {f.GetReference(): len(f.Pads()) for f in board.GetFootprints()}
    if not pcbnew.SaveBoard(SCRATCH, board):
        raise SystemExit("stage 1 save failed")
    return counts


# ---- stage 2: text pass ---------------------------------------------------
def stamp_pad_nets(src, codes):
    lines = src.split("\n")
    out, ref, pins, depth, cur_pad, stamped = [], None, {}, 0, None, 0
    seen = set()
    for ln in lines:
        if cur_pad is None:
            if ln.startswith("\t(footprint "):
                ref, pins = None, {}
            m = re.match(r'^\t\t\(property "Reference" "([^"]+)"', ln)
            if m:
                ref = m.group(1)
                pins = ref_pins(ref)
                seen.add(ref)
            pm = re.match(r'^\t\t\(pad "(\w+)"', ln)
            if pm and ref:
                cur_pad = pm.group(1)
                depth = ln.count("(") - ln.count(")")
                out.append(ln)
                continue
        if cur_pad is not None:
            depth += ln.count("(") - ln.count(")")
            if depth <= 0:
                net = pad_net(ref, cur_pad, pins)
                if net is None:
                    raise SystemExit("%s pad %s has no net in the schematic" % (ref, cur_pad))
                out.append('\t\t\t(net %d "%s")' % (codes[net], net))
                stamped += 1
                cur_pad, depth = None, 0
        out.append(ln)
    missing = set(PLACEMENT) - seen
    if missing:
        raise SystemExit("no footprint block for %s" % sorted(missing))
    return "\n".join(out), stamped


def stage_two_text(pad_counts):
    src = open(SCRATCH).read()
    codes, names = net_index_tables()

    # net declarations: a TOP-LEVEL section, right after (setup ...)
    decls = '\t(net 0 "")\n' + "\n".join('\t(net %d "%s")' % (codes[n], n) for n in names)
    i = src.find("\n\t(setup")
    if i < 0:
        raise SystemExit("no (setup ...) block")
    depth, k = 0, i + 2
    while k < len(src):
        if src[k] == "(":
            depth += 1
        elif src[k] == ")":
            depth -= 1
            if depth == 0:
                break
        k += 1
    end_of_setup = src.index("\n", k)
    src = src[:end_of_setup] + "\n" + decls + src[end_of_setup:]

    src, stamped = stamp_pad_nets(src, codes)
    want = sum(pad_counts.values())
    print("  pads stamped: %d (expected %d)" % (stamped, want))
    if stamped != want:
        raise SystemExit("pad/net stamping mismatch")

    # board outline
    edges = []
    for (x0, y0, x1, y1) in [(0, 0, BOARD_W, 0), (BOARD_W, 0, BOARD_W, BOARD_H),
                             (BOARD_W, BOARD_H, 0, BOARD_H), (0, BOARD_H, 0, 0)]:
        edges.append('\t(gr_line\n\t\t(start %s %s)\n\t\t(end %s %s)\n'
                     '\t\t(stroke\n\t\t\t(width 0.1)\n\t\t\t(type solid)\n\t\t)\n'
                     '\t\t(layer "Edge.Cuts")\n\t\t(uuid "%s")\n\t)'
                     % (x0, y0, x1, y1, new_uuid()))

    # copper pours
    def zone_block(net, layer, x0, y0, x1, y1, clearance=0.25):
        return ('\t(zone\n\t\t(net "%s")\n\t\t(layer "%s")\n'
                '\t\t(uuid "%s")\n\t\t(hatch edge 0.508)\n'
                '\t\t(connect_pads\n\t\t\t(clearance %s)\n\t\t)\n'
                '\t\t(min_thickness 0.254)\n\t\t(filled_areas_thickness no)\n'
                '\t\t(fill yes\n\t\t\t(thermal_gap 0.508)\n'
                '\t\t\t(thermal_bridge_width 0.508)\n\t\t)\n'
                '\t\t(polygon\n\t\t\t(pts\n'
                '\t\t\t\t(xy %s %s) (xy %s %s) (xy %s %s) (xy %s %s)\n'
                '\t\t\t)\n\t\t)\n\t)'
                % (net, layer, new_uuid(), clearance,
                   x0, y0, x1, y0, x1, y1, x0, y1))

    m0 = 0.3
    pours = "\n".join([
        zone_block("GND", "In1.Cu", m0, m0, BOARD_W - m0, BOARD_H - m0),
        zone_block("GND", "B.Cu", m0, m0, BOARD_W - m0, BOARD_H - m0),
        zone_block("+15V", "In2.Cu", m0, m0, BOARD_W - m0, BOARD_H / 2 - 0.75),
        zone_block("-15V", "In2.Cu", m0, BOARD_H / 2 + 0.75, BOARD_W - m0, BOARD_H - m0),
    ])
    anchor = src.find("\n\t(embedded_fonts")
    src = src[:anchor] + "\n" + "\n".join(edges) + "\n" + pours + src[anchor:]
    open(BOARD, "w").write(src)
    return codes, names


# ---- report ---------------------------------------------------------------
def report(board):
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pads.setdefault(p.GetNetname(), []).append(
                (p.GetPosition().x / 1e6, p.GetPosition().y / 1e6))

    def chain(pts):
        pts = list(pts)
        cur = pts.pop(0)
        tot = 0.0
        while pts:
            j = min(range(len(pts)), key=lambda i: abs(pts[i][0] - cur[0]) + abs(pts[i][1] - cur[1]))
            tot += abs(pts[j][0] - cur[0]) + abs(pts[j][1] - cur[1])
            cur = pts.pop(j)
        return tot

    rows = []
    for net, pts in pads.items():
        if not net or len(pts) < 2 or net in POWER:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        rows.append((net, max(max(xs) - min(xs), max(ys) - min(ys)), chain(pts), len(pts)))

    print("\nSignal nets, worst first (bbox = spread, chain = greedy walk length):")
    for net, bbox, cn, n in sorted(rows, key=lambda r: -r[1])[:14]:
        tag = "  <-- high-Z" if net in HIGH_Z else ""
        print("   %-5s pads=%-2d bbox=%5.2f mm  chain=%5.2f mm%s" % (net, n, bbox, cn, tag))

    boxes = [(ref,) + part_box(ref) for ref in PLACEMENT]
    hits = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ox = min(a[3], b[3]) - max(a[1], b[1])
            oy = min(a[4], b[4]) - max(a[2], b[2])
            if ox > 0.01 and oy > 0.01:
                hits.append((a[0], b[0], round(ox, 2), round(oy, 2)))
    print("\nCourtyard overlaps: %d" % len(hits))
    for h in hits[:20]:
        print("   %-5s %-5s  %.2f x %.2f mm" % h)

    off = [(r, round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))
           for r, x0, y0, x1, y1 in boxes
           if x0 < 1.5 or y0 < 1.5 or x1 > BOARD_W - 1.5 or y1 > BOARD_H - 1.5]
    print("Parts within 1.5 mm of the outline:", off if off else "none")
    print("Board: %.1f x %.1f mm" % (BOARD_W, BOARD_H))
    return hits, off


if __name__ == "__main__":
    counts = stage_one_footprints()
    codes, names = stage_two_text(counts)
    print("wrote %s  (%d nets, %d footprints)" % (BOARD, len(names), len(PLACEMENT)))
    b = pcbnew.LoadBoard(BOARD)
    nn = [p.GetNetname() for f in b.GetFootprints() for p in f.Pads()]
    print("reloaded: copper=%d footprints=%d zones=%d pads-with-net=%d/%d"
          % (b.GetCopperLayerCount(), len(b.GetFootprints()), len(list(b.Zones())),
             sum(1 for n in nn if n), len(nn)))
    report(b)
