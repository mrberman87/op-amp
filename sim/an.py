import math,re,sys
def load(fn):
    txt=open(fn).read()
    p=re.compile(r'^\s*\d+\s+([0-9.eE+-]+)\s+([-0-9.eE+]+),\s+([-0-9.eE+]+)\s*$',re.M)
    rows=[]
    for m in p.finditer(txt):
        f,re_,im=map(float,m.groups())
        rows.append((f,math.hypot(re_,im),math.atan2(im,re_)))
    rows.sort()
    return rows
def phase_unwrap(ph):
    out=[ph[0]]
    for i in range(1,len(ph)):
        d=ph[i]-ph[i-1]
        while d>math.pi: d-=2*math.pi
        while d<-math.pi: d+=2*math.pi
        out.append(out[-1]+d)
    return out
def report(fn):
    rows=load(fn)
    ph=phase_unwrap([r[2] for r in rows])
    gdb=[20*math.log10(r[1]) for r in rows]
    f=[r[0] for r in rows]
    crossings=[]
    for i in range(len(rows)-1):
        if gdb[i]>=0>=gdb[i+1]:
            t=(0-gdb[i])/(gdb[i+1]-gdb[i])
            fx=10**(math.log10(f[i])+(math.log10(f[i+1])-math.log10(f[i]))*t)
            phx=math.degrees(ph[i]+(ph[i+1]-ph[i])*t)
            crossings.append((fx,180+phx))
    aol=gdb[0]
    # dominant pole freq (~where gain drops 3dB)
    fp=None
    for i in range(len(f)):
        if gdb[i]<=aol-3: fp=f[i]; break
    return aol,fp,crossings,f,gdb,ph
for fn in sys.argv[1:]:
    aol,fp,cs,f,gdb,ph=report(fn)
    s=f"{fn:26s} Aol={aol:6.1f}dB fp~{fp/1e3 if fp else 0:8.2f}kHz "
    for fx,pm in cs:
        s+=f"| 0dB@{fx/1e6:6.2f}MHz PM={pm:+6.1f} "
    print(s)
