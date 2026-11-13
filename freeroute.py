#!/usr/bin/env python3
"""Route opamp.kicad_pcb with Freerouting (Specctra DSN / SES round trip).

    python3 freeroute.py prep        # board -> freerouting/opamp.dsn
    /usr/lib/jvm/java-25-openjdk-amd64/bin/java -jar tools/freerouting/freerouting-2.5.0.jar \\
         -de freerouting/opamp.dsn -do freerouting/opamp.ses \\
         --router.autorouter.max_passes=100 --gui.enabled=false
    python3 freeroute.py import      # freerouting/opamp.ses -> board, stitch, fill

prep:
  * strips any old routing;
  * reshapes R19's thermal copper to where R19 now sits;
  * lays the fixed copper with route.py's router and locks it, so the
    autorouter keeps it: the OUT / OUTA corridor runs on B.Cu (route.corridor),
    a stub from every rail / GND pad to a via into its own plane, and the
    perimeter GND stitching;
  * exports the DSN with the project's net classes (KiCad's exporter only
    writes the default class): Power 0.5 mm / 0.8-0.4 vias, Analog 0.25 mm,
    Default 0.25 mm;
  * leaves the B.Cu GND pour out of the DSN: exported as a plane it would
    shut B.Cu to every other net; it is refilled round the tracks afterwards.

import: reads the SES, refills (R19 thermal copper via route.py --post).

Status: optional.  Tried on this board (Nov 2026): with signals restricted to
F.Cu it completes but takes long detours (vcd ~100 mm round the board edge)
and necks tracks below the 0.2 mm minimum; with B.Cu allowed for low-Z nets
it leaves high-Z nets unrouted.  The board is routed with route.py, which
now includes rip-up/reroute and tidy passes.  Freerouting 2.5 needs Java 25
(the native CLI build crashes in its board-snapshot serialisation).
"""
import os
import re
import subprocess
import sys

import pcbnew

import place

ROOT = os.path.dirname(os.path.abspath(__file__))
BOARD = os.path.join(ROOT, "opamp.kicad_pcb")
PRO = os.path.join(ROOT, "opamp.kicad_pro")
WORK = os.path.join(ROOT, "freerouting")
DSN = os.path.join(WORK, "opamp.dsn")
SES = os.path.join(WORK, "opamp.ses")

JAVA = "/usr/lib/jvm/java-25-openjdk-amd64/bin/java"   # Freerouting 2.5 needs Java 25


def _load_clean():
    """The board with any routing stripped (text level, see place.py)."""
    src, n = place.strip_routing(open(BOARD).read())
    tmp = os.path.join(ROOT, ".fr_tmp_%d.kicad_pcb" % os.getpid())
    open(tmp, "w").write(src)
    import shutil
    shutil.copy(PRO, tmp[:-10] + ".kicad_pro")
    board = pcbnew.LoadBoard(tmp)
    os.remove(tmp)
    os.remove(tmp[:-10] + ".kicad_pro")
    return board, n


def preroute(board):
    """Fixed copper the autorouter must keep: the OUT / OUTA corridor runs,
    a short stub from every rail / GND pad to a via into its own plane (a rail
    via always lands in its own In2.Cu pour, place.rail_miss), and the GND
    stitching round the perimeter.  Built with route.py's router, written to
    the board and locked."""
    import route
    r = route.Router(board)
    route.corridor(r)

    # rail pads over the far side of the corridor first (longest stubs)
    done, fails = set(), 0
    for only_far in (True, False):
        for net in ("+15V", "-15V", "GND"):
            for (ref, num, x, y, cells) in r.pads[net]:
                if (net, ref, num) in r.tht or (ref, num) in done:
                    continue
                far = net != "GND" and place.rail_miss(net, x, y, m=0.0) > 0
                if only_far and not far:
                    continue
                fails += 0 if r.fanout(net, ref, num, x, y, cells) else 1
                done.add((ref, num))
    ns = r.stitch()
    r.write()
    for t in board.GetTracks():
        t.SetLocked(True)
    print("fixed copper: OUT/OUTA corridor runs, %d fanouts (%d failed), %d stitching vias"
          % (len(done), fails, ns))
    print("longest fanout stubs: %s" % ", ".join(
        "%s %.1f mm" % (p_, L) for L, p_, _n in sorted(r.fan_len, reverse=True)[:5]))
    if fails:
        raise SystemExit("fanout failed")


def _blocks(src, head):
    """(start, end) of every balanced s-expression starting with `head`."""
    out, i = [], 0
    while True:
        k = src.find(head, i)
        if k < 0:
            return out
        depth, e = 0, k
        while True:
            c = src[e]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            e += 1
        out.append((k, e + 1))
        i = e + 1


