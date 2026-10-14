#!/usr/bin/env python3
"""Real-device (BFP420/BFP520) wideband front-end experiments.

Adds a cascoded PNP mirror load to push the single-stage gain toward the
gm*ro limit (~60 dB for BFP420). Also reports device VCE so we can see the
4.5 V-part voltage problem on +/-15 V rails.
"""
import math, subprocess, os

WORK = "/tmp/wb2"
os.makedirs(WORK, exist_ok=True)

BFP420 = ("NPN(IS=0.20045f BF=72.534 NF=1.2432 VAF=28.383 IKF=0.48731 ISE=19.049f "
          "NE=2.0518 BR=7.8287 NR=1.3325 VAR=19.705 IKR=0.69141m ISC=0.019237f NC=1.1724 "
          "RB=8.5757 IRB=0.72983m RBM=3.4849 RE=0.31111 RC=0.10105 CJE=1.8063f VJE=0.8051 "
          "MJE=0.46576 FC=0.73234 CJC=234.53f VJC=0.81696 MJC=0.30232 XCJC=0.3 TF=6.7661p "
          "XTF=0.42199 VTF=0.23794 ITF=1m PTF=0 TR=2.3249n XTB=0 EG=1.11 XTI=3 TNOM=300)")
BFP520 = ("PNP(IS=15a BF=235 NF=1 VAF=25 IKF=0.4 ISE=25f NE=2 BR=1.5 NR=1 VAR=2 IKR=0.01 "
          "ISC=20f NC=2 RB=11 RBM=7.5 RE=0.6 RC=7.6 CJE=235f VJE=0.958 MJE=0.335 FC=0.5 "
          "CJC=93f VJC=0.661 MJC=0.236 XCJC=1 TF=1.7p XTF=10 VTF=5 ITF=0.7 PTF=50 TR=50n "
          "XTB=-0.25 EG=1.11 XTI=0.35 TNOM=298)")
MODELS = f".model QN {BFP420}\n.model QP {BFP520}\n"


def circuit(vcc="15", itail="6m", rl="47k", cp="4.7p", ibuf="5m",
            vcp=None, voff=None, vcn=None):
    src = (f"Voff INN 0 DC {voff}\nVSRC INP 0 DC 0 AC 1\n"
           if voff is not None else "VSRC INP 0 DC 0 AC 1\n")
    if vcn is not None:                       # cascode the INPUT pair
        core = f"""Q1 a1 INP T QN
Q2 a2 INN T QN
Q1c c1 vcn a1 QN
Q2c c2 vcn a2 QN
Q3 c1 c1 {vcc} QP
Q4 c2 c1 {vcc} QP
Vcn vcn 0 DC {vcn}
"""
    elif vcp is not None:                     # cascoded PNP mirror
        core = (f"Q1 c3 INP T QN\nQ2 c2 INN T QN\n"
                f"Q3 b b {vcc} QP\nQ3c c3 vcp b QP\nQ4 c4 b {vcc} QP\n"
                f"Q4c c2 vcp c4 QP\nVcp vcp 0 DC {vcp}\n")
    else:                                     # simple mirror
        core = (f"Q1 c3 INP T QN\nQ2 c2 INN T QN\n"
                f"Q3 c3 c3 {vcc} QP\nQ4 c2 c3 {vcc} QP\n")
    return f"""* BFP420/BFP520 front-end
{MODELS}
VCC {vcc} 0 DC {vcc}
VEE -{vcc} 0 DC -{vcc}
Itail T -{vcc} DC {itail}
{core}RL c2 0 {rl}
CL c2 0 {cp}
Q5 {vcc} c2 OUT QN
Ibuf OUT -{vcc} DC {ibuf}
{src}"""


def _run(deck, ctrl, cwd):
    open(cwd + "/b.cir", "w").write(deck + ctrl + "\n.end\n")
    return subprocess.run(["ngspice", "-b", "b.cir"], cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True).stdout


def find_voff(cwd="/tmp/wb2", **kw):
    kw = dict(kw); kw["voff"] = "0"
    _run(circuit(**kw),
         ".control\ndc Voff -120m 120m 0.05m\nwrdata dsw.dat v(OUT)\n.endc", cwd)
    pts = []
    for l in open(cwd + "/dsw.dat"):
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


def metrics(vcc="15", itail="6m", rl="47k", cp="4.7p", vcp=None, ibuf="5m",
            vcn=None):
    cwd = "/tmp/wb2"
    voff = find_voff(vcc=vcc, itail=itail, rl=rl, cp=cp, ibuf=ibuf, vcp=vcp,
                     vcn=vcn)
    _run(circuit(vcc=vcc, itail=itail, rl=rl, cp=cp, ibuf=ibuf, vcp=vcp,
                 vcn=vcn, voff=repr(voff)),
         ".control\nop\nac dec 60 1 20gig\nwrdata ac.dat v(OUT)\n.endc", cwd)
    rows = []
    for l in open(cwd + "/ac.dat"):
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
    return dict(voff=voff, aol=m[0], bw=bw, gbw=gbw, pm=(180+gph) if gbw else None)


def show(tag, **kw):
    r = metrics(**kw)
    print("%-30s Aol=%5.1f dB  BW=%-9s GBW=%-9s PM=%-7s voff=%.1fmV" % (
        tag, r["aol"],
        ("%.3f MHz" % (r["bw"]/1e6)) if r["bw"] else "none",
        ("%.0f MHz" % (r["gbw"]/1e6)) if r["gbw"] else "none",
        ("%.1f" % r["pm"]) if r["pm"] is not None else "n/a",
        r["voff"]*1e3))


def vce(vcp="13.5", **kw):
    voff = find_voff(vcp=vcp, **kw)
    out = _run(circuit(voff=repr(voff), vcp=vcp, **kw),
               ".control\nop\nprint v(c2) v(c3) v(b) v(c4)\n"
               "print @Q1[ic] @Q2[ic] @Q3[ic] @Q4[ic] @Q3c[ic] @Q4c[ic]\n.endc",
               "/tmp/wb2")
    for l in out.splitlines():
        if l.strip().startswith(("v(", "@")):
            print("   " + l.strip())


if __name__ == "__main__":
    print("== cascoded mirror (tune PNP cascode bias vcp) ==")
    for vcp in ("13.0", "13.2", "13.4", "13.6"):
        show("vcp=%s" % vcp, vcp=vcp, itail="6m", rl="47k", cp="4.7p")
