#!/usr/bin/env python3
"""Wideband prototype experiments: active load vs. peaking inductors.

Two-step open-loop measurement (needed at high gain, where the DC output rails):
  1. close the loop at DC with a huge inductor, read the needed input offset;
  2. fix INN at that offset, drive INP with AC, probe the output.
"""
import math, subprocess, re, os, tempfile

WORK = "/tmp/wb2"
os.makedirs(WORK, exist_ok=True)

MODELS = """
.model QN NPN(IS=1e-14 BF=150 VAF=80 IKF=0.2 ISE=1e-14 NE=2 BR=20 RB=8 RC=4 RE=1 CJE=1.5p CJC=1p TF=25p TR=3n XTB=1.5)
.model QP PNP(IS=1e-14 BF=120 VAF=50 IKF=0.2 ISE=1e-14 NE=2 BR=15 RB=10 RC=5 RE=1 CJE=2p CJC=1.5p TF=40p TR=4n XTB=1.5)
"""


def circuit(itail="3m", rl="3.5k", lp="", rs="", cp="2p", ibuf="5m",
            iload="", ac_fb=None, voff=None):
    """Non-cascode topology (known-good). Load = RL (series peaking inductor LP)
    to gnd, optional shunt RS, optional DC current-source active load ILOAD."""
    load = ""
    if rl and lp:
        load += f"RL c2 n1 {rl}\nLP n1 0 {lp}\n"
    elif rl:
        load += f"RL c2 0 {rl}\n"
    elif lp:
        load += f"LP c2 0 {lp}\n"
    if rs:
        load += f"RS c2 0 {rs}\n"
    if iload:
        load += f"Iload +15V c2 DC {iload}\n"
    cp_line = f"CL c2 0 {cp}\n" if cp else ""
    fb = "Lfb OUT INN 1e6\n" if ac_fb == "Lfb" else ""
    src = (f"Voff INN 0 DC {voff}\nVSRC INP 0 DC 0 AC 1\n" if voff is not None
           else "VSRC INP 0 DC 0 AC 1\n")
    return f"""* wideband experiment
{MODELS}
VCC +15V 0 DC 15
VEE -15V 0 DC -15
Itail T -15V DC {itail}
Q1 c3 INP T QN
Q2 c2 INN T QN
Q3 c3 c3 +15V QP
Q4 c2 c3 +15V QP
{load}{cp_line}Q5 +15V c2 OUT QN
Ibuf OUT -15V DC {ibuf}
{fb}{src}"""


def find_voff(**kw):
    """Sweep the input offset and interpolate the point where the (railed)
    output crosses mid-rail: that is the linear bias point of the open loop."""
    kw = dict(kw)
    kw["ac_fb"] = None
    kw["voff"] = "0"
    deck = circuit(**kw) + """
.control
dc Voff -60m 60m 0.02m
wrdata dcsw.dat v(OUT)
.endc
.end
"""
    open(WORK + "/t.cir", "w").write(deck)
    subprocess.run(["ngspice", "-b", WORK + "/t.cir"], cwd=WORK,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pts = []
    for l in open(WORK + "/dcsw.dat"):
        s = l.split()
        if len(s) < 2:
            continue
        try:
            pts.append((float(s[0]), float(s[1])))
        except ValueError:
            continue
    for i in range(len(pts) - 1):
        (v0, o0), (v1, o1) = pts[i], pts[i + 1]
        if (o0) * (o1) <= 0 and o0 != o1:
            t = -o0 / (o1 - o0)
            return v0 + t * (v1 - v0)
    best = min(pts, key=lambda p: abs(p[1]), default=(0.0, 0.0))
    return best[0]


def metrics(**kw):
    voff = find_voff(**{k: v for k, v in kw.items() if k != "voff"})
    kw["voff"] = repr(voff)
    deck = circuit(**kw) + """
.control
op
ac dec 80 1 30gig
wrdata out.dat v(OUT)
.endc
.end
"""
    open(WORK + "/t.cir", "w").write(deck)
    subprocess.run(["ngspice", "-b", WORK + "/t.cir"], cwd=WORK,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = []
    for l in open(WORK + "/out.dat"):
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
    return dict(voff=voff, aol=m[0], bw=bw, gbw=gbw, pm=pm, peak=max(m) - m[0])


def show(tag, **kw):
    r = metrics(**kw)
    print("%-34s Aol=%5.1f dB  BW=%-9s GBW=%-9s PM=%-7s peak=%+.2f dB  voff=%.2fmV" % (
        tag, r["aol"],
        ("%.3f MHz" % (r["bw"] / 1e6)) if r["bw"] else "none",
        ("%.0f MHz" % (r["gbw"] / 1e6)) if r["gbw"] else "none",
        ("%.1f deg" % r["pm"]) if r["pm"] is not None else "n/a",
        r["peak"], r["voff"] * 1e3))


if __name__ == "__main__":
    print("== baseline (matches 45 dB prototype) ==")
    show("RL=3.5k", rl="3.5k", cp="2p")
    print("== raise gain with the SAME resistor load ==")
    for rl in ("4.7k", "10k", "22k", "47k", "100k", "1Meg"):
        show("RL=%s" % rl, rl=rl, cp="2p")
    print("== ACTIVE LOAD: ideal current source (DC) + shunt R for gain ==")
    for rs in ("22k", "47k", "100k"):
        show("Iload=1.5m + RS=%s" % rs, rl="", iload="1.5m", rs=rs, cp="2p")
    print("== PEAKING INDUCTOR (shunt peaking) on the active-load node ==")
    for lp in ("1u", "2.2u", "4.7u", "10u"):
        show("Iload=1.5m RS=47k + Lp=%s" % lp, rl="", iload="1.5m", rs="47k",
             lp=lp, cp="2p")
