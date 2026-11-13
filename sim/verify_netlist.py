#!/usr/bin/env python3
"""Verify the schematic's exported SPICE netlist against the Rev E spec.

`rf_two_stage.py` proves the *intended* circuit meets spec.  This proves the
schematic in the file is that same circuit: it re-runs the closed-loop AC test
on the netlist that KiCad exports, so a wiring mistake (a shorted rail, a
swapped pin, a label that does not connect) fails here even if ERC is clean.

Usage:  python3 sim/verify_netlist.py path/to/netlist.cir
        (reads stdin if no path is given)
"""
import math
import os
import re
import subprocess
import sys
import tempfile

TARGET = {
    "gain_db": 59.91,        # closed loop at 1 kHz, 1 + 10k/10
    "peak_db": 59.91,        # no peaking
    "f3db_hz": 11.47e6,
    "gain_10meg_db": 57.96,
}
TOL_DB = 0.05
TOL_F3 = 0.02               # 2 %

# KiCad names a net after its label; a local label yields "/NAME" and a global
# label yields "NAME".  Accept either so the check survives a labelling change.
OUT_NAMES = ("OUT", "/OUT")


def _find_top(netlist):
    """Node on the amplifier side of the 47 R isolation resistor (R17).

    Feedback has to be taken there, not from the OUT terminal: R17 plus the
    1 nF load would otherwise sit inside the loop and read as peaking.
    """
    for l in netlist.splitlines():
        m = re.match(r"^R\S+\s+(\S+)\s+(\S+)\s+47\s*$", l)
        if m:
            a, b = m.group(1), m.group(2)
            if a in OUT_NAMES:
                return b
            if b in OUT_NAMES:
                return a
    raise SystemExit("could not locate the 47 R isolation resistor (R17) "
                     "in the netlist - schematic output stage changed?")


def _named(netlist, name):
    """Return the netlist spelling of `name`, or None if it is not a named net."""
    for spell in (name, "/" + name):
        for l in netlist.splitlines():
            if not re.match(r"^[QRJLC]\S+\s", l):
                continue
            if spell in l.split()[1:]:
                return spell
    return None


def run(path):
    netlist = open(path).read()
    top = _find_top(netlist)
    inp = _named(netlist, "INP")
    inn = _named(netlist, "INN")
    if not inp or not inn:
        raise SystemExit("INP/INN are not named nets in the netlist "
                         "(found %r, %r) - the input pair is not labelled" % (inp, inn))
    body = "\n".join(l for l in netlist.splitlines()
                     if not l.strip().startswith(".ac"))
    deck = body + "\nVCC +15V 0 DC 15\nVEE -15V 0 DC -15\n" \
        "Rf %s %s 10k\nRg %s 0 10\nVSRC %s 0 DC 0 AC 1\n" % (top, inn, inn, inp) + \
        ".control\nop\nac dec 60 0.01 40gig\nwrdata @ac.dat v(%s)\n.endc\n.end\n" % top

    with tempfile.TemporaryDirectory() as d:
        cir = os.path.join(d, "b.cir")
        with open(cir, "w") as f:
            f.write(deck.replace("@ac.dat", os.path.join(d, "ac.dat")))
        subprocess.run(["ngspice", "-b", cir], check=True,
                       capture_output=True, timeout=600)
        rows = []
        for l in open(os.path.join(d, "ac.dat")):
            p = l.split()
            if len(p) >= 3:
                try:
                    rows.append((float(p[0]), float(p[1]), float(p[2])))
                except ValueError:
                    pass
    rows.sort()
    f = [r[0] for r in rows]
    m = [20 * math.log10(max(math.hypot(r[1], r[2]), 1e-30)) for r in rows]

    def at(fx):
        for i in range(len(f) - 1):
            if f[i] <= fx <= f[i + 1]:
                t = (math.log10(fx) - math.log10(f[i])) / (math.log10(f[i + 1]) - math.log10(f[i]))
                return m[i] + t * (m[i + 1] - m[i])
        return None

    gain = at(1e3)
    peak = max(m)
    f3 = None
    for i in range(len(f) - 1):
        if f[i] > 1e5 and (m[i] - (gain - 3)) * (m[i + 1] - (gain - 3)) <= 0:
            t = ((gain - 3) - m[i]) / (m[i + 1] - m[i])
            f3 = 10 ** (math.log10(f[i]) + t * (math.log10(f[i + 1]) - math.log10(f[i])))
            break
    return {"gain_db": gain, "peak_db": peak, "f3db_hz": f3,
            "gain_10meg_db": at(1e7), "feedback_node": top}


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = "/dev/stdin"
    got = run(path)
    print("  feedback taken from node %s" % got["feedback_node"])
    ok = True
    for key, want in TARGET.items():
        have = got[key]
        if have is None:
            print("  %-16s MISSING (no -3 dB crossing found)" % key)
            ok = False
            continue
        if key == "f3db_hz":
            good = abs(have - want) / want <= TOL_F3
            print("  %-16s %10.2f MHz   (want %.2f MHz)  %s"
                  % (key, have / 1e6, want / 1e6, "ok" if good else "FAIL"))
        else:
            good = abs(have - want) <= TOL_DB
            print("  %-16s %10.2f dB    (want %.2f dB)   %s"
                  % (key, have, want, "ok" if good else "FAIL"))
        ok = ok and good
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
