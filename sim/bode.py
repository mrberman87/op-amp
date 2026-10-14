#!/usr/bin/env python3
"""Render a Bode plot (magnitude + phase) as a PNG from an ngspice wrdata file.

wrdata format is <freq> <re> <im> per line (complex response of one probe).

Usage:
    bode.py <data.dat> <out.png> "<title>" [ol|fol]

    ol  -> annotate open-loop Aol / GBW / phase margin; mark the 0 dB crossing
    fol -> annotate closed-loop DC gain / peaking / -3 dB point

Pillow-only (no matplotlib / no numpy needed).
"""
import sys
import math
from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BG = (255, 255, 255)
PLOT_BG = (252, 252, 253)
FG = (30, 30, 30)
AXIS = (90, 90, 90)
GRID = (222, 222, 226)
GRID_MINOR = (240, 240, 242)
MAG = (21, 90, 200)
PHA = (200, 70, 20)
ZERO = (205, 60, 60)
ACC = (0, 120, 60)
DASH = (130, 130, 130)


def load(fn):
    rows = []
    for line in open(fn):
        p = line.split()
        if len(p) < 3:
            continue
        try:
            f, re_, im = (float(x) for x in p[:3])
        except ValueError:
            continue
        if f > 0:
            rows.append((f, re_, im))
    rows.sort(key=lambda r: r[0])
    return rows


def to_bode(rows):
    f = [r[0] for r in rows]
    mag = [20.0 * math.log10(math.hypot(r[1], r[2])) for r in rows]
    raw = [math.degrees(math.atan2(r[2], r[1])) for r in rows]
    pha = [raw[0]]
    for v in raw[1:]:
        d = v - pha[-1]
        while d > 180:
            d -= 360
        while d < -180:
            d += 360
        pha.append(pha[-1] + d)
    return f, mag, pha


def fmt_freq(x):
    if x >= 1e9:
        return "%gG" % (x / 1e9)
    if x >= 1e6:
        return "%gM" % (x / 1e6)
    if x >= 1e3:
        return "%gk" % (x / 1e3)
    return "%g" % x


def nice_step(span, target):
    raw = span / max(target, 1)
    for s in (1, 2, 2.5, 5, 10, 15, 20, 25, 30, 45, 50, 100, 200, 250, 500, 1000):
        if s >= raw:
            return float(s)
    return raw


def log_ticks(lo, hi):
    out = []
    for e in range(int(math.floor(lo)) - 1, int(math.ceil(hi)) + 2):
        for m in (1, 2, 5):
            v = m * 10 ** e
            if lo - 1e-9 <= math.log10(v) <= hi + 1e-9:
                out.append(v)
    return out


class Panel:
    def __init__(self, box, title, ylabel, color):
        self.x0, self.y0, self.x1, self.y1 = box
        self.title = title
        self.ylabel = ylabel
        self.color = color
        self.f = self.v = []
        self.step = 1.0
        self.ymin = self.ymax = 0.0

    def set_data(self, f, v):
        self.f, self.v = f, v
        self.ymin = math.floor(min(v) / self.step) * self.step
        self.ymax = math.ceil(max(v) / self.step) * self.step
        if self.ymax - self.ymin < self.step:
            self.ymax = self.ymin + self.step

    def X(self, f):
        lo, hi = math.log10(self.f[0]), math.log10(self.f[-1])
        return self.x0 + (math.log10(f) - lo) / (hi - lo) * (self.x1 - self.x0)

    def Y(self, v):
        return self.y1 - (v - self.ymin) / (self.ymax - self.ymin) * (self.y1 - self.y0)

    def freq_of(self, level):
        for i in range(len(self.f) - 1):
            a, b = self.v[i], self.v[i + 1]
            if (a - level) * (b - level) <= 0 and a != b:
                t = (level - a) / (b - a)
                return 10 ** (math.log10(self.f[i])
                              + t * (math.log10(self.f[i + 1]) - math.log10(self.f[i])))
        return None

    def draw(self, d, font, fontb, mark_zero=False, marks=(), xlabels=True):
        x0, y0, x1, y1 = self.x0, self.y0, self.x1, self.y1
        lo, hi = math.log10(self.f[0]), math.log10(self.f[-1])
        d.rectangle([x0, y0, x1, y1], fill=PLOT_BG, outline=AXIS, width=1)

        for tv in log_ticks(lo, hi):
            lg = math.log10(tv)
            xx = x0 + (lg - lo) / (hi - lo) * (x1 - x0)
            major = abs(lg - round(lg)) < 1e-9
            d.line([(xx, y0), (xx, y1)], fill=GRID if major else GRID_MINOR, width=1)

        yv = self.ymin
        while yv <= self.ymax + 1e-6:
            yy = self.Y(yv)
            d.line([(x0, yy), (x1, yy)], fill=GRID_MINOR, width=1)
            d.text((x0 - 9, yy), "%g" % yv, font=font, fill=FG, anchor="rm")
            yv += self.step

        if mark_zero and self.ymin <= 0 <= self.ymax:
            d.line([(x0, self.Y(0)), (x1, self.Y(0))], fill=ZERO, width=1)

        for fx, label in marks:
            xx = self.X(fx)
            y = y0
            while y < y1:
                d.line([(xx, y), (xx, min(y + 7, y1))], fill=DASH, width=1)
                y += 13
            d.text((xx + 6, y0 + 6), label, font=font, fill=ACC, anchor="la")

        pts = [(self.X(f), self.Y(v)) for f, v in zip(self.f, self.v)]
        d.line(pts, fill=self.color, width=3, joint="curve")

        if xlabels:
            for tv in log_ticks(lo, hi):
                if abs(math.log10(tv) - round(math.log10(tv))) < 1e-9:
                    xx = self.X(tv)
                    d.line([(xx, y1), (xx, y1 + 6)], fill=AXIS, width=1)
                    d.text((xx, y1 + 10), fmt_freq(tv), font=font, fill=FG, anchor="ma")

        d.text((x0, y0 - 26), self.title, font=fontb, fill=FG, anchor="la")
        d.text((x0 - 64, (y0 + y1) / 2), self.ylabel, font=font, fill=self.color, anchor="mm")


def main():
    if len(sys.argv) < 4:
        sys.stderr.write(__doc__)
        sys.exit(2)
    data, out, title = sys.argv[1], sys.argv[2], sys.argv[3]
    kind = sys.argv[4] if len(sys.argv) > 4 else "ol"

    rows = load(data)
    f, mag, pha = to_bode(rows)

    W, H = 1400, 900
    L, R, T, B, GAP = 100, 40, 96, 74, 72
    panh = (H - T - B - GAP) // 2
    b1 = (L, T, W - R, T + panh)
    b2 = (L, T + panh + GAP, W - R, T + panh + GAP + panh)

    p1 = Panel(b1, "Magnitude", "Gain (dB)", MAG)
    p1.step = nice_step(max(mag) - min(mag), 8)
    p1.set_data(f, mag)
    p2 = Panel(b2, "Phase", "Phase (deg)", PHA)
    p2.step = nice_step(max(pha) - min(pha), 8)
    p2.set_data(f, pha)

    marks = []
    if kind == "ol":
        aol = mag[0]
        gbw = p1.freq_of(0.0)
        pm = None
        if gbw:
            marks = [(gbw, "0 dB  %sHz" % fmt_freq(gbw))]
            j = min(range(len(f)), key=lambda i: abs(math.log10(f[i]) - math.log10(gbw)))
            pm = 180 + pha[j]
            while pm > 180:
                pm -= 360
            while pm < -180:
                pm += 360
        note = "Aol = %.1f dB    GBW = %sHz" % (aol, fmt_freq(gbw) if gbw else "?")
        if pm is not None:
            note += "    PM = %.1f deg" % pm
    else:
        dc = mag[0]
        pk = max(mag)
        fp = f[mag.index(pk)]
        f3 = p1.freq_of(mag[0] - 3.0)
        note = ("DC gain = %.3f dB (%.4f V/V)    peaking = %+.2f dB @ %sHz"
                % (dc, 10 ** (dc / 20.0), max(mag) - mag[0], fmt_freq(fp)))
        if f3:
            note += "     -3 dB @ %sHz" % fmt_freq(f3)

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 20)
    fontb = ImageFont.truetype(FONTB, 22)
    fontt = ImageFont.truetype(FONTB, 30)

    p1.draw(d, font, fontb, mark_zero=(kind == "ol"), marks=marks, xlabels=False)
    p2.draw(d, font, fontb, xlabels=True)

    d.text((W / 2, 44), title, font=fontt, fill=FG, anchor="mm")
    d.text((W - R, b2[3] + 40), "Frequency (Hz)", font=font, fill=FG, anchor="ra")
    d.rectangle([L, H - 52, W - R, H - 14], fill=(238, 247, 240), outline=ACC, width=1)
    d.text((L + 14, (H - 58 + H - 14) / 2 + 2), note, font=fontb, fill=ACC, anchor="lm")
    img.save(out)
    print("wrote %s | %s" % (out, note))


if __name__ == "__main__":
    main()
