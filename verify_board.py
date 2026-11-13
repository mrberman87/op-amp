#!/usr/bin/env python3
"""Gate: the board must match the schematic, layer up correctly, and self-DRC.

Checks that matter for this design, and would be expensive to notice later:

  1. 4 copper layers in the intended order (F.Cu / In1.Cu GND / In2.Cu rails / B.Cu)
  2. every component on the TOP side (the agreed assembly constraint)
  3. every (ref, pin) net in the schematic equals the net on that board pad
  4. SOT-343 (BFP420) pad 4 is tied to pad 2 — the second emitter
  5. no courtyard overlaps
  6. kicad-cli DRC reports no electrical violations (silkscreen and unconnected
     pads are allowed: the board is not routed yet)
"""
import json
import os
import re
import subprocess
import sys

import pcbnew

import gen_pcb as G
import gen_sch_rf as sch

ROOT = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(ROOT, "opamp.kicad_pcb")
fails = []


def check(label, ok, detail=""):
    print("  %-46s %s%s" % (label, "ok" if ok else "FAIL", (" — " + detail) if detail else ""))
    if not ok:
        fails.append(label)


def main():
    if not os.path.exists(BOARD):
        raise SystemExit("no board file — run python3 gen_pcb.py first")
    board = pcbnew.LoadBoard(BOARD)

    enabled = [i for i in range(40) if board.GetEnabledLayers().Contains(i)]
    copper = {board.GetLayerName(i) for i in enabled
              if (board.GetLayerName(i) or "").endswith(".Cu")}
    check("4 copper layers", board.GetCopperLayerCount() == 4 and len(copper) == 4,
          "%s enabled: %s" % (board.GetCopperLayerCount(), sorted(copper)))
    # layer ids enumerate as F,B,In1,In2 — physical stack order is the fab's
    # business; what we control is which net sits on which layer (checked below)
    check("stack is F.Cu + two inner + B.Cu",
          copper == {"F.Cu", "In1.Cu", "In2.Cu", "B.Cu"}, str(sorted(copper)))
    check("no unused inner layers enabled", not board.GetEnabledLayers().Contains(pcbnew.In3_Cu))

    pads = {f.GetReference(): {p.GetPadName(): p.GetNetname() for p in f.Pads()}
            for f in board.GetFootprints()}

    bottom = [f.GetReference() for f in board.GetFootprints() if f.GetLayer() != pcbnew.F_Cu]
    check("all components on top side", not bottom, str(bottom))

    refs_sch = {c[0] for c in sch.COMPONENTS}
    # mounting holes and fiducials exist only on the board (place.BOARD_ONLY)
    import place
    board_only = set(place.BOARD_ONLY)
    check("board-only parts present (holes, fiducials)", board_only <= set(pads),
          "missing %s" % sorted(board_only - set(pads)))
    check("board-only parts carry no nets",
          not any(n for r in board_only for n in pads.get(r, {}).values()))
    pads = {r: v for r, v in pads.items() if r not in board_only}
    check("component set matches schematic", set(pads) == refs_sch,
          "missing %s extra %s" % (sorted(refs_sch - set(pads)), sorted(set(pads) - refs_sch)))

    bad = []
    for (ref, pin), net in sch.NET.items():
        if pads.get(ref, {}).get(pin) != net:
            bad.append("%s.%s want %s got %s" % (ref, pin, net, pads.get(ref, {}).get(pin)))
    check("every schematic pin's net is on its board pad", not bad, "; ".join(bad[:4]))

    s343 = [r for r, pn in pads.items() if len(pn) == 4 and r.startswith("Q")]
    untied = [r for r in s343 if pads[r].get("4") != pads[r].get("2")]
    check("SOT-343 pad 4 tied to pad 2 (%d parts)" % len(s343), len(s343) == 6 and not untied,
          str(untied))

    boxes = [(r,) + G.part_box(r) for r in G.PLACEMENT]
    ov = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if (min(a[3], b[3]) - max(a[1], b[1])) > 0.01 and (min(a[4], b[4]) - max(a[2], b[2])) > 0.01:
                ov.append((a[0], b[0]))
    check("no courtyard overlaps", not ov, str(ov[:5]))

    # KiCad 10 zones are multi-layer; GetLayerName() reports the primary only,
    # so ask each zone which layers it actually covers
    zones = set()
    for z in board.Zones():
        for i in range(40):
            nm = board.GetLayerName(i)
            if nm and nm.endswith(".Cu") and z.IsOnLayer(i):
                zones.add((z.GetNetname(), nm))
    want = {("GND", "In1.Cu"), ("GND", "B.Cu"), ("+15V", "In2.Cu"), ("-15V", "In2.Cu")}
    check("pours: GND on In1+B, rails on In2", zones == want, str(sorted(zones)))

    rpt = "/tmp/opencode/verify_board.drc"
    subprocess.run(["kicad-cli", "pcb", "drc", "--severity-all", "-o", rpt, BOARD],
                   check=True, capture_output=True, timeout=600)
    text = open(rpt).read()
    kinds = re.findall(r"^\[([a-z_]+)\]", text, re.M)
    counts = {k: kinds.count(k) for k in set(kinds)}
    electrical = [k for k in counts if k not in ("silk_overlap", "silk_over_copper",
                                                 "unconnected_items")]
    check("DRC: no electrical/clearance violations", not electrical,
          str({k: counts[k] for k in electrical}))
    print("     DRC breakdown: %s" % counts)
    print("     (silk_* are cosmetic; unconnected_items is expected before routing)")

    if fails:
        print("\nBOARD GATE FAILED: %s" % fails)
        return 1
    print("\nboard gate OK — %d nets, %d parts, %d copper layers"
          % (len({n for n in sch.NET.values()}), len(pads), len(copper)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
