* v2 - corrected: both drains to mirror input; gain node X defined
VCC  VCC 0 DC 15
VEE  VEE 0 DC -15

R12 INM n_q1g 1k
R13 INP n_q2g 1k
* BOTH JFET drains to mirror input node (proper active-load diff pair)
J1  n_q1d n_q1g n_q1s BF245A
J2  n_q1d n_q2g n_q2s BF245A
RT1a n_q1s n_tail {t*1k}
RT1b n_tail n_q2s {(1-t)*1k}
Q3  n_tail n_q3b n_q3e M2N3904
Q4  n_q3b  n_q3b n_q4e M2N3904
R1  n_q3b 0 14k
R2  n_q3e VEE 470
R3  n_q4e VEE 470

* active load mirror; mirror OUTPUT alone on gain node n_x
R16 VCC n_mire {R16v}
Q9  n_q1d n_q1d n_mire M2N3906
Q10 n_x   n_q1d n_mire M2N3906

* DC definition of gain node (the missing piece)
RBX n_x 0 {RBXv}
RY2 n_y 0 {RY2v}

* VAS chain (unchanged from original)
Q11 VCC n_x n_y M2N3904
Q5  n_q5c n_y n_q5e M2N3906
R6  VCC n_q5e {R6v}
R7  n_q5c n_r78 3.9k
R8  n_r78 VEE 300
C3  n_x n_q5c 12p

Q6  VCC n_q5c n_b1 M2N3904
Q12 n_b1 n_q12b n_b2 M2N3904
R17 n_b1 n_q12b 1.1k
R18 n_q12b n_b2 1k
R9  n_b2 VEE 2.7k
C4  n_b1 n_b2 100n
Q7  VCC n_b1 n_q7e M2N3904
Q8  VEE n_b2 n_q8e M2N3906
R10 n_q7e OUT 2.2
R11 n_q8e OUT 2.2
C1 VCC 0 100n
C2 VCC 0 100n

.param t=0.5
.param R16v=22k
.param RBXv=100k
.param R6v=4.7k
.param RY2v=100k
.model BF245A NJF ( VTO=-1.6 BETA=1.17m LAMBDA=0.003 RD=50 RS=50 CGS=4p CGD=2p PB=0.6 )
.model M2N3904 NPN ( IS=6.734f XTI=3 EG=1.11 VAF=74.03 BF=416.4 ISE=1.073f NE=1.259 IKF=0.2878 XTB=1.5 BR=0.7371 XCJC=0.3693 RC=1 CJC=3.638p CJE=4.493p TR=239.5n TF=301.2p ITF=0.4 VTF=4 XTF=2 RB=10 CJS=0 VJS=0.75 MJS=0.333 PS=10 FC=0.5 )
.model M2N3906 PNP ( IS=1.873f XTI=3 EG=1.11 VAF=93.74 BF=322.5 ISE=1.787f NE=1.492 IKF=0.5773 XTB=1.5 BR=10.02 XCJC=0.3663 RC=7 CJC=2.448p CJE=5.167p TR=153.9n TF=344.8p ITF=0.4 VTF=4 XTF=2 RB=20 CJS=0 VJS=0.75 MJS=0.333 PS=10 FC=0.5 )