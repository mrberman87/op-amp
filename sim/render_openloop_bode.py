#!/usr/bin/env python3
"""Render the open-loop frequency response (Bode) of the Rev-C op-amp to a PNG.

Runs the same netlist as rf_final.py (the topology captured by the KiCad
schematic) at the recommended operating point -- fixed R8 re4 = 54.9 Ohm and
the schematic's external load RL = 10 kOhm -- then hands the ngspice wrdata
file to bode.py for rendering.

Output: artifacts/freq_response_openloop.png
       (tracked in git, unlike the regenerable sim/*.png scratch plots)
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARTIFACTS = os.path.join(ROOT, "artifacts")
sys.path.insert(0, HERE)
import rf_final  # noqa: E402

DAT = "/tmp/opamp_openloop_ac.dat"
PNG = os.path.join(ARTIFACTS, "freq_response_openloop.png")
TITLE = ("Discrete RF BJT op-amp \u2014 open-loop frequency response "
         "(Rev C, RL = 10 k\u03a9, R8 = 54.9 \u03a9)")


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    kw = dict(re4="54.9", rc="15k", rl="10k")
    voff = rf_final.find_voff(**kw)
    deck = rf_final.circuit(voff=repr(voff), **kw)
    ctrl = (".control\nop\nac dec 60 1 40gig\nset filetype=ascii\n"
            "wrdata %s v(OUT)\n.endc" % DAT)
    rf_final._run(deck, ctrl)
    print("netlist: /tmp/wb3/f.cir  ->  %s  (Vos = %.1f mV)" % (DAT, voff * 1e3))

    subprocess.run([sys.executable, os.path.join(HERE, "bode.py"),
                    DAT, PNG, TITLE, "ol"], check=True)


if __name__ == "__main__":
    main()
