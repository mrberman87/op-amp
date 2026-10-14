* FAST-PARTS variant: BC550/BC560-class + faster outputs, higher VAS load
VCC  VCC 0 DC 15
VEE  VEE 0 DC -15
R12 INM n_q1g 1k
R13 INP n_q2g 1k
J1  n_q1d n_q1g n_q1s BF245A
J2  n_x   n_q2g n_q2s BF245A
RT1a n_q1s n_tail {t*1k}
RT1b n_tail n_q2s {(1-t)*1k}
Q3  n_tail n_q3b n_q3e FNPN
Q4  n_q3b  n_q3b n_q4e FNPN
R1  n_q3b 0 14k
R2  n_q3e VEE 470
R3  n_q4e VEE 470
R16 VCC n_mire 4.3k
Q9  n_q1d n_q1d n_mire FPNP
Q10 n_x   n_q1d n_mire FPNP
Q11 VCC n_x n_y FNPN
Q5  n_q5c n_y n_q5e FPNP
R6  VCC n_q5e 1.3k
R7  n_q5c n_r78 10k
R8  n_r78 VEE 1k
C3  n_x n_q5c {C3v}
Q6  VCC n_q5c n_b1 FNPN
Q12 n_b1 n_q12b n_b2 FNPN
R17 n_b1 n_q12b 1.1k
R18 n_q12b n_b2 1k
R9  n_b2 VEE 2.7k
C4  n_b1 n_b2 100n
Q7  VCC n_b1 n_q7e FNPN
Q8  VEE n_b2 n_q8e FPNP
R10 n_q7e OUT 2.2
R11 n_q8e OUT 2.2
C1 VCC 0 100n
C2 VCC 0 100n
RLEAK1 n_q1g 0 100Meg
RLEAK2 n_q2g 0 100Meg
RY     n_y  0 100k
.param t=0.5
.param C3v=12p
.model BF245A NJF ( VTO=-1.6 BETA=1.17m LAMBDA=0.003 RD=50 RS=50 CGS=4p CGD=2p PB=0.6 )
.model FNPN NPN ( IS=6.7f VAF=120 BF=350 ISE=1f NE=1.5 IKF=0.3 XTB=1.5 BR=60 XCJC=0.35 RC=1.5 CJC=1.5p CJE=2.5p TR=10n TF=0.42n RB=15 )
.model FPNP PNP ( IS=1.9f VAF=120 BF=300 ISE=1.7f NE=1.49 IKF=0.5 XTB=1.5 BR=25 XCJC=0.35 RC=2 CJC=2p CJE=3p TR=8n TF=0.55n RB=20 )
