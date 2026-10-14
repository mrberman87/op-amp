#!/usr/bin/env python3
"""Sweep the Miller compensation cap C3 and report open-loop metrics.

For each value it rewrites the C3 line in kicad_export.inc, runs the open-loop
AC bench through the ngspice shared library, and prints:
    C3, Aol(dB), f_-3dB (dominant pole), GBW (0 dB crossing), phase margin.
"""
import os, math, shutil, subprocess, sys

SIM = os.path.dirname(os.path.abspath(__file__))
WORK = "/tmp/cc_sweep"
BASE = open(os.path.join(SIM, "kicad_export.inc")).read()
BENCH = "from_sch_ol.deck"
RUNNER = os.path.join(SIM, "kicad_spice_run.py")


def with_c3(val):
    out = []
    for ln in BASE.splitlines():
        if ln.startswith("C3 ") and ln.split()[-1].endswith("p"):
            ln = ln.rsplit(None, 1)[0] + " " + val
        out.append(ln)
    return "\n".join(out) + "\n"


def sweep(val):
    os.makedirs(WORK, exist_ok=True)
    open(os.path.join(WORK, "kicad_export.inc"), "w").write(with_c3(val))
    shutil.copy(os.path.join(SIM, BENCH), os.path.join(WORK, "bench.cir"))
    subprocess.run([sys.executable, RUNNER, "bench.cir", "op",
                    "ac dec 80 1 3gig", "wrdata out.dat v(/OUT)"],
                   cwd=WORK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    for line in open(os.path.join(WORK, "out.dat")):
        p = line.split()
        if len(p) < 3:
            continue
        try:
            f, re_, im = (float(x) for x in p[:3])
        except ValueError:
            continue
        rows.append((f, re_, im))
    rows.sort()
    f = [r[0] for r in rows]
    mag = [20 * math.log10(math.hypot(r[1], r[2])) for r in rows]
    ang = [math.degrees(math.atan2(r[2], r[1])) for r in rows]
    ph = [ang[0]]
    for v in ang[1:]:
        d = v - ph[-1]
        while d > 180:
            d -= 360
        while d < -180:
            d += 360
        ph.append(ph[-1] + d)

    def cross(level):
        for i in range(len(f) - 1):
            if (mag[i] - level) * (mag[i + 1] - level) <= 0 and mag[i] != mag[i + 1]:
                t = (level - mag[i]) / (mag[i + 1] - mag[i])
                return 10 ** (math.log10(f[i]) + t * (math.log10(f[i + 1]) - math.log10(f[i])))
        return None

    pm = None
    if cross(0.0):
        for i in range(len(f) - 1):
            if mag[i] >= 0 >= mag[i + 1] and mag[i] != mag[i + 1]:
                t = (0 - mag[i]) / (mag[i + 1] - mag[i])
                pm = 180 + ph[i] + t * (ph[i + 1] - ph[i])
                while pm > 180:
                    pm -= 360
                while pm < -180:
                    pm += 360
                break
    return mag[0], cross(mag[0] - 3), cross(0.0), pm


def fmtf(x):
    if x is None:
        return "none"
    return ("%.3f MHz" % (x / 1e6)) if x >= 1e6 else ("%.3f kHz" % (x / 1e3))


def main():
    vals = sys.argv[1:] or ["12p", "8p", "5p", "3p", "2p", "1p", "0.5p",
                            "0.2p", "0.1p", "0.05p", "0.02p", "0.01p"]
    print("  C3       Aol(dB)   f-3dB (dominant pole)   GBW (0dB)      PM")
    for v in vals:
        aol, f3, gbw, pm = sweep(v)
        print("  %-6s   %6.2f    %-22s   %-12s   %s" % (
            v, aol, fmtf(f3), fmtf(gbw),
            ("%.1f deg" % pm) if pm is not None else "n/a"))


if __name__ == "__main__":
    main()
