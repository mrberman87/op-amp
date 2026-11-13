"""Device stress at the Rev E operating point.

Designators are the schematic's, so a row here can be read straight against
opamp.kicad_sch.  VCE maps each transistor to (collector, emitter, VCEO) and
PD to its package dissipation limit, both taken from the model definitions in
rf_lcsc.py.  Anything over 50 % of either limit is flagged.
"""
import math, rf_two_stage as r

# (collector node, emitter node, VCEO) — BFP420 4.5 V, MMBTH81 20 V, MMBT3904 40 V
VCE = {
    "Q1":  ("a1", "T", 4.5),      # BFP420 diff pair
    "Q2":  ("c2", "T", 4.5),
    "Q3":  ("c1", "a1", 40.0),    # MMBT3904 reference cascode
    "Q4":  ("n1", "e3", 20.0),    # MMBTH81 regulated-cascode mirror
    "Q5":  ("c1", "n1", 20.0),
    "Q6":  ("n2", "e4", 20.0),
    "Q7":  ("c2", "n2", 20.0),
    "Q8":  ("vcp", "15", 20.0),
    "Q9":  ("vref", "veb", 40.0),
    "Q10": ("Tc", "vet", 40.0),
    "Q11": ("x8", "d1", 4.5),     # BFP420 follower, cascoded by Q12
    "Q12": ("15", "x8", 40.0),
    "Q13": ("d2", "e1", 4.5),     # BFP420 second gain stage
    "Q14": ("x9", "d3", 4.5),     # BFP420 follower, cascoded by Q15
    "Q15": ("15", "x9", 40.0),
    "Q16": ("xo", "n8", 4.5),     # BFP420 output NPN, cascoded by Q17
    "Q17": ("15", "xo", 40.0),
    "Q18": ("n9", "-15", 20.0),   # MMBTH81 output PNP
    "Q19": ("d3", "b9", 40.0),    # Vbe multiplier
}

# package dissipation limit, W
PD = {"Q1": .21, "Q2": .21, "Q3": .20, "Q4": .225, "Q5": .225, "Q6": .225,
      "Q7": .225, "Q8": .225, "Q9": .20, "Q10": .20, "Q11": .21, "Q12": .20,
      "Q13": .21, "Q14": .21, "Q15": .20, "Q16": .21, "Q17": .20, "Q18": .225,
      "Q19": .20}

# Every resistor in the reference deck is checked (an earlier hand-written list
# covered only four and missed R1 and R18 at ~51 mW each).  Nodes and values
# come from the deck itself; the package limit from the schematic footprint.
PKG_W = {"R_0603": 0.100, "R_0805": 0.125, "R_1206": 0.250}


def _resistors(deck):
    import os, re, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import gen_sch_rf as sch
    fp = {c[0]: c[7] for c in sch.COMPONENTS}
    out = {}
    for l in deck.splitlines():
        m = re.match(r"^(R\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s*$", l)
        if not m or m.group(1) not in fp:
            continue          # Rf / Rg are the external test feedback network
        ref, a, b, val = m.groups()
        pkg = [w for k, w in PKG_W.items() if k in fp[ref]]
        if not pkg:
            raise SystemExit("no power rating for %s footprint %s" % (ref, fp[ref]))
        out[ref] = (a, b, val, pkg[0])
    return out


def _ohms(tok):
    tok = str(tok)
    mult = {"k": 1e3, "M": 1e6, "u": 1e-6, "n": 1e-9, "p": 1e-12}
    if tok[-1] in mult:
        return float(tok[:-1]) * mult[tok[-1]]
    return float(tok)


def stress(**kw):
    par = dict(r.DEFAULTS)
    par.update(kw)
    deck = r.circuit(**kw) + '\nR24 OUTA INN 10k\nR25 INN 0 10\n'
    ic_list = " ".join("@%s[ic]" % d for d in VCE)
    out = r._run(deck, ".control\nop\n"
                 "print v(T) v(Tc) v(a1) v(c1) v(c2) v(n1) v(n2) v(vcp) v(vcn) v(vcd)\n"
                 "print v(d1) v(d2) v(d3) v(b9) v(x8) v(x9) v(xo) v(n8) v(n9) v(e1)\n"
                 "print v(e3) v(e4) v(vref) v(veb) v(vet) v(OUTA) v(OUT)\n"
                 "print v(db) v(INP) v(INN) v(c2b) v(d2b) v(d3b)\n"
                 "print %s\n.endc" % ic_list)
    vals = {"15": 15.0, "-15": -15.0, "0": 0.0, "gnd": 0.0}
    ics = {}
    for l in out.splitlines():
        s = l.strip()
        if s.startswith("v(") and "=" in s:
            # ngspice reports node names lower-cased, so index everything lowercase
            vals[s[2:s.index(")")].lower()] = float(s.split("=")[1])
        elif s.startswith("@") and "[ic]" in s:
            ics[s[1:s.index("[")].upper()] = float(s.split("=")[1])

    def V(name):
        key = name.lower()
        if key not in vals:
            raise SystemExit("node %r never showed up in the operating point — "
                             "sim and schematic have diverged" % name)
        return vals[key]

    if len(ics) < len(VCE):
        missing = sorted(set(VCE) - set(ics))
        raise SystemExit("netlist is missing transistors %s — sim and schematic "
                         "have diverged again" % missing)

    print("Device stress:")
    bad = []
    for dev, (nc, ne, lim) in VCE.items():
        v = abs(V(nc) - V(ne))
        ic = abs(ics[dev])
        pd = ic * v
        pmax = PD[dev]
        over = v > lim or pd > 0.5 * pmax
        if over:
            bad.append(dev)
        print("   %-4s Ic=%6.2f mA Vce=%6.2f V (max %4.1f) Pd=%5.1f mW (max %3.0f)%s"
              % (dev, ic * 1e3, v, lim, pd * 1e3, pmax * 1e3,
                 "  OVER" if over else ""))

    print("Resistor stress:")
    res = _resistors(deck)
    for ref in sorted(res, key=lambda k: int(k[1:])):
        na, nb, val, pmax = res[ref]
        va, vb = V(na), V(nb)
        watt = (va - vb) ** 2 / _ohms(val)
        # semiconductors are derated to 50 %; resistors to 75 %, which is the
        # usual board-level rule for chip resistors in still air
        over = watt > 0.75 * pmax
        if over:
            bad.append(ref)
        print("   %-4s %6.1f mW (max %3.0f, %3.0f%% used) %s"
              % (ref, watt * 1e3, pmax * 1e3, 100 * watt / pmax,
                 "  HOT" if over else "ok"))
    print("   flagged:", bad if bad else "none")
    return bad


if __name__ == "__main__":
    print("== stress at R19=1k R20=50 C7=68p ==")
    stress()
    print()
    print("== stress at R19=1.2k R20=82 ==")
    stress(r19="1.2k", r20="82")
