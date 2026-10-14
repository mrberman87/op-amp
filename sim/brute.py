import subprocess,re,itertools,sys

def run_net(r16, rbx, r6, ryv, ryref):
    net=f"""find workable bias for v2
.include v2p.inc
RLEAK1 n_q1g 0 100M
RLEAK2 n_q2g 0 100M
RINM INM 0 1u
VSRC INP 0 DC 0
RL   OUT 0 10k
RBX n_x {rbx}
RY2 n_y {ryref} {ryv}
.control
op
set width=100
print v(inp) v(inm) v(out) v(n_q1d) v(n_x) v(n_y) v(n_q5c) v(n_b1) v(n_b2) vcc#branch
print @q5[ic] @q7[ic] @q8[ic]
.endc
.end"""
    open("_t.cir","w").write(net)
    p=subprocess.run(["ngspice","-b","_t.cir"],capture_output=True,text=True)
    out=p.stdout
    try:
        vals=re.search(r'v\(inp\) = (.+?)\nv\(inm\) = (.+?)\nv\(out\) = (.+?)\nv\(n_q1d\) = (.+?)\nv\(n_x\) = (.+?)\nv\(n_y\) = (.+?)\nv\(n_q5c\) = (.+?)\nv\(n_b1\) = (.+?)\nv\(n_b2\) = (.+?)\nv\(vcc#branch\) = (.+?)\n',out).groups()
        qs=re.findall(r'@q(\d)\[ic\] = (.+)',out)
        qdict=dict(qs)
        return dict(zip(["inp","inm","out","q1d","x","y","q5c","b1","b2","icc"],map(float,vals))), float(qdict.get("5","nan")), float(qdict.get("7","nan")), float(qdict.get("8","nan"))
    except Exception as e:
        return None,None,None,None

s=open("v2.inc").read()
s=s.replace("R16 VCC n_mire 4.3k","R16 VCC n_mire {R16v}")
s=s.replace("RBX n_x 0 1M","RBX n_x 0 {RBXv}")
s=s.replace("R6  VCC n_q5e 1.3k","R6  VCC n_q5e {R6v}")
s=s.replace(".param t=0.5",".param t=0.5\n.param R16v=22k\n.param RBXv=47k\n.param R6v=1.3k")
open("v2p.inc","w").write(s)

combo_space = [
    ("R16=4.3k", 4_300, "RBX=47k to 0", 47_000, 0, "R6=4.7k", 4_700),
    ("R16=4.3k", 4_300, "RBX=100k to 0", 100_000, 0, "R6=4.7k", 4_700),
    ("R16=22k", 22_000, "RBX=47k to 0", 47_000, 0, "R6=1.3k", 1_300),
    ("R16=22k", 22_000, "RBX=47k to 0", 47_000, 0, "R6=4.7k", 4_700),
    ("R16=22k", 22_000, "RBX=10k to +15", 10_000, "VCC", "R6=4.7k", 4_700),
    ("R16=22k", 22_000, "RBX=47k to +15", 47_000, "VCC", "R6=4.7k", 4_700),
    ("R16=100k", 100_000, "RBX=tenk to +15", 10_000, "VCC", "R6=4.7k", 4_700),
    ("R16=100k", 100_000, "RBX=47k to +15", 47_000, "VCC", "R6=4.7k", 4_700),
    ("R16=22k", 22_000, "RBX=22k to +15", 22_000, "VCC", "R6=10k", 10_000),
    ("R16=22k", 22_000, "RBX=100k to +15", 100_000, "VCC", "R6=10k", 10_000),
]

for c in combo_space:
    r16k,r16,rbxk,rbx,rbref,r6k,r6 = c
    d,q5,q7,q8 = run_net(r16,rbx,r6,100_000,0)
    if d is None:
        print(f"{r16k:9s} {rbxk:14s} {r6k:9s}: no converge")
        continue
    x=d["x"]; y=d["y"]; o=d["out"]; q1d=d["q1d"]; icc=-d["icc"]
    ok = abs(x)<14.5 and abs(o)<14.5
    flag = "" if (ok and x>1 and y>1) else "   <-- dead/sat"
    print(f"{r16k:9s} {rbxk:14s} {r6k:9s}: X={x:7.2f} Y={y:7.2f} q1d={q1d:6.2f} OUT={o:7.2f} Iq5={q5:8.1f}u Iq7={q7:8.1f}u Iq8={q8:8.1f}u Icc={icc:6.2f}mA{flag}")