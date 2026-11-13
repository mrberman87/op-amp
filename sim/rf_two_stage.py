#!/usr/bin/env python3
"""Rev E: two-stage, Miller-compensated, LCSC-sourced discrete op-amp.

Reference designators and node names match `opamp.kicad_sch` one-for-one, so a
number quoted from this simulation can be read directly off the schematic.

Stage 1  Q1/Q2 BFP420 diff pair, Q3 MMBT3904 reference cascode,
         Q4-Q8 MMBTH81 regulated-cascode mirror  ->  c2
Buffer 1 Q11 BFP420 follower + Q12 MMBT3904 cascode  ->  d1
Stage 2  Q13 BFP420 common-emitter, R19 collector load,
         R20/C6 emitter degeneration bypassed below ~1.5 Hz  ->  d2
Comp     C7 (Miller) from d1 to d2 — sets the 11.5 MHz bandwidth
Buffer 2 Q14 BFP420 follower + Q15 MMBT3904 cascode  ->  d3
Output   class-AB push-pull Q16 (BFP420) / Q18 (MMBTH81),
         Q19 + R12/R13/R14 Vbe multiplier, C3 speed-up,
         R15/R16 emitter ballast, R17 47R isolation, R7 load

The point of stage 2 is *open-loop gain*: the first stage alone tops out at
58.5 dB (BFP420 VAF = 28.4 V).  With stage 2 the DC gain is ~110 dB, so a
60 dB closed loop has ~50 dB of loop gain; the Miller cap sets the GBW and
hence the closed-loop bandwidth.

Bench-only parts (not on the schematic): VCC, VEE, VSRC, Rf/Rg, CL.
"""
import math, subprocess, os

WORK = "/tmp/lcsc_two"
os.makedirs(WORK, exist_ok=True)

from rf_lcsc import BFP420, MMBTH81, MMBT3904, MMBT3906  # real models

MODELS = (f"\n.model QN {BFP420}\n.model QP {MMBTH81}\n"
          f".model Q4N {MMBT3904}\n.model Q4P {MMBT3906}\n")

# keys are schematic reference designators
DEFAULTS = dict(
    r1="13.7k", r2="1k", r3="180", r18="470",        # bias + tail
    r4="6.8k", r9="8.2k", r10="6.8k", r11="11k",     # cascode dividers
    r5="22", r8="20", r6="22k",                      # mirror degeneration / helper
    r19="1k", r20="50", c6="220u",                   # stage-2 load (1206) / emitter / bypass
    c7="68p",                                        # Miller compensation (sets 60 dB / 11 MHz)
    r12="1.8k", r13="1.2k", r14="10k",               # Vbe multiplier
    r15="4.7", r16="4.7", r17="47", r7="10k",        # ballast / isolation / load
    cl="0.1p",                                       # bench load cap, not a real part
)


def circuit(voff=None, **kw):
    p = dict(DEFAULTS)
    p.update(kw)
    src = (f"Voff INN 0 DC {voff}\nVSRC INP 0 DC 0 AC 1\n"
           if voff is not None else "VSRC INP 0 DC 0 AC 1\n")
    return f"""* Rev E two-stage LCSC op-amp — designators match opamp.kicad_sch
{MODELS}
VCC 15 0 DC 15
VEE -15 0 DC -15
* ---- bias reference + tail ----
R1 15 vref {p['r1']}
Q9 vref vref veb Q4N
R2 veb -15 {p['r2']}
Q10 Tc vref vet Q4N
R3 vet -15 {p['r3']}
R18 T Tc {p['r18']}
* ---- cascode bias dividers ----
R4 15 vcn {p['r4']}
R9 vcn -15 {p['r9']}
C4 vcn 0 100n
R10 15 vcd {p['r10']}
R11 vcd -15 {p['r11']}
C5 vcd 0 100n
* ---- stage 1: diff pair + reference cascode + regulated mirror ----
Q1 a1 INN T QN
Q3 c1 vcn a1 Q4N
Q2 c2 INP T QN
R5 15 e3 {p['r5']}
R8 15 e4 {p['r8']}
Q4 n1 c1 e3 QP
Q5 c1 vcp n1 QP
Q6 n2 c1 e4 QP
Q7 c2 vcp n2 QP
Q8 vcp n2 15 QP
R6 vcp -15 {p['r6']}
* ---- buffer 1 ----
Q11 x8 c2 d1 QN
Q12 15 vcd x8 Q4N
* ---- stage 2: Miller-compensated CE ----
Q13 d2 d1 e1 QN
R19 15 d2 {p['r19']}
R20 e1 0 {p['r20']}
C6 e1 0 {p['c6']}
C7 d1 d2 {p['c7']}
* ---- buffer 2 ----
Q14 x9 d2 d3 QN
Q15 15 vcd x9 Q4N
* ---- class-AB output ----
Q16 xo d3 n8 QN
Q17 15 vcd xo Q4N
R15 n8 OUTA {p['r15']}
Q18 -15 b9 n9 QP
R16 OUTA n9 {p['r16']}
Q19 d3 db b9 Q4N
R12 d3 db {p['r12']}
R13 db b9 {p['r13']}
R14 b9 -15 {p['r14']}
C3 d3 b9 100n
R17 OUTA OUT {p['r17']}
* ---- bench only ----
R7 OUT 0 {p['r7']}
CL OUT 0 {p['cl']}
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
    """Fine offset search: a 110 dB amp needs ~uV resolution, so do a coarse
    scan then a bisection refinement."""
    def out_at(v):
        o = _run(circuit(voff=repr(v), **kw), ".control\nop\nprint v(OUT)\n.endc")
        for l in o.splitlines():
            s = l.strip()
            if s.startswith("v(out)") and "=" in s:
                return float(s.split("=")[1])
        return 0.0

    lo, hi = -0.02, 0.02
    # coarse scan for a sign change
    _run(circuit(voff="0", **kw),
         ".control\ndc Voff -0.02 0.02 0.0005\nwrdata vo.dat v(OUT)\n.endc")
    pts = _pts("vo.dat")
    a = b = None
    for i in range(len(pts) - 1):
        (v0, o0), (v1, o1) = pts[i], pts[i + 1]
        if o0 * o1 <= 0 and o0 != o1:
            a, b = v0, v1
            break
    if a is None:
        return min(pts, key=lambda p: abs(p[1]))[0]
    # bisection to ~1 uV
    for _ in range(40):
        mid = 0.5 * (a + b)
        om = out_at(mid)
        if abs(om) < 1e-4 or (b - a) < 1e-7:
            return mid
        if om > 0:
            a = mid
        else:
            b = mid
    return 0.5 * (a + b)


def bode(voff, **kw):
    _run(circuit(voff=repr(voff), **kw),
         ".control\nop\nac dec 100 1 40gig\nwrdata ac.dat v(OUTA)\n.endc")
    rows = []
    for l in open(WORK + "/ac.dat"):
        s = l.split()
        if len(s) < 3:
            continue
        try:
            rows.append((float(s[0]), float(s[1]), float(s[2])))
        except ValueError:
            pass
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
    return f, m, ph


def _cross(f, y, lv):
    for i in range(len(f) - 1):
        if (y[i] - lv) * (y[i + 1] - lv) <= 0 and y[i] != y[i + 1]:
            t = (lv - y[i]) / (y[i + 1] - y[i])
            return 10 ** (math.log10(f[i]) + t * (math.log10(f[i + 1]) - math.log10(f[i])))
    return None


def _at(f, y, fx):
    for i in range(len(f) - 1):
        if f[i] <= fx <= f[i + 1]:
            t = (math.log10(fx) - math.log10(f[i])) / (math.log10(f[i + 1]) - math.log10(f[i]))
            return y[i] + t * (y[i + 1] - y[i])
    return None


def metrics(tag="", **kw):
    voff = find_voff(**kw)
    f, m, ph = bode(voff, **kw)
    gbw = _cross(f, m, 0.0)
    pm = None
    if gbw:
        pm = 180 + _at(f, ph, gbw) - ph[0]
    g60 = _cross(f, m, 60.0)
    print("%-22s Aol=%6.2f dB  GBW=%-9s PM=%-5s  f(|A|=60dB)=%-9s  f-3dB=%-9s" % (
        tag, m[0],
        ("%.2f GHz" % (gbw / 1e9)) if gbw else "none",
        ("%.1f" % pm) if pm else "n/a",
        ("%.2f MHz" % (g60 / 1e6)) if g60 else "none",
        ("%.1f kHz" % (_cross(f, m, m[0] - 3) / 1e3)) if _cross(f, m, m[0] - 3) else "none"))
    return f, m, ph, voff


def closed_loop(rf="10k", rg="10", **kw):
    """The spec test: non-inverting feedback, gain = 1 + rf/rg = 60 dB."""
    deck = circuit(**kw) + f"\nRf OUTA INN {rf}\nRg INN 0 {rg}\n"
    _run(deck, ".control\nop\nac dec 60 0.01 40gig\nwrdata cl.dat v(OUTA)\n.endc")
    rows = []
    for l in open(WORK + "/cl.dat"):
        s = l.split()
        if len(s) >= 3:
            try:
                rows.append((float(s[0]), float(s[1]), float(s[2])))
            except ValueError:
                pass
    rows.sort()
    f = [r[0] for r in rows]
    m = [20 * math.log10(math.hypot(r[1], r[2])) for r in rows]
    ref = _at(f, m, 1e3)
    bw = _cross(f, m, ref - 3)
    print("closed loop (1+%s/%s): gain=%.2f dB  peak=%.2f dB  f-3dB=%.2f MHz  @10MHz=%.2f dB"
          % (rf, rg, ref, max(m), bw / 1e6 if bw else float("nan"), _at(f, m, 1e7)))


if __name__ == "__main__":
    print("== Rev E: two-stage, Miller compensated ==")
    closed_loop()
