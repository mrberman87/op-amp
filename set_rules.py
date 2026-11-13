#!/usr/bin/env python3
"""Write board design rules and net classes into opamp.kicad_pro.

Rules are conservative for a 4-layer JLCPCB-style process (their minimums are
around 0.127 mm outer track/space and a 0.3/0.6 mm via), so the board can be
fabbed without a special-capability order.

Three classes:
  Default   signal
  Power     +/-15V and GND — wide pours/tracks, bigger vias
  Analog    the high-impedance nodes, flagged so they are easy to keep short
"""
import json
import os
import re

import gen_pcb as G
import gen_sch_rf as sch

ROOT = os.path.dirname(os.path.abspath(__file__))
PRO = os.path.join(ROOT, "opamp.kicad_pro")

HIGH_Z = sorted(G.HIGH_Z)
POWER = ["+15V", "-15V", "GND"]

TRACK_WIDTHS = [0.2, 0.25, 0.3, 0.4, 0.5, 0.8]
VIA_SIZES = [{"drill": 0.3, "diameter": 0.6},
             {"drill": 0.35, "diameter": 0.7},
             {"drill": 0.4, "diameter": 0.8},
             {"drill": 0.5, "diameter": 0.9}]


def base_class(name, clearance, track, via_d, via_drill, color):
    return {
        "bus_width": 12,
        "clearance": clearance,
        "diff_pair_gap": 0.2,
        "diff_pair_via_gap": 0.2,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "max_error": 0.005,
        "microvia_diameter": 0.35,
        "microvia_drill": 0.15,
        "name": name,
        "pcb_color": color,
        "priority": 1000,
        "schematic_color": color,
        "track_width": track,
        "tuning_profile": "",
        "via_diameter": via_d,
        "via_drill": via_drill,
        "wire_width": 6,
    }


def main():
    p = json.load(open(PRO))

    ns = p["net_settings"]
    ns["classes"] = [
        base_class("Default", 0.20, 0.20, 0.60, 0.30, "rgba(0, 0, 0, 0.000)"),
        dict(base_class("Power", 0.25, 0.50, 0.80, 0.40, "rgba(255, 60, 60, 0.350)"),
             priority=100),
        dict(base_class("Analog", 0.20, 0.25, 0.60, 0.30, "rgba(60, 180, 255, 0.350)"),
             priority=200),
    ]
    ns["netclass_patterns"] = {"Power": ["+15V", "-15V", "GND"],
                               "Analog": HIGH_Z, "Default": ["*"]}
    ns["netclass_assignments"] = {"Power": POWER, "Analog": HIGH_Z}

    ds = p["board"]["design_settings"]
    ds["rules"].update({
        "min_clearance": 0.20,
        "min_connection": 0.0,
        "min_copper_edge_clearance": 0.30,
        "min_hole_clearance": 0.25,
        "min_hole_to_hole": 0.50,
        "min_silk_clearance": 0.10,
        "min_through_hole_diameter": 0.30,
        "min_track_width": 0.20,
        # 0.6 mm via on a 0.3 mm drill = 0.15 mm ring (standard low-cost
        # 4-layer capability); 0.20 here contradicted the Default via preset
        "min_via_annular_width": 0.15,
        "min_via_diameter": 0.60,
    })
    ds["track_widths"] = [{"width": w} for w in TRACK_WIDTHS]
    ds["via_dimensions"] = VIA_SIZES
    # nets should connect to the plane zones, with a sane thermal relief
    ds.setdefault("defaults", {})["net_impedance_options"] = ds.get(
        "defaults", {}).get("net_impedance_options",
        {"gap_report_settings": {"show_all_gap_violations": False,
                                 "show_only_gap_violations_for_active_net": False}})

    json.dump(p, open(PRO, "w"), indent=1, sort_keys=True)
    print("wrote design rules to", PRO)
    print("  classes: Default / Power(+/-15V, GND) / Analog(%d high-Z nets)" % len(HIGH_Z))
    print("  min clearance %.2f, min track %.2f, min via %.2f/%.2f"
          % (ds["rules"]["min_clearance"], ds["rules"]["min_track_width"],
             ds["rules"]["min_via_diameter"], ds["rules"]["min_through_hole_diameter"]))
    print("  track presets:", TRACK_WIDTHS)
    print("  via presets:", [(v["diameter"], v["drill"]) for v in VIA_SIZES])


if __name__ == "__main__":
    main()
