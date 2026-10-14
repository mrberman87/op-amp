* Open-loop bench: unity-gain DC feedback via huge L, AC drive at IN+
RLEAK1 n_q1g 0 100M
RLEAK2 n_q2g 0 100M
RY     n_y  0 100k
VSRC INP 0 DC 0 AC 1
LFB  OUT INM 1e6
RL   OUT 0 10k
CL   OUT 0 10p