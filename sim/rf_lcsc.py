#!/usr/bin/env python3
"""LCSC-sourced discrete op-amp — Rev D (real devices, class-AB push-pull).

Everything here uses parts that are actually stocked by LCSC:

    BFP420    NPN  25 GHz, VCEO 4.5 V, SOT-343   LCSC C412737  (input pair, driver, output NPN)
    MMBTH81   PNP 600 MHz, VCEO  20 V, SOT-23    LCSC C190349  (mirror, cascodes, helper, output PNP)
    MMBT3904  NPN 300 MHz, VCEO  40 V, SOT-23    (bias, tail, input/driver/output cascodes)
    MMBT3906  PNP 250 MHz, VCEO  40 V, SOT-23    (not used in the current bias point)

Why the extra cascodes: the BFP420's VCEO is only 4.5 V, so on +/-15 V rails
every BFP420 must be cascoded.  The MMBTH81 mirror/cascode is fine on 20 V.

Topology:

    Q1/Q2  BFP420 diff pair, tail Q10 (MMBT3904)
    Q1c    MMBT3904 reference-side cascode  (protects Q1 from 14 V)
    Q3..Q6 MMBTH81 PNP mirror + regulated cascode, helper Q7
    Q8     BFP420 driver follower, Q8c MMBT3904 cascode
    Q8o    BFP420 output NPN,  Q8oc MMBT3904 cascode
    Q9o    MMBTH81 output PNP
    Q10b   MMBT3904 Vbe multiplier  (class-AB bias)
    Q9     MMBT3904 bias-reference diode

The push-pull output is buffered by Q8, so the gain is no longer load
dependent (the Rev-C emitter follower lost ~7 dB into 1 k).

Validated operating point (RL = 10k):
    Aol 58.5 dB, f-3dB 19.6 MHz (only -1 dB at 10 MHz), PM 54 deg,
    Vos 0.6 mV, output quiescent 2.3 mA, no device over VCEO.
"""
import math, subprocess, os

WORK = "/tmp/lcsc_opamp"
os.makedirs(WORK, exist_ok=True)

# ---- real device models ----------------------------------------------------
BFP420 = ("NPN(IS=0.20045f BF=72.534 NF=1.2432 VAF=28.383 IKF=0.48731 ISE=19.049f "
          "NE=2.0518 BR=7.8287 NR=1.3325 VAR=19.705 IKR=0.69141m ISC=0.019237f NC=1.1724 "
          "RB=8.5757 IRB=0.72983m RBM=3.4849 RE=0.31111 RC=0.10105 CJE=1.8063f VJE=0.8051 "
          "MJE=0.46576 FC=0.73234 CJC=234.53f VJC=0.81696 MJC=0.30232 XCJC=0.3 TF=6.7661p "
          "XTF=0.42199 VTF=0.23794 ITF=1m PTF=0 TR=2.3249n XTB=0 EG=1.11 XTI=3 TNOM=27)")
MMBTH81 = ("PNP(Is=10f Xti=3 Eg=1.11 Vaf=100 Bf=133.8 Ise=1.678p Ne=2.159 Ikf=.1658 Nk=.901 "
           "Xtb=1.5 Var=100 Br=1 Isc=9.519n Nc=3.88 Ikr=5.813 Rc=7.838 Cjc=2.81p Mjc=.1615 "
           "Vjc=.8282 Fc=.5 Cje=2.695p Mje=.3214 Vje=.7026 Tr=11.32n Tf=97.83p Itf=69.29 "
           "Xtf=599u Vtf=10 TNOM=27)")
MMBT3904 = ("NPN(Is=6.734f Xti=3 Eg=1.11 Vaf=74.03 Bf=416.4 Ne=1.259 Ise=6.734f Ikf=66.78m "
            "Xtb=1.5 Br=.7371 Nc=2 Isc=0 Ikr=0 Rc=1 Cjc=3.638p Mjc=.3085 Vjc=.75 Fc=.5 "
            "Cje=4.493p Mje=.2593 Vje=.75 Tr=239.5n Tf=301.2p Itf=.4 Vtf=4 Xtf=2 Rb=10 TNOM=27)")
MMBT3906 = ("PNP(Is=1.41f Xti=3 Eg=1.11 Vaf=18.7 Bf=180.7 Ne=1.5 Ise=0 Ikf=80m Xtb=1.5 Br=4.977 "
            "Nc=2 Isc=0 Ikr=0 Rc=2.5 Cjc=9.728p Mjc=.5776 Vjc=.75 Fc=.5 Cje=8.063p Mje=.3677 "
            "Vje=.75 Tr=33.42n Tf=179.3p Itf=.4 Vtf=4 Xtf=2 Rb=10 TNOM=27)")
MODELS = (f"\n.model QN {BFP420}\n.model QP {MMBTH81}\n"
          f".model Q4N {MMBT3904}\n.model Q4P {MMBT3906}\n")

# ---- design values ---------------------------------------------------------
DEFAULTS = dict(
    rbias="13.7k", reb="1k", ret="180",      # bias reference + tail (R3; thermal/bandwidth balance)
    re3="22", re4="20",                       # mirror degeneration (Re4 nulls Vos)
    rc="22k",                                 # helper load
    r13="6.8k", r14="8.2k",                   # vcn divider  (~1.4 V)
    r15="6.8k", r16="11k",                    # vcd divider  (~3.5 V)
    r10="1.8k", r11="1.2k", r12="10k",        # Vbe multiplier + PNP base pull-down
    re8="4.7", re9="4.7",                     # output emitter resistors
    riso="47",                                # series output isolation (CL stability)
    rtc="470",                                # tail collector resistor (Q10 dissipation)
    cp="0.1p", rl="10k",                      # load
)


def circuit(voff=None, **kw):
    p = dict(DEFAULTS)
    p.update(kw)
    src = (f"Voff INN 0 DC {voff}\nVSRC INP 0 DC 0 AC 1\n"
           if voff is not None else "VSRC INP 0 DC 0 AC 1\n")
    return f"""* LCSC discrete op-amp Rev D - class-AB push-pull
{MODELS}
VCC 15 0 DC 15
VEE -15 0 DC -15
* ---- bias reference (Q9 diode + R1) and tail source (Q10) ----
Rbias 15 vref {p['rbias']}
Q9 vref vref veb Q4N
R2 veb -15 {p['reb']}
Q10 Tc vref vet Q4N
R3 vet -15 {p['ret']}
Rtc T Tc {p['rtc']}
* ---- cascode bias dividers (AC bypassed) ----
R13 15 vcn {p['r13']}
R14 vcn -15 {p['r14']}
C4 vcn 0 100n
R15 15 vcd {p['r15']}
R16 vcd -15 {p['r16']}
C5 vcd 0 100n
* ---- input pair + reference-side cascode ----
Q1 a1 INP T QN
Q1c c1 vcn a1 Q4N
Q2 c2 INN T QN
* ---- PNP mirror, regulated cascode ----
R5 15 e3 {p['re3']}
R8 15 e4 {p['re4']}
Q3 n1 c1 e3 QP
Q5 c1 vcp n1 QP
Q4 n2 c1 e4 QP
Q6 c2 vcp n2 QP
Q7 vcph n2 15 QP
R6 vcph -15 {p['rc']}
Vvcp vcp vcph DC 0
* ---- buffered class-AB push-pull output ----
Q8 x8 c2 d QN
Q8c 15 vcd x8 Q4N
Q8o xo d n8 QN
Q8oc 15 vcd xo Q4N
Re8 n8 OUTA {p['re8']}
Q9o -15 b9 n9 QP
Re9 n9 OUTA {p['re9']}
Q10b d db b9 Q4N
R10 d db {p['r10']}
R11 db b9 {p['r11']}
R12 b9 -15 {p['r12']}
C3 d b9 100n
* series isolation keeps the output stable into capacitive loads
Riso OUTA OUT {p['riso']}
CL OUT 0 {p['cp']}
RL OUT 0 {p['rl']}
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
         ".control\ndc Voff -1.5 1.5 0.005\nwrdata vo.dat v(OUT)\n.endc")
    pts = _pts("vo.dat")
    for i in range(len(pts) - 1):
        (v0, o0), (v1, o1) = pts[i], pts[i + 1]
        if o0 * o1 <= 0 and o0 != o1:
            return v0 + (-o0 / (o1 - o0)) * (v1 - v0)
    return min(pts, key=lambda p: abs(p[1]))[0]


def _bode(voff, **kw):
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


def metrics(tag="", **kw):
    voff = find_voff(**kw)
    f, m, ph = _bode(voff, **kw)
    bw = _cross(f, m, m[0] - 3)
    gbw = _cross(f, m, 0.0)
    pm = 180 + ph[f.index(min(f, key=lambda x: abs(x - gbw)))] - ph[0] if gbw else None
    # phase at the 0 dB crossing
    if gbw:
        for i in range(len(f) - 1):
            if f[i] <= gbw <= f[i + 1]:
                t = (math.log10(gbw) - math.log10(f[i])) / (math.log10(f[i + 1]) - math.log10(f[i]))
                pm = 180 + ph[i] + t * (ph[i + 1] - ph[i]) - ph[0]
                break
    g10 = None
    for i in range(len(f) - 1):
        if f[i] <= 1e7 <= f[i + 1]:
            t = (math.log10(1e7) - math.log10(f[i])) / (math.log10(f[i + 1]) - math.log10(f[i]))
            g10 = m[i] + t * (m[i + 1] - m[i])
            break
    print("%-24s Aol=%5.2f dB  @10MHz=%5.2f dB  f-3dB=%-9s GBW=%-9s PM=%-5s Vos=%.2f mV" % (
        tag, m[0], g10 if g10 else float('nan'),
        ("%.2f MHz" % (bw / 1e6)) if bw else "none",
        ("%.2f GHz" % (gbw / 1e9)) if gbw else "none",
        ("%.1f" % pm) if pm else "n/a", voff * 1e3))
    return f, m, ph


VCE = {
    "Q1  BFP420":  ("a1", "t", 4.5), "Q2  BFP420": ("c2", "t", 4.5),
    "Q1c 3904":    ("c1", "a1", 40),
    "Q3  MMBTH81": ("n1", "e3", 20), "Q4  MMBTH81": ("n2", "e4", 20),
    "Q5  MMBTH81": ("c1", "n1", 20), "Q6  MMBTH81": ("c2", "n2", 20),
    "Q7  MMBTH81": ("15", "vcph", 20),
    "Q8  BFP420":  ("x8", "d", 4.5), "Q8c 3904": ("15", "x8", 40),
    "Q8o BFP420":  ("xo", "n8", 4.5), "Q8oc 3904": ("15", "xo", 40),
    "Q9o MMBTH81": ("n9", "-15", 20),
    "Q10b 3904":   ("d", "b9", 40),
    "Q9  3904":    ("vref", "veb", 40), "Q10 3904": ("tc", "vet", 40),
}


DEV = [
    # (schematic ref, Ic key, VCE-dict key, Pd rating W)
    ("Q1",  "Q1",  "Q1  BFP420",  .21),
    ("Q2",  "Q2",  "Q2  BFP420",  .21),
    ("Q3",  "Q3",  "Q1c 3904",    .20),
    ("Q4",  "Q4",  "Q3  MMBTH81", .225),
    ("Q5",  "Q5",  "Q5  MMBTH81", .225),
    ("Q6",  "Q6",  "Q4  MMBTH81", .225),
    ("Q7",  "Q7",  "Q6  MMBTH81", .225),
    ("Q8",  "Q8",  "Q7  MMBTH81", .225),
    ("Q9",  "Q9",  "Q9  3904",    .20),
    ("Q10", "Q10", "Q10 3904",    .20),
    ("Q11", "Q8",   "Q8  BFP420",  .21),
    ("Q12", "Q8C",  "Q8c 3904",    .20),
    ("Q13", "Q8O",  "Q8o BFP420",  .21),
    ("Q14", "Q8OC", "Q8oc 3904",   .20),
    ("Q15", "Q9O",  "Q9o MMBTH81", .225),
    ("Q16", "Q10B", "Q10b 3904",   .20),
]


def check_vce(**kw):
    voff = find_voff(**kw)
    out = _run(circuit(voff=repr(voff), **kw),
               ".control\nop\n"
               "print v(c1) v(c2) v(a1) v(T) v(e3) v(e4) v(n1) v(n2)\n"
               "print v(vcph) v(vcn) v(vcd) v(d) v(b9) v(x8) v(xo) v(n8) v(n9)\n"
               "print v(veb) v(vet) v(vref) v(tc) v(OUT)\n"
               "print @Q1[ic] @Q2[ic] @Q3[ic] @Q4[ic]\n"
               "print @Q5[ic] @Q6[ic] @Q7[ic] @Q8[ic]\n"
               "print @Q9[ic] @Q10[ic] @Q8c[ic] @Q8o[ic]\n"
               "print @Q8oc[ic] @Q9o[ic] @Q10b[ic]\n"
               ".endc")
    vals = {"15": 15.0, "-15": -15.0}
    ics = {}
    for l in out.splitlines():
        s = l.strip()
        if s.startswith("v(") and "=" in s:
            vals[s[2:s.index(")")]] = float(s.split("=")[1])
        elif s.startswith("@") and "[ic]" in s:
            ics[s[1:s.index("[")].upper()] = float(s.split("=")[1])
    print("Device stress:")
    bad, hot = [], []
    for label, ick, vkey, pmax in DEV:
        nc, ne, vmax = VCE[vkey]
        if nc not in vals or ne not in vals:
            continue
        v = abs(vals[nc] - vals[ne])
        ic = abs(ics.get(ick.upper(), 0.0))
        pd = ic * v
        if v > vmax:
            bad.append("%s %.1f>%.1f V" % (label, v, vmax))
        if pd > 0.5 * pmax:
            hot.append("%s %.0f>%.0f mW" % (label, pd * 1e3, 0.5 * pmax * 1e3))
        print("   %-4s Ic=%6.2f mA  Vce=%6.2f V (max %4.1f)  Pd=%5.1f mW (max %3.0f)%s"
              % (label, ic * 1e3, v, vmax, pd * 1e3, pmax * 1e3,
                 "  OVER" if v > vmax else ("  HOT" if pd > 0.5 * pmax else "")))
    print("   Vce violations:", bad if bad else "NONE")
    print("   >50% Pd:", hot if hot else "none")
    return vals


if __name__ == "__main__":
    print("== Rev D: real LCSC devices, class-AB push-pull ==")
    metrics("final", )
    print()
    check_vce()
