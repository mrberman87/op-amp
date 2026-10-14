#!/usr/bin/env python3
"""Two-stage front-end with real BFP420/BFP520 devices.

Stage 1: NPN differential pair Q1/Q2 with a PNP mirror load (Q3/Q4),
         single-ended output at c2 (sits ~1 Vbe below VCC).
Stage 2: PNP common-emitter Q6 (emitter at VCC), current-source load,
         inverting; Miller cap Cc from c2 to c7.
Buffer : NPN emitter follower Q7 -> OUT, tailed by Ibuf.

Rbias (c2 -> gnd) sets the DC operating point of the interstage node: the
mirror output current equals the second-stage base current plus Irbias, so
a small stage-1 tail current keeps the bias resistor from loading c2.
"""
import math, subprocess, os
from rf_frontend import BFP420, BFP520

WORK = "/tmp/wb2"
os.makedirs(WORK, exist_ok=True)
MODELS = "\n.model QN %s\n.model QP %s\n" % (BFP420, BFP520)


def circuit(vcc="15", it1="0.6m", i2="3m", rbias="56k", cc="2p", cl="4.7p",
            ibuf="5m", voff=None, re6="0", rc7="0", rs="0",
            rload="0", cload="1u"):
    src = (f"Voff INN 0 DC {voff}\nVSRC INP 0 DC 0 AC 1\n"
           if voff is not None else "VSRC INP 0 DC 0 AC 1\n")
    if re6 != "0":
        dev = f"Q6 c7 c2 e6 QP\nRe6 e6 {vcc} {re6}"
    else:
        dev = f"Q6 c7 c2 {vcc} QP"
    if rc7 != "0":
        load = f"Rc7 c7 -{vcc} {rc7}"
    else:
        load = f"I2 c7 -{vcc} DC {i2}"
    if rs != "0":
        load += f"\nRs c7 -{vcc} {rs}"
    comp = "" if cc == "0" else f"Cc c2 c7 {cc}\n"
    acload = (f"Rz c2 cz {rload}\nCz cz 0 {cload}\n"
              if rload != "0" else "")
    return f"""* BFP420/BFP520 two-stage front-end
{MODELS}
VCC {vcc} 0 DC {vcc}
VEE -{vcc} 0 DC -{vcc}
Itail T -{vcc} DC {it1}
Q1 c1 INP T QN
Q2 c2 INN T QN
Q3 c1 c1 {vcc} QP
Q4 c2 c1 {vcc} QP
Rbias c2 0 {rbias}
{dev}
{load}
{comp}{acload}Q7 {vcc} c7 OUT QN
Ibuf OUT -{vcc} DC {ibuf}
CL OUT 0 {cl}
{src}"""


def _run(deck, ctrl, cwd="/tmp/wb2"):
    open(cwd + "/t.cir", "w").write(deck + ctrl + "\n.end\n")
    return subprocess.run(["ngspice", "-b", "t.cir"], cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True).stdout


def find_voff(**kw):
    _run(circuit(voff="0", **kw),
         ".control\ndc Voff -0.6 0.6 0.005\nwrdata vo.dat v(OUT)\n.endc")
    pts = []
    for l in open("/tmp/wb2/vo.dat"):
        s = l.split()
        if len(s) >= 2:
            try:
                pts.append((float(s[0]), float(s[1])))
            except ValueError:
                pass
    for i in range(len(pts) - 1):
        (v0, o0), (v1, o1) = pts[i], pts[i + 1]
        if o0 * o1 <= 0 and o0 != o1:
            return v0 + (-o0 / (o1 - o0)) * (v1 - v0)
    return min(pts, key=lambda p: abs(p[1]))[0]


def metrics(**kw):
    voff = find_voff(**kw)
    _run(circuit(voff=repr(voff), **kw),
         ".control\nop\nac dec 60 1 20gig\nwrdata ac2.dat v(OUT)\n"
         "print v(c2) v(c7) @Q1[ic] @Q4[ic] @Q6[ic]\n.endc",
         "/tmp/wb2")
    rows = []
    for l in open("/tmp/wb2/ac2.dat"):
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
        while d > 180: d -= 360
        while d < -180: d += 360
        ph.append(ph[-1] + d)

    def cr(lv):
        for i in range(len(f) - 1):
            if (m[i]-lv)*(m[i+1]-lv) <= 0 and m[i] != m[i+1]:
                t = (lv-m[i])/(m[i+1]-m[i])
                return (10**(math.log10(f[i])+t*(math.log10(f[i+1])-math.log10(f[i]))),
                        ph[i]+t*(ph[i+1]-ph[i]))
        return (None, None)
    bw = cr(m[0]-3)[0]
    gbw, gph = cr(0.0)
    return dict(voff=voff, aol=m[0], bw=bw, gbw=gbw,
                pm=(180+gph-ph[0]) if gbw else None)


def show(tag, **kw):
    r = metrics(**kw)
    print("%-30s Aol=%5.1f dB  BW=%-9s GBW=%-9s PM=%-7s voff=%.2fmV" % (
        tag, r["aol"],
        ("%.3f MHz" % (r["bw"]/1e6)) if r["bw"] else "none",
        ("%.0f MHz" % (r["gbw"]/1e6)) if r["gbw"] else "none",
        ("%.1f" % r["pm"]) if r["pm"] is not None else "n/a",
        r["voff"]*1e3))


if __name__ == "__main__":
    print("== two-stage, +/-15 V (tune it1, rbias, Cc) ==")
    for rbias in ("56k", "100k"):
        show("rbias=%s"%rbias, rbias=rbias, cc="2p", it1="0.6m", i2="3m")
