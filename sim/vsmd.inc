* ===== self-contained redesigned core (params) =====
VCC  VCC 0 DC 15
VEE  VEE 0 DC -15
.param t=0.5
.param R7v=1.5k
.param R9v=2.7k
.param Cc1v=12p
.param Cz=22p
.param Rzv=0
.param R6v=900
.param R7v=1.5k
.param C4v=100n
R12 INM n_q1g 1k
R13 INP n_q2g 1k
J1  n_q1d n_q1g n_q1s J2SK209
J2  n_x   n_q2g n_q2s J2SK209
RT1a n_q1s n_tail {t*1k}
RT1b n_tail n_q2s {(1-t)*1k}
Q3  n_tail n_q3b n_q3e FNPN
Q4  n_q3b  n_q3b n_q4e FNPN
R1  n_q3b 0 14k
R2  n_q3e VEE 470
R3  n_q4e VEE 470
R16 VCC n_mire 4.3k
Q9  n_q1d n_q1d n_mire FPNP
Q10 n_mc  n_q1d n_mire FPNP
Q13 n_x   n_vb  n_mc   FPNP
Rb1 VCC n_vb 8.2k
Rb2 n_vb VEE 33k
Cvc n_vb 0 100n
Q11 VCC n_x n_y FNPN
Q5  n_q5cc n_y n_q5e FPNP
Q16 n_q5c n_vc n_q5cc FPNP
Rv1 VCC n_vc 7.5k
Rv2 n_vc VEE 10k
R6  VCC n_q5e {R6v}
C6  n_q5e VCC 100n
R7  n_q5c n_r78 {R7v}
R8  n_r78 VEE 150
Cc1 n_x n_rz {Cc1v}
Rz  n_rz n_q5c {Rzv}
Cz  n_q1d 0 {Cz}
Q6  VCC n_q5c n_b1 FNPN
Q12 n_b1 n_q12b n_b2 FNPN
R17 n_b1 n_q12b 1.1k
R18 n_q12b n_b2 1k
R9  n_b2 VEE {R9v}
C4  n_b1 n_b2 {C4v}
Q7  VCC n_b1 n_q7e FNPN
Q8  VEE n_b2 n_q8e FPNP
R10 n_q7e OUT 2.2
R11 n_q8e OUT 2.2
RLEAK1 n_q1g 0 100Meg
RLEAK2 n_q2g 0 100Meg
RY     n_y  0 100k
.model J2SK209 NJF ( VTO=-0.7 BETA=9.0m LAMBDA=0.006 RD=12 RS=13 CGS=10p CGD=3p PB=0.4 FC=0.5 )
.model FNPN NPN ( IS=6.7f VAF=120 BF=350 ISE=1f NE=1.5 IKF=0.3 XTB=1.5 BR=60 XCJC=0.35 RC=1.5 CJC=1.5p CJE=2.5p TR=10n TF=0.42n RB=15 )
.model FPNP PNP ( IS=1.9f VAF=120 BF=300 ISE=1.7f NE=1.49 IKF=0.5 XTB=1.5 BR=25 XCJC=0.35 RC=2 CJC=2p CJE=3p TR=8n TF=0.55n RB=20 )
