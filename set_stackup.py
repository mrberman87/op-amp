#!/usr/bin/env python3
"""Write the physical 4-layer stack-up into opamp.kicad_pcb (idempotent).

Layer use (unchanged policy):
  F.Cu    components + all signal routing
  In1.Cu  solid, unbroken GND plane        (reference for every F.Cu trace)
  In2.Cu  +15 V / -15 V pours              (split; referenced to B.Cu GND)
  B.Cu    GND pour, component-free         (short signal hops only if forced)

Build: standard 1.6 mm 4-layer, 1 oz outer / 0.5 oz inner, 7628 prepreg
between each outer layer and its plane, ~1.07 mm core in the middle.  This is
the common default 4-layer build at low-cost fabs (e.g. JLCPCB JLC04161H-7628);
confirm the exact dielectric thicknesses with the fab before ordering.

Why this arrangement suits this board:
  * the thin L1-L2 prepreg keeps every F.Cu trace tight to an unbroken GND
    return, so the In2.Cu split never sits under a signal;
  * the thin L3-L4 prepreg couples the rail pours to the B.Cu GND pour,
    adding a little plane capacitance where the BFP420s need it most (GHz);
  * In1/In2 are typed "power" so an autorouter keeps tracks off the planes.
"""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(ROOT, "opamp.kicad_pcb")

STACK = [
    ("F.SilkS", "Top Silk Screen", None, None),
    ("F.Paste", "Top Solder Paste", None, None),
    ("F.Mask", "Top Solder Mask", 0.01, None),
    ("F.Cu", "copper", 0.035, None),
    ("dielectric 1", "prepreg", 0.2104, ("7628", 4.4, 0.02)),
    ("In1.Cu", "copper", 0.0152, None),
    ("dielectric 2", "core", 1.065, ("FR4", 4.6, 0.02)),
    ("In2.Cu", "copper", 0.0152, None),
    ("dielectric 3", "prepreg", 0.2104, ("7628", 4.4, 0.02)),
    ("B.Cu", "copper", 0.035, None),
    ("B.Mask", "Bottom Solder Mask", 0.01, None),
    ("B.Paste", "Bottom Solder Paste", None, None),
    ("B.SilkS", "Bottom Silk Screen", None, None),
]
FINISH = "HAL lead-free"


def stackup_sexpr():
    out = ["\t\t(stackup"]
    for name, typ, t, diel in STACK:
        out.append('\t\t\t(layer "%s"' % name)
        out.append('\t\t\t\t(type "%s")' % typ)
        if t is not None:
            out.append("\t\t\t\t(thickness %s)" % t)
        if diel:
            mat, er, tand = diel
            out.append('\t\t\t\t(material "%s")' % mat)
            out.append("\t\t\t\t(epsilon_r %s)" % er)
            out.append("\t\t\t\t(loss_tangent %s)" % tand)
        out.append("\t\t\t)")
    out.append('\t\t\t(copper_finish "%s")' % FINISH)
    out.append("\t\t\t(dielectric_constraints no)")
    out.append("\t\t)")
    return "\n".join(out)


def total():
    return sum(t for _n, _ty, t, _d in STACK if t)


def main():
    src = open(BOARD).read()
    # drop any previous stack-up block
    i = src.find("\t\t(stackup")
    if i >= 0:
        depth, k = 0, i
        while True:
            if src[k] == "(":
                depth += 1
            elif src[k] == ")":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        src = src[:i] + src[k + 2:]
    j = src.index("\t(setup\n") + len("\t(setup\n")
    src = src[:j] + stackup_sexpr() + "\n" + src[j:]
    src = re.sub(r'\(4 "In1.Cu" \w+\)', '(4 "In1.Cu" power)', src)
    src = re.sub(r'\(6 "In2.Cu" \w+\)', '(6 "In2.Cu" power)', src)
    src = re.sub(r"\(thickness 1\.6\)", "(thickness %.4f)" % total(), src, count=1)
    open(BOARD, "w").write(src)
    print("stack-up written: %.3f mm total, In1/In2 typed as power planes" % total())


if __name__ == "__main__":
    main()
