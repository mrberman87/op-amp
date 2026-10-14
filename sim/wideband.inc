* Wideband op-amp prototype (high-fT RF BJT input, single cascode-free stage + follower)
* Target: Aol ~ 45 dB, open-loop -3dB ~ 10 MHz, PM ~ 53 deg.
* NOTE: generic high-fT models (TF=25p/40p => fT ~ 6.4/4 GHz); map to BFR93A/BFP420 etc.
* Open-loop bench below biases INN and drives INP (AC 1 V).
* wideband high-fT prototype
.model QN NPN(IS=1e-14 BF=150 VAF=80 IKF=0.2 ISE=1e-14 NE=2 BR=20 RB=8 RC=4 RE=1 CJE=1.5p CJC=1p TF=25p TR=3n XTB=1.5)
.model QP PNP(IS=1e-14 BF=120 VAF=50 IKF=0.2 ISE=1e-14 NE=2 BR=15 RB=10 RC=5 RE=1 CJE=2p CJC=1.5p TF=40p TR=4n XTB=1.5)
VCC +15V 0 DC 15
VEE -15V 0 DC -15
Itail T -15V DC 3m
Q1 c1 INP T QN
Q2 c2 INN T QN
Q3 c1 c1 +15V QP
Q4 c2 c1 +15V QP
RL c2 0 3.5k
CL c2 0 2.2p
Q5 +15V c2 OUT QN
Ibuf OUT -15V DC 5m
Voff INN 0 DC 0
VSRC INP 0 DC 0 AC 1
