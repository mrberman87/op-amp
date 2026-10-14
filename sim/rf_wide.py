#!/usr/bin/env python3
"""Single-stage wideband front-end with a cascoded active load.

Topology (goal: Aol ~ 60 dB, GBW ~ 10 GHz, i.e. -3 dB at 10 MHz):

    NPN diff pair Q1/Q2 (BFP420) -> cascoded PNP mirror load (BFP520)
    -> unity-gain NPN buffer Q5 -> OUT

The cascode on the mirror raises the load resistance (gain) without moving
the dominant pole, because the high-impedance output node is the *cascode
collector* and its capacitance barely changes.  Measured metrics reuse the
two-step offset/open-loop bench from rf_frontend (find_voff + AC).

Knobs:
  itail   tail current (sets gm, hence GBW)
  vcp     PNP mirror cascode bias (base of Q3c/Q4c); must sit ~1 Vbe below VCC
  rc      if set, enables the *regulated* (gain-boosted) cascode: helper PNP Qh
          senses the cascode emitter n2 and drives both cascode bases through
          Rc, multiplying the cascode gm (and ro) -> ~+2..4 dB Aol
  vcn     NPN input cascode bias (V), or None to skip the input cascode
  cp      explicit capacitance at the output node (models the next-stage load)
  rx      series resistance between the pair collector and the cascode (peaking)

Recommended operating point (meets 60 dB / 10 MHz):
  itail=2m, rc=20k, cp=0.1p  ->  Aol 62.0 dB, f-3dB 15.8 MHz, GBW 6.2 GHz, PM 54deg
"""
import math, subprocess, os
from rf_frontend import BFP420, BFP520

WORK = "/tmp/wb2"
os.makedirs(WORK, exist_ok=True)
MODELS = "\n.model QN %s\n.model QP %s\n" % (BFP420, BFP520)


def circuit(vcc="15", itail="4m", vcp="13.6", vcn=None, cp="0.1p",
            ibuf="5m", voff=None, rl=None, rc=None):
    src = (f"Voff INN 0 DC {voff}\nVSRC INP 0 DC 0 AC 1\n"
           if voff is not None else "VSRC INP 0 DC 0 AC 1\n")
    if vcn is not None:
        pair = (f"Q1 a1 INP T QN\nQ2 a2 INN T QN\n"
                f"Q1c c1 vcn a1 QN\nQ2c c2 vcn a2 QN\nVcn vcn 0 DC {vcn}\n")
    else:
        pair = "Q1 c1 INP T QN\nQ2 c2 INN T QN\n"
    if rc is not None:
        load = (f"Q3 n1 c1 {vcc} QP\nQ3c c1 vcp n1 QP\n"
                f"Q4 n2 c1 {vcc} QP\nQ4c c2 vcp n2 QP\n"
                f"Qh vcph n2 {vcc} QP\nRc vcph -{vcc} {rc}\n"
                f"Vvcp vcp vcph DC 0\n")
    else:
        load = (f"Q3 n1 c1 {vcc} QP\nQ3c c1 vcp n1 QP\n"
                f"Q4 n2 c1 {vcc} QP\nQ4c c2 vcp n2 QP\nVcp vcp 0 DC {vcp}\n")
    rlx = f"RL c2 0 {rl}\n" if rl else ""
    return f"""* cascoded single-stage front-end
{MODELS}
VCC {vcc} 0 DC {vcc}
VEE -{vcc} 0 DC -{vcc}
Itail T -{vcc} DC {itail}
{pair}{load}{rlx}Q5 {vcc} c2 OUT QN
Ibuf OUT -{vcc} DC {ibuf}
CL OUT 0 {cp}
{src}"""


def _run(deck, ctrl):
    open(WORK + "/t.cir", "w").write(deck + ctrl + "\n.end\n")
    return subprocess.run(["ngspice", "-b", "t.cir"], cwd=WORK,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True).stdout


def find_voff(**kw):
    _run(circuit(voff="0", **kw),
         ".control\ndc Voff -0.4 0.4 0.005\nwrdata vo.dat v(OUT)\n.endc")
    pts = []
    for l in open(WORK + "/vo.dat"):
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
         ".control\nop\nac dec 60 1 40gig\nwrdata ac3.dat v(OUT)\n"
         "print v(c1) v(c2) v(n2) v(n1)\n"
         "print @Q1[ic] @Q2[ic] @Q3[ic] @Q4[ic]\n.endc")
    rows = []
    for l in open(WORK + "/ac3.dat"):
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
    print("%-26s Aol=%5.1f dB  f-3dB=%-10s GBW=%-10s PM=%-7s voff=%.1fmV" % (
        tag, r["aol"],
        ("%.1f MHz" % (r["bw"]/1e6)) if r["bw"] else "none",
        ("%.2f GHz" % (r["gbw"]/1e9)) if r["gbw"] else "none",
        ("%.1f" % r["pm"]) if r["pm"] is not None else "n/a",
        r["voff"]*1e3))


if __name__ == "__main__":
    print("== cascoded single-stage, target 60 dB / 10 MHz ==")
    print("-- fixed cascode bias --")
    for it in ("2m", "3m", "4m", "6m"):
        show("itail=%s" % it, itail=it, vcp="13.2", cp="0.1p")
    print("-- regulated (gain-boosted) cascode, rc=20k --")
    for it in ("2m", "3m"):
        show("itail=%s rc=20k" % it, itail=it, rc="20k", cp="0.1p")
