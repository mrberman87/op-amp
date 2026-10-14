#!/usr/bin/env python3
"""Fully self-biased realization of the winning single-stage op-amp.

The ideal current sources used in rf_wide.py (Itail, Ibuf) are replaced by a
real NPN current mirror fed from a resistor reference, and an offset-trim
rheostat RT1 is added at the output mirror emitter.  This is the netlist the
KiCad schematic (gen_sch.py) captures.

Bias generator (shared base vref):
    Rbias  +15 -> vref ; Qb diode (C=B=vref, E=veb) ; Reb veb -> -15
    Qtail  C=T   (input-pair tail)  B=vref  E=vet  Re_tail -> -15
    Qbuf   C=OUT (follower sink)    B=vref  E=veb2 Re_buf  -> -15

Signal path:
    NPN diff pair Q1/Q2 (BFP420)
      -> mirror emitter degeneration Re3/Re4 (Re4 = RT1 trim)
      -> cascoded PNP mirror Q3/Q3c, Q4/Q4c (BFP520) with regulated
         (gain-boosted) cascode helper Qh + Rc
      -> unity-gain NPN buffer Q5 (BFP420) -> OUT

Recommended operating point:
    Rbias 13.7k, Reb 1k -> Iref ~2 mA ; Re_tail 1k -> Itail 2 mA ;
    Re_buf 390 -> Ibuf ~5 mA ; Re3 22, (RT1) Re4 ~30 ; Rc 15k ; Cp 0.1p
    -> Aol 60.5 dB, f-3dB 15.9 MHz, GBW 7.0 GHz, PM 64 deg, Vos ~14 mV.
"""
import math, subprocess, os
from rf_frontend import BFP420, BFP520

WORK = "/tmp/wb3"
os.makedirs(WORK, exist_ok=True)
MODELS = "\n.model QN %s\n.model QP %s\n" % (BFP420, BFP520)


def circuit(rbias="13.7k", reb="1k", ret="1k", rebuf="390", re3="22",
            re4="30", rc="15k", cp="0.1p", rl="1k", voff=None):
    src = (f"Voff INN 0 DC {voff}\nVSRC INP 0 DC 0 AC 1\n"
           if voff is not None else "VSRC INP 0 DC 0 AC 1\n")
    return f"""* self-biased single-stage op-amp
{MODELS}
VCC 15 0 DC 15
VEE -15 0 DC -15
* ---- bias generator ----
Rbias 15 vref {rbias}
Qb vref vref veb QN
Reb veb -15 {reb}
Qtail T vref vet QN
Ret vet -15 {ret}
Qbuf OUT vref veb2 QN
Rebuf veb2 -15 {rebuf}
* ---- input pair ----
Q1 c1 INP T QN
Q2 c2 INN T QN
* ---- mirror emitter degeneration (Re4 = RT1 trim) ----
Re3 15 e3 {re3}
Re4 15 e4 {re4}
* ---- regulated cascoded PNP mirror load ----
Q3 n1 c1 e3 QP
Q3c c1 vcp n1 QP
Q4 n2 c1 e4 QP
Q4c c2 vcp n2 QP
Qh vcph n2 15 QP
Rc vcph -15 {rc}
Vvcp vcp vcph DC 0
* ---- output buffer + load ----
Q5 15 c2 OUT QN
CL OUT 0 {cp}
RL OUT 0 {rl}
{src}"""


def _run(deck, ctrl):
    open(WORK + "/f.cir", "w").write(deck + ctrl + "\n.end\n")
    return subprocess.run(["ngspice", "-b", "f.cir"], cwd=WORK,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          text=True).stdout


def _pts(fn):
    pts = []
    for l in open(WORK + "/" + fn):
        s = l.split()
        if len(s) >= 2:
            try:
                pts.append((float(s[0]), float(s[1])))
            except ValueError:
                pass
    return pts


def find_voff(**kw):
    _run(circuit(voff="0", **kw),
         ".control\ndc Voff -0.6 0.6 0.005\nwrdata vo.dat v(OUT)\n.endc")
    pts = _pts("vo.dat")
    for i in range(len(pts) - 1):
        (v0, o0), (v1, o1) = pts[i], pts[i + 1]
        if o0 * o1 <= 0 and o0 != o1:
            return v0 + (-o0 / (o1 - o0)) * (v1 - v0)
    return min(pts, key=lambda p: abs(p[1]))[0]


def metrics(tag="", **kw):
    voff = find_voff(**kw)
    out = _run(circuit(voff=repr(voff), **kw),
               ".control\nop\nac dec 60 1 40gig\nwrdata ac.dat v(OUT)\n"
               "print v(c1) v(c2) v(e3) v(e4) v(vcph) v(T) v(OUT)\n"
               "print @Q1[ic] @Q2[ic] @Qtail[ic] @Qbuf[ic] @Qh[ic]\n.endc")
    rows = []
    for l in open(WORK + "/ac.dat"):
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
    op = [l.strip() for l in out.splitlines() if l.strip().startswith(("@", "v("))]
    print("%-22s Aol=%5.1f dB  f-3dB=%-9s GBW=%-9s PM=%-6s voff=%.1fmV" % (
        tag, m[0],
        ("%.1f MHz" % (bw/1e6)) if bw else "none",
        ("%.2f GHz" % (gbw/1e9)) if gbw else "none",
        ("%.1f" % (180+gph-ph[0])) if gbw else "n/a", voff*1e3))
    return op


if __name__ == "__main__":
    print("== self-biased single-stage op-amp (target 60 dB / 10 MHz) ==")
    op = metrics("recommended", re4="30", rc="15k")
    for l in op:
        print("     ", l)
    print("-- Vos trim range (RT1 on Q4 emitter) --")
    for re4 in ("0", "15", "30", "45", "60"):
        metrics("Re4(RT1)=%s" % re4, re4=re4, rc="15k")
