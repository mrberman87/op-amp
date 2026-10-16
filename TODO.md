# TODO — discrete RF BJT op-amp (Rev C)

Status as of commit `8d79396` ("Fix Rev-C schematic wiring, replace offset trimmer
with fixed R8"). The tree is clean and in a **known-good state**:

- `opamp.kicad_sch` regenerates from `gen_sch_rf.py` and passes
  `kicad-cli sch erc` with **0 errors / 0 warnings**.
- `sim/rf_final.py` is the source of truth for the netlist and reproduces the
  documented operating point (Aol 58.8 dB, f-3dB 12.8 MHz, GBW 6.08 GHz,
  PM 66.3 deg, Vos ~0 at RL = 10k).
- The schematic's SPICE netlist matches `sim/rf_final.py` device-for-device
  (checked by hand this session; see task 4 to make that automatic).

Nothing below is started. Items are ordered by importance.

---

## 1. Confirm LCSC availability of the RF transistors (highest priority)

### 1.1 Why this matters

The user's requirement is that the board be sourced from **LCSC**. The blocker
was believed to be that the 11 RF transistors are not in the LCSC/JLCPCB
library. **That belief is now known to be wrong** (see 1.2), but it has not been
confirmed end-to-end, so the sourcing decision is still open.

The design uses 11 transistors — 6x BFP420 (NPN, fT 25 GHz) and 5x BFP520
(PNP, fT 45 GHz):

| Sim name | Schematic | Role | Part |
|---|---|---|---|
| Q1, Q2 | Q1, Q2 | input diff pair | BFP420 |
| Qh | Q7 | regulated-cascode helper | BFP520 |
| Q3, Q4 | Q3, Q4 | PNP mirror load | BFP520 |
| Q3c, Q4c | Q5, Q6 | PNP cascodes | BFP520 |
| Q5 | Q8 | output follower | BFP420 |
| Qtail | Q10 | tail current source | BFP420 |
| Qbuf | Q11 | follower current sink | BFP420 |
| Qb | Q9 | bias reference diode | BFP420 |

These parts are what give the design its 6 GHz GBW. A substitution to a
general-purpose BJT would collapse the GBW and destroy the phase margin — the
published performance depends on 25/45 GHz fT devices.

### 1.2 What is already established

- The `jlcsearch` index originally used to declare "not available" is
  **incomplete**, not authoritative. It carries only the ~100 most popular
  JLCPCB BJTs (all general-purpose, max fT 300 MHz: MMBT3904/3906, 2N3904,
  MMBT2222A, S8050/S8550). That is why BFP420/BFP520 appeared absent.
- LCSC's **own** autocomplete endpoint does recognise these parts:
  - `BFP420` -> `BFP420H6327`, `MBFP420A1`, `MBFP420A2`
  - `BFP520` -> `BFP520H6327`, `BFP520FE6327`
  - also seen: `BFR93AW`, `2SC3356`, `BFG540/X`, `BFT92W,115`
- **Caveat:** an autocomplete *suggestion* means the string is in LCSC's search
  index. It does **not** prove the part is stocked, orderable, or in the
  expected package. That must be confirmed per part (task 1.3).

### 1.3 Tasks

- [ ] **1.3.1** Get the LCSC part numbers (C-codes) for `BFP420H6327`,
      `BFP520H6327`/`BFP520FE6327`, and any alternates (`MBFP420A1/A2`).
- [ ] **1.3.2** For each C-code confirm via the product-detail endpoint:
      stock, price at the needed quantity (6x NPN, 5x PNP), lifecycle status,
      and **package**.
- [ ] **1.3.3** Settle the package question — see task 2. The schematic
      currently uses `Package_TO_SOT_SMD:SOT-23` for all 11 transistors, but
      the Infineon BFP420/BFP520 are normally SOT-343 (4-lead). If the LCSC
      parts are SOT-343 this needs a footprint and pin-map change, and the
      "H6327" / "FE6327" suffixes must be decoded to know which variant it is.
- [ ] **1.3.4** Get C-codes for the passives so a complete BOM can be issued:

      | Ref | Value | Footprint |
      |---|---|---|
      | R1 | 13.7k | R_0603 |
      | R2, R3 | 1k | R_0603 |
      | R4 | 390 | R_0603 |
      | R5 | 22 | R_0603 |
      | R8 | 54.9 (E96, 1%) | R_0603 |
      | R6 | 15k | R_0603 |
      | R7 | 10k | R_0603 |
      | C1, C2 | 100n | C_0603 |
      | J1 | Conn_01x06 | PinHeader_1x06_P2.54mm_Vertical_SMD_Pin1Left |

- [ ] **1.3.5** Decide the ordering strategy and write it into the README:
      - (a) **LCSC-only** — if 1.3.1-1.3.3 come back clean, this is now the
        likely answer and the earlier "redesign around LCSC parts" direction is
        **not needed** (do not start a redesign without re-reading this file).
      - (b) **Consigned parts** — if the RF transistors are not stockable,
        JLCPCB's PCBA service accepts customer-supplied components. Source the
        11 transistors from DigiKey/Mouser and consign them; keep everything
        else LCSC-sourced. Zero schematic/sim change; preserves the design.
      - (c) **Redesign around LCSC general-purpose BJTs** — last resort. Would
        break the 6 GHz GBW claim and require re-doing compensation; treat as a
        project, not a BOM swap.
- [ ] **1.3.6** Optional: commit a small, working sourcing helper so this is not
      re-derived. See 1.4 for the endpoint that works.

### 1.4 Endpoints — what works and what does not

Do not re-walk these; they were all probed this session.

**Works** (needs a desktop-ish `User-Agent`):

- MPN autocomplete (no C-codes, no stock):
  `GET https://wmsc.lcsc.com/ftps/wm/search/v2/pre?keyword=<term>`
  -> `{"code":200,"result":[{"type":"MPN","resultList":[{"key","value","highlight"}]}]}`
- Product detail (needs the C-code — this is the authoritative one, includes
  `stockNumber`):
  `GET https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=Cxxxxx`

**Broken / unusable:**

- `jlcsearch.tscircuit.com/api/search?q=...` — fuzzy nonsense; cannot find
  `SS8050` or `MMBT3904`, which are definitely in the library. Useless for MPN
  existence checks.
- `jlcsearch.tscircuit.com/bjt_transistors/list.json` — only the 100 most
  popular BJTs; **ignores** every filter param (`search`, `q`, `keyword`,
  `mpn`, `name`).
- `wmsc.lcsc.com/ftps/wm/search/v3/global` (+ `/export`) — returns HTTP 200
  with `{"code":500}`. The Nuxt bundle references `encryptFields`, so this
  endpoint likely wants signed/encrypted params. This is the one that would
  give search results with C-codes directly, if it can be unlocked.
- `wmsc.lcsc.com/ftps/wm/search/pre`, `/search/pre/link`, `/search/v2/pre/link`
  — `{}` or 500.
- `www.lcsc.com/search?q=...` — client-side SPA; no product data in the SSR
  HTML.
- `jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList`
  — `code=200` with 0 rows for every query tried.
- `easyeda.com/api/products/search` — 404.

A throwaway helper was written at `/tmp/opencode/lcsc_suggest.py` during the
investigation; `/tmp` is not durable, so re-create it from the spec above if
needed.

---

## 2. Transistor package / footprint reconciliation

- [ ] **2.1** Determine the physical package of the LCSC-stocked ordering codes
      from 1.3.1.
- [ ] **2.2** If it is **not** SOT-23, update every transistor footprint in
      `gen_sch_rf.py` (`SOT23 = "Package_TO_SOT_SMD:SOT-23"`) and check the
      pin map. The schematic uses `Q_NPN_BEC` / `Q_PNP_BEC` (pin 1 = B,
      2 = E, 3 = C) and the symbol `Sim.Pins` fields say `1=B 2=E 3=C`.
      A 4-lead SOT-343 part has a different pinout, so the symbol, the
      `Sim.Pins` mapping, and the drawn wires would all need review.
- [ ] **2.3** Regenerate and re-run ERC (see task 4) after any footprint change.

Note: this is separate from electrical correctness — the *simulation* is done
using the bare die models, so the package change does not alter the numbers.
It affects only the fabricated board.

---

## 3. Fix the `TNOM` bug in the transistor models

### 3.1 The bug

`sim/rf_frontend.py` declares the model cards with a Kelvin temperature in a
field ngspice reads as degrees Celsius:

- line ~13: `BFP420` model ends with `... XTI=3 TNOM=300`
- line ~18: `BFP520` model ends with `... XTI=0.35 TNOM=298`

Per the `.model` card semantics `TNOM` is in degC, so these ask ngspice for
300 degC and 298 degC — not the 27 degC / 25 degC the models were presumably
extracted at. This was confirmed earlier by parameter bisection: the `TNOM`
values are interpreted as Celsius and are model bugs.

The same two strings are duplicated in `gen_sch_rf.py` as the `_BFP420` /
`_BFP520` constants, which are exported into the schematic as the `Sim.*`
symbol fields and therefore into
`kicad-cli sch export netlist --format spice` output. So the generated
schematic carries the same wrong `tnom=300`.

### 3.2 Impact (measured, low)

At the recommended point (Re4 = 54.9, RL = 10k), both models agree closely:

| model | Aol | f-3dB | GBW | PM | Vos |
|---|---|---|---|---|---|
| as shipped (TNOM 300/298) | 58.8 dB | 12.8 MHz | 6.08 GHz | 66.3 deg | −0.6 mV |
| corrected (TNOM 27/25) | 58.8 dB | 12.1 MHz | 6.05 GHz | 66.0 deg | −0.1 mV |

The R8 = 54.9 ohm offset null holds under both, so **the fix does not change
any design decision** — it only makes the model physically right.

### 3.3 Tasks

- [ ] **3.3.1** Decide whether to fix it (the user previously chose not to).
- [ ] **3.3.2** If yes, change `TNOM=300` -> `TNOM=27` and `TNOM=298` ->
      `TNOM=25` in **three** places:
      - `sim/rf_frontend.py` (the authoritative model strings)
      - `gen_sch_rf.py` (`_BFP420`, `_BFP520`)
      - regenerate `opamp.kicad_sch` so the exported netlist matches
- [ ] **3.3.3** Re-run `sim/rf_final.py` and `sim/render_openloop_bode.py`, then
      update the published numbers in `README.md` sections 5e and 6, the §5e
      table, the figure caption, the `rf_final.py` docstring, and the `TEXTS`
      in `gen_sch_rf.py` (which quote "Aol ~= 58.8 dB ... GBW ~= 6 GHz").
- [ ] **3.3.4** Re-run ERC.

---

## 4. Add an ERC + netlist gate so "silently broken" cannot recur

**Why:** the schematic committed in `8d79396` was broken for a whole session
without anyone noticing, because the check that was run reported clean while
`kicad-cli sch erc` found 36 violations (16 errors) on the same file. The root
cause of the breakage was off-grid generator coordinates (J1 stubs at x = 45.08
against pins at 45.72; C1/C2 power symbols at x = 255 against pins at x = 254),
which leave pins connected to nothing.

- [ ] **4.1** Add a `make check`-style script (or a `Makefile`) that runs:
      ```
      python3 gen_sch_rf.py
      kicad-cli sch erc -o /tmp/erc.rpt opamp.kicad_sch        # expect 0 violations
      kicad-cli sch export netlist --format spice -o /tmp/opamp.cir opamp.kicad_sch
      ```
      and fails if ERC reports anything, or if the offline output is
      committed-but-unregenerated.
- [ ] **4.2** Turn the `NETS` dict in `gen_sch_rf.py` into an actual test.
      It is currently described as "Reference netlist for verification" but
      **nothing consumes it** — it is dead reference data. Wire it up to parse
      the `kicad-cli` spice netlist and assert the same connections. That also
      closes the loop on the hand-verification done so far.
- [ ] **4.3** Consider treating `gen_sch_rf.py` output as generated: either
      commit it (current practice) and gate on reproducibility, or regenerate
      on demand. Do not leave it to drift silently again.

---

## 5. Housekeeping (low priority)

- [ ] **5.1** Local backup clutter, all gitignored and safe to delete once the
      committed schematic is confirmed good:
      `gen_sch.py.bak`, `opamp.kicad_sch.bak-pregen`,
      `opamp.kicad_sch.bak2-pregen`.
- [ ] **5.2** `gen_sch.py` (the base emitter) and `gen_sch_rf.py` (the Rev-C
      override) both exist; confirm `gen_sch.py` is still the intended shared
      base and that `gen_sch.py.bak` is not newer.
- [ ] **5.3** `sim/rf_final.py` defaults to `rl="1k"` while the schematic and
      the README's published point use `R7 = 10k`. This is deliberate and
      already documented, but it is a trap — consider defaulting to `10k` or
      making the recommended call explicit in `__main__`.
- [ ] **5.4** Decide whether to keep the earlier-iteration scripts
      (`rf_two.py`, `rf_wide.py`, `waveband*.py`) or move them to an
      `sim/archive/` directory.

---

## Reference

### Reproduction commands

```bash
# regenerate the schematic (writes opamp.kicad_sch)
python3 gen_sch_rf.py

# design-rule check — must report 0 violations
kicad-cli sch erc -o /tmp/erc.rpt opamp.kicad_sch

# schematic -> SPICE netlist (for cross-checking against sim/rf_final.py)
kicad-cli sch export netlist --format spice -o /tmp/opamp.cir opamp.kicad_sch

# open-loop metrics at the recommended point
cd sim && python3 rf_final.py

# re-render the README figure (writes artifacts/freq_response_openloop.png)
cd sim && python3 render_openloop_bode.py
```

### Measured offset-null data (RL = 10k, as-shipped models)

| Re4 (R8) | Aol | f-3dB | GBW | PM | Vos |
|---|---|---|---|---|---|
| 30 | 60.2 dB | 13.8 MHz | 6.25 GHz | 59.9 deg | +16.2 mV |
| 45 | 59.5 dB | 13.0 MHz | 6.14 GHz | 64.8 deg | +4.9 mV |
| 51 | 59.0 dB | 13.0 MHz | 6.14 GHz | 65.6 deg | +1.5 mV |
| **54.9** | **58.8 dB** | **12.8 MHz** | **6.08 GHz** | **66.3 deg** | **−0.6 mV** |
| 60 | 58.7 dB | 12.6 MHz | 5.99 GHz | 67.2 deg | −3.1 mV |

The offset being nulled is **systematic**, not component mismatch: at the
balanced point the reference-side cascode is saturated (Q3c ib ~ −306 uA vs
Q4c ~ −4.4 uA) and the input pair's collectors sit at very different voltages
(Q1 at the mirror reference node ~+14 V, Q2 at the output node), so Early
effect (VAF ~ 28 V) alone gives a ~40 % mirror current error. Matching the two
legs cannot fix it — matched legs were measured to give a *larger* Vos.

### Simulation gotchas (ngspice 45.2)

- `@q[ic]` is not swept by a `.dc` sweep; and `print` after `dc` in a
  `.control` block emits only the first point.
- `wrdata` repeats the scale column before each vector (N vectors -> 2N
  columns). Mis-parsing this silently produced several wrong results.
- A standalone `op` on a directly-wired follower converges to a spurious root
  (OUT = −13.5 V). Use the follower sweep (`dc Vin -14 14 0.5`, read `v(OUT)`
  at Vin = 0) to measure `Vos` — unity-gain, so it equals the input offset.
- Node naming in `sim/rf_final.py` is load-bearing: `c1` is simultaneously
  Q1's collector, the Q3/Q4 base tie and Q3c's collector (the mirror diode
  node). Renaming `c1` breaks the mirror's diode connection.
- The two "corrected" numbers in section 3.2 differ from the shipped ones only
  because of the `TNOM` bug; everything else about the netlist is identical.

### Environment

- KiCad 10.0.6, `kicad-cli` at `/usr/bin/kicad-cli`.
- ngspice 45.2. `matplotlib` is **not** installed; figures are rendered with
  Pillow (`sim/bode.py` + `sim/render_openloop_bode.py`).
- `sim/*.png` is gitignored — the README figure deliberately lives in the
  tracked `artifacts/` directory instead.
