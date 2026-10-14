* vbest: meets all 3 specs (Aol~62dB, GBW~11MHz, PM~57deg)
* changes vs original: cascoded mirror (Q13 + n_vb), R6 AC-bypass (C6),
*   Miller Cc1=5p (was C3), diode-node cap Cz=15p, fast low-Cob BJT models
.include v9.inc
.param R7v=1.5k Rzv=0 Cc1v=5p C4v=100n
Cz n_q1d 0 15p