def fix_dsn(path):
    src = open(path).read()
    # B.Cu GND pour out (see docstring)
    for k, e in reversed(_blocks(src, "(plane GND (polygon B.Cu")):
        src = src[:k] + src[e:]
    # an 0.8 / 0.4 via for the Power class
    m = re.search(r'\(padstack "Via\[0-3\]_600:300_um"', src)
    k, e = _blocks(src[m.start():], "(padstack")[0]
    small = src[m.start() + k:m.start() + e]
    big = small.replace("600:300", "800:400").replace(" 600)", " 800)")
    src = src[:m.start() + e] + "\n    " + big + src[m.start() + e:]
    src = src.replace('(via "Via[0-3]_600:300_um")',
                      '(via "Via[0-3]_600:300_um" "Via[0-3]_800:400_um")', 1)
    # net classes
    k, e = _blocks(src, "(class kicad_default")[0]
    nets = src[k:e].split("(circuit")[0].split()[2:]
    analog = set(place.HIGH_Z) & set(nets)
    power = {"+15V", "-15V", "GND"}

    def q(n):
        return '"%s"' % n if re.search(r"[^A-Za-z0-9_]", n) else n

    def cls(name, members, width, clr, via, layers=None):
        use = "".join('\n        (use_layer %s)' % l for l in layers or ())
        return ("(class %s %s\n      (circuit\n        (use_via \"%s\")%s\n      )\n"
                "      (rule\n        (width %d)\n        (clearance %d)\n      )\n    )"
                % (name, " ".join(q(n) for n in sorted(members)), via, use, width, clr))
    # the high-impedance analog nodes and the two inputs stay on F.Cu (over
    # In1's solid GND, nothing but GND between them and B.Cu); the low-
    # impedance and DC nets may cross on B.Cu
    fonly = ((analog - set(place.DC_BIAS)) | {"INP", "INN"}) & {n.strip('"') for n in nets}
    default = [n.strip('"') for n in nets
               if n.strip('"') not in power | fonly]
    classes = "\n    ".join([
        cls("Power", power, 500, 250, "Via[0-3]_800:400_um"),
        cls("Analog", fonly, 250, 250, "Via[0-3]_600:300_um", ["F.Cu"]),
        cls("kicad_default", default, 250, 200, "Via[0-3]_600:300_um", ["F.Cu", "B.Cu"])])
    src = src[:k] + classes + src[e:]
    # Freerouting misreads the fixed fanout at these two SOT-23 collector
    # pads as unconnected (KiCad's DRC sees them connected) and then skips its
    # optimizer: take them out of its netlist; their copper is fixed already
    for pin in DSN_DROP_PINS:
        src = re.sub(r"(\(net \"?\+15V\"?\s*\(pins[^)]*?)\s%s(?=[\s)])" % re.escape(pin), r"\1", src)
    open(path, "w").write(src)


DSN_DROP_PINS = ("Q15-3", "Q17-3")


def prep():
    pro_text = open(PRO).read()
    board, n = _load_clean()
    if n:
        print("stripped %d old tracks / vias" % n)
    pads = None
    for f in board.GetFootprints():
        if f.GetReference() == "R19":
            pads = [(p.GetNumber(), (p.GetBoundingBox().GetLeft(), p.GetBoundingBox().GetTop(),
                     p.GetBoundingBox().GetRight(), p.GetBoundingBox().GetBottom()), p.GetNet())
                    for p in f.Pads()]
    import route
    route.thermal_pad(board, pads, "1", "R19")
    preroute(board)
    ok = pcbnew.SaveBoard(BOARD, board)
    open(PRO, "w").write(pro_text)
    if not ok:
        raise SystemExit("save failed")
    os.makedirs(WORK, exist_ok=True)
    if not pcbnew.ExportSpecctraDSN(board, DSN):
        raise SystemExit("DSN export failed")
    fix_dsn(DSN)
    print("pre-routed OUT / OUTA on B.Cu; wrote %s" % os.path.relpath(DSN, ROOT))
    print("next: %s -jar tools/freerouting/freerouting-2.5.0.jar -de %s -do %s "
          "--router.autorouter.max_passes=100 --gui.enabled=false"
          % (JAVA, os.path.relpath(DSN, ROOT), os.path.relpath(SES, ROOT)))


def do_import():
    pro_text = open(PRO).read()
    board = pcbnew.LoadBoard(BOARD)
    if not pcbnew.ImportSpecctraSES(board, SES):
        raise SystemExit("SES import failed")
    ok = pcbnew.SaveBoard(BOARD, board)
    open(PRO, "w").write(pro_text)
    if not ok:
        raise SystemExit("save failed")
    print("imported %s" % os.path.relpath(SES, ROOT))
    # thermal copper + pour fill in a fresh process (SWIG, see place.py)
    subprocess.run([sys.executable, os.path.join(ROOT, "route.py"), "--post", BOARD], check=True)
    open(PRO, "w").write(pro_text)


if __name__ == "__main__":
    {"prep": prep, "import": do_import}[sys.argv[1]]()
    sys.stdout.flush()
    os._exit(0)
