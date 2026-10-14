.model __Q16 PNP
+            is=1.9f
+            bf=300
+            vaf=120
+            ikf=0.5
+            ise=1.7f
+            ne=1.49
+            br=25
+            rb=20
+            rc=2
+            cje=3p
+            tf=0.55n
+            cjc=2p
+            xcjc=0.35
+            tr=8n
+            xtb=1.5
.model __Q7 NPN
+           is=6.7f
+           bf=350
+           vaf=120
+           ikf=0.3
+           ise=1f
+           ne=1.5
+           br=60
+           rb=15
+           rc=1.5
+           cje=2.5p
+           tf=0.42n
+           cjc=1.5p
+           xcjc=0.35
+           tr=10n
+           xtb=1.5
.model __Q6 NPN
+           is=6.7f
+           bf=350
+           vaf=120
+           ikf=0.3
+           ise=1f
+           ne=1.5
+           br=60
+           rb=15
+           rc=1.5
+           cje=2.5p
+           tf=0.42n
+           cjc=1.5p
+           xcjc=0.35
+           tr=10n
+           xtb=1.5
.model __Q4 NPN
+           is=6.7f
+           bf=350
+           vaf=120
+           ikf=0.3
+           ise=1f
+           ne=1.5
+           br=60
+           rb=15
+           rc=1.5
+           cje=2.5p
+           tf=0.42n
+           cjc=1.5p
+           xcjc=0.35
+           tr=10n
+           xtb=1.5
.model __Q8 PNP
+           is=1.9f
+           bf=300
+           vaf=120
+           ikf=0.5
+           ise=1.7f
+           ne=1.49
+           br=25
+           rb=20
+           rc=2
+           cje=3p
+           tf=0.55n
+           cjc=2p
+           xcjc=0.35
+           tr=8n
+           xtb=1.5
.model __Q12 NPN
+            is=6.7f
+            bf=350
+            vaf=120
+            ikf=0.3
+            ise=1f
+            ne=1.5
+            br=60
+            rb=15
+            rc=1.5
+            cje=2.5p
+            tf=0.42n
+            cjc=1.5p
+            xcjc=0.35
+            tr=10n
+            xtb=1.5
.model __Q9 PNP
+           is=1.9f
+           bf=300
+           vaf=120
+           ikf=0.5
+           ise=1.7f
+           ne=1.49
+           br=25
+           rb=20
+           rc=2
+           cje=3p
+           tf=0.55n
+           cjc=2p
+           xcjc=0.35
+           tr=8n
+           xtb=1.5
.model __Q1 NJF
+           vto=-0.7
+           beta=9m
+           lambda=0.006
+           rd=12
+           rs=13
+           cgs=10p
+           cgd=3p
+           pb=0.4
+           fc=0.5
.model __Q2 NJF
+           vto=-0.7
+           beta=9m
+           lambda=0.006
+           rd=12
+           rs=13
+           cgs=10p
+           cgd=3p
+           pb=0.4
+           fc=0.5
.model __Q3 NPN
+           is=6.7f
+           bf=350
+           vaf=120
+           ikf=0.3
+           ise=1f
+           ne=1.5
+           br=60
+           rb=15
+           rc=1.5
+           cje=2.5p
+           tf=0.42n
+           cjc=1.5p
+           xcjc=0.35
+           tr=10n
+           xtb=1.5
.model __Q11 NPN
+            is=6.7f
+            bf=350
+            vaf=120
+            ikf=0.3
+            ise=1f
+            ne=1.5
+            br=60
+            rb=15
+            rc=1.5
+            cje=2.5p
+            tf=0.42n
+            cjc=1.5p
+            xcjc=0.35
+            tr=10n
+            xtb=1.5
.model __Q13 PNP
+            is=1.9f
+            bf=300
+            vaf=120
+            ikf=0.5
+            ise=1.7f
+            ne=1.49
+            br=25
+            rb=20
+            rc=2
+            cje=3p
+            tf=0.55n
+            cjc=2p
+            xcjc=0.35
+            tr=8n
+            xtb=1.5
.model __Q10 PNP
+            is=1.9f
+            bf=300
+            vaf=120
+            ikf=0.5
+            ise=1.7f
+            ne=1.49
+            br=25
+            rb=20
+            rc=2
+            cje=3p
+            tf=0.55n
+            cjc=2p
+            xcjc=0.35
+            tr=8n
+            xtb=1.5
.model __Q5 PNP
+           is=1.9f
+           bf=300
+           vaf=120
+           ikf=0.5
+           ise=1.7f
+           ne=1.49
+           br=25
+           rb=20
+           rc=2
+           cje=3p
+           tf=0.55n
+           cjc=2p
+           xcjc=0.35
+           tr=8n
+           xtb=1.5
R7 Net-_Q16-C_ Net-_R7-Pad2_ 1.5k
Q16 Net-_Q16-C_ Net-_Q16-B_ Net-_Q16-E_ __Q16
R17 Net-_Q12-C_ Net-_Q12-B_ 1.1k
Q7 +15V Net-_Q12-C_ Net-_Q7-E_ __Q7
R10 Net-_Q7-E_ /OUT 2.2
Q6 +15V Net-_Q16-C_ Net-_Q12-C_ __Q6
Rv2 Net-_Q16-B_ -15V 10k
Rb1 +15V Net-_Q13-B_ 8.2k
C3 Net-_Q11-B_ Net-_Q16-C_ 12p
C5 GND Net-_Q13-B_ 100n
Q4 Net-_Q3-B_ Net-_Q3-B_ Net-_Q4-E_ __Q4
Q8 -15V Net-_Q12-E_ Net-_Q8-E_ __Q8
R9 Net-_Q12-E_ -15V 2.7k
Q12 Net-_Q12-C_ Net-_Q12-B_ Net-_Q12-E_ __Q12
C4 Net-_Q12-C_ Net-_Q12-E_ 100n
R11 Net-_Q8-E_ /OUT 2.2
R18 Net-_Q12-B_ Net-_Q12-E_ 1k
R8 Net-_R7-Pad2_ -15V 150
R2 Net-_Q3-E_ -15V 470
R3 Net-_Q4-E_ -15V 470
R1 Net-_Q3-B_ GND 14k
R16 +15V Net-_Q10-E_ 4.3k
Q9 Net-_Q1-D_ Net-_Q1-D_ Net-_Q10-E_ __Q9
R13 /IN+ Net-_Q2-G_ 1k
JQ1 Net-_Q1-D_ Net-_Q1-G_ Net-_Q1-S_ __Q1
R12 /IN- Net-_Q1-G_ 1k
C7 Net-_Q1-D_ GND 22p
Rb2 Net-_Q13-B_ -15V 33k
JQ2 Net-_Q11-B_ Net-_Q2-G_ Net-_Q2-S_ __Q2
* RT1 (1k trimmer, wiper at mid) replaced by two 500 ohm halves for ngspice
RT1a Net-_Q1-S_ Net-_Q3-C_ 500
RT1b Net-_Q3-C_ Net-_Q2-S_ 500
Q3 Net-_Q3-C_ Net-_Q3-B_ Net-_Q3-E_ __Q3
C2 +15V GND 100n
Q11 +15V Net-_Q11-B_ Net-_Q11-E_ __Q11
C1 +15V GND 100n
Q13 Net-_Q11-B_ Net-_Q13-B_ Net-_Q10-C_ __Q13
Q10 Net-_Q10-C_ Net-_Q1-D_ Net-_Q10-E_ __Q10
C6 +15V Net-_Q5-E_ 100n
Q5 Net-_Q16-E_ Net-_Q11-E_ Net-_Q5-E_ __Q5
Rv1 +15V Net-_Q16-B_ 7.5k
R6 +15V Net-_Q5-E_ 900
