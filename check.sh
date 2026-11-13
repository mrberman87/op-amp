#!/usr/bin/env bash
# Regenerate the Rev-E schematic, ERC it, export the netlist and run the
# closed-loop + device-stress checks.
set -euo pipefail
cd "$(dirname "$0")"

echo "== regenerate schematic =="
python3 gen_sch_rf.py

echo "== ERC =="
kicad-cli sch erc --severity-all -o /tmp/opamp_erc.rpt opamp.kicad_sch
if ! grep -q "0  Errors 0  Warnings" /tmp/opamp_erc.rpt; then
    echo "ERC FAILED:"
    cat /tmp/opamp_erc.rpt
    exit 1
fi

echo "== netlist export =="
kicad-cli sch export netlist --format spice -o /tmp/opamp.cir opamp.kicad_sch

echo "== closed-loop spec test (reference circuit) =="
( cd sim && python3 rf_two_stage.py )

echo "== closed-loop spec test (schematic netlist) =="
python3 sim/verify_netlist.py /tmp/opamp.cir

echo "== device stress =="
( cd sim && python3 stress_two.py )

echo "== board: rules, verify =="
# The board is edited in place (J1 is locked by hand, place.py owns the
# 50 x 40 mm placement), so it is NOT regenerated here: gen_pcb.py would
# rebuild the old outline and discard both.  Re-place with: python3 place.py
python3 set_rules.py >/dev/null
python3 verify_board.py

echo "OK"
