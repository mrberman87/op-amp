#!/usr/bin/env python3
"""Prototype: high-fT wideband op amp (single high-gain stage + follower).

Open-loop gain is measured directly: INN is DC-biased, INP driven with AC 1 V,
output probed at the buffer. Metrics: Aol, open-loop -3 dB, GBW, phase margin.
"""
import os, math, subprocess, sys

SIM = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(SIM, "kicad_spice_run.py")


def ckt(p):
    return f"""* wideband high-fT prototype
.model QN NPN(IS=1e-14 BF={p['bfn']} VAF=80 IKF=0.2 ISE=1e-14 NE=2 BR=20 RB=8 RC=4 RE=1 CJE=1.5p CJC=1p TF={p['tf']} TR=3n XTB=1.5)
.model QP PNP(IS=1e-14 BF=120 VAF=50 IKF=0.2 ISE=1e-14 NE=2 BR=15 RB=10 RC=5 RE=1 CJE=2p CJC=1.5p TF={p['tfp']} TR=4n XTB=1.5)
VCC +15V 0 DC 15
VEE -15V 0 DC -15
Itail T -15V DC {p['itail']}
Q1 c1 INP T QN
Q2 c2 INN T QN
Q3 c1 c1 +15V QP
Q4 c2 c1 +15V QP
RL c2 0 {p['rout']}
CL c2 0 {p['cpole']}
Q5 +15V c2 OUT QN
Ibuf OUT -15V DC {p['ibuf']}
Voff INN 0 DC {p['voff']}
VSRC INP 0 DC 0 AC 1
"""


def acdata(p, fmax="20gig"):
    os.makedirs("/tmp/wb", exist_ok=True)
    open("/tmp/wb/bench.cir", "w").write(ckt(p) + ".end\n")
    subprocess.run([sys.executable, RUN, "bench.cir", "op",
                    f"ac dec 60 1 {fmax}", "wrdata out.dat v(OUT)"],
                   cwd="/tmp/wb", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    for l in open("/tmp/wb/out.dat"):
        s = l.split()
        if len(s) < 3:
            continue
        try:
            f, re_, im = (float(x) for x in s[:3])
        except ValueError:
            continue
        rows.append((f, re_, im))
    rows.sort()
    f = [r[0] for r in rows]
    m = [20 * math.log10(math.hypot(r[1], r[2])) for r in rows]
    a = [math.degrees(math.atan2(r[2], r[1])) for r in rows]
    ph = [a[0]]
    for v in a[1:]:
        d = v - ph[-1]
        while d > 180:
            d -= 360
        while d < -180:
            d += 360
        ph.append(ph[-1] + d)
    return f, m, ph


def measure(p):
    f, m, ph = acdata(p)

    def cross(lv):
        for i in range(len(f) - 1):
            if (m[i] - lv) * (m[i + 1] - lv) <= 0 and m[i] != m[i + 1]:
                t = (lv - m[i]) / (m[i + 1] - m[i])
                return (10 ** (math.log10(f[i]) + t * (math.log10(f[i + 1]) - math.log10(f[i]))),
                        ph[i] + t * (ph[i + 1] - ph[i]))
        return (None, None)

    bw = cross(m[0] - 3)[0]
    gbw, gph = cross(0.0)
    pm = (180 + gph) if gbw else None
    if pm is not None:
        while pm > 180:
            pm -= 360
        while pm < -180:
            pm += 360
    return m[0], bw, gbw, pm


def show(tag, p):
    aol, bw, gbw, pm = measure(p)
    print("%-26s Aol=%5.1f dB  o.l.-3dB=%-9s GBW=%-9s PM=%s" % (
        tag, aol,
        ("%.3f MHz" % (bw / 1e6)) if bw else "none",
        ("%.1f MHz" % (gbw / 1e6)) if gbw else "none",
        ("%.1f deg" % pm) if pm is not None else "n/a"))


DEF = dict(tf="25p", tfp="40p", itail="2m", rout="3.9k", cpole="4p",
           ibuf="5m", voff="0", bfn="150")

if __name__ == "__main__":
    base = dict(DEF)
    for cp in ["4p", "3p", "2p", "1.5p", "1p", "0.7p", "0.5p"]:
        p = dict(base)
        p["cpole"] = cp
        show("Cpole=%s" % cp, p)
