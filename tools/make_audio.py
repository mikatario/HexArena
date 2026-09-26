# -*- coding: utf-8 -*-
"""BGM と効果音をプログラムで作曲・合成して assets/bgm, assets/se に WAV で書き出す（開発用。numpy が必要）

  python tools/make_audio.py
"""
import os
import wave

import numpy as np

SR = 22050
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
rng = np.random.default_rng(7)


def f(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def env(n, a=0.005, d=0.1, s=0.6, r=0.1, total=None):
    t = np.arange(n) / SR
    total = total or n / SR
    e = np.ones(n)
    e = np.where(t < a, t / max(a, 1e-4), e)
    dd = (t >= a) & (t < a + d)
    e = np.where(dd, 1 - (1 - s) * (t - a) / max(d, 1e-4), e)
    e = np.where(t >= a + d, s, e)
    rel = t > total - r
    e = np.where(rel, e * np.clip((total - t) / max(r, 1e-4), 0, 1), e)
    return e


def lowpass(x, k):
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):   # 1次のローパス
        acc += k * (x[i] - acc)
        y[i] = acc
    return y


def lp_fast(x, k):
    """ブロック処理の簡易ローパス（移動平均の重ね掛け）"""
    w = max(1, int(1 / max(k, 1e-3)))
    ker = np.ones(w) / w
    return np.convolve(np.convolve(x, ker, "same"), ker, "same")


def osc(kind, freq, n, detune=0.0):
    t = np.arange(n) / SR
    ph = (freq * (1 + detune)) * t
    if kind == "sine":
        return np.sin(2 * np.pi * ph)
    if kind == "tri":
        return 2 * np.abs(2 * (ph % 1) - 1) - 1
    if kind == "saw":
        return 2 * (ph % 1) - 1
    if kind == "square":
        return np.where((ph % 1) < 0.5, 1.0, -1.0)
    if kind == "pulse":
        return np.where((ph % 1) < 0.25, 1.0, -1.0)
    raise ValueError(kind)


def pluck(freq, dur, bright=0.35):
    n = int(dur * SR)
    x = 0.6 * osc("square", freq, n) + 0.4 * osc("saw", freq, n, 0.003)
    x = lp_fast(x, bright)
    return x * env(n, 0.003, dur * 0.6, 0.15, min(0.08, dur * 0.3))


def pad(freqs, dur):
    n = int(dur * SR)
    x = np.zeros(n)
    for fr in freqs:
        x += osc("saw", fr, n, 0.004) + osc("saw", fr, n, -0.004)
    x = lp_fast(x / (2 * len(freqs)), 0.08)
    return x * env(n, dur * 0.25, 0.1, 0.9, dur * 0.3)


def bass(freq, dur, kind="tri"):
    n = int(dur * SR)
    x = osc(kind, freq, n) * 0.8 + 0.3 * osc("sine", freq / 2, n)
    if kind != "tri":
        x = lp_fast(x, 0.12)
    return x * env(n, 0.004, dur * 0.4, 0.55, 0.03)


def lead(freq, dur, vib=True):
    n = int(dur * SR)
    t = np.arange(n) / SR
    wob = 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.15, 0, 1) if vib else np.zeros(n)
    fm = freq * (1 + wob)
    ph = np.cumsum(fm) / SR
    x = np.where((ph % 1) < 0.5, 1.0, -1.0) * 0.5 + 0.5 * np.sin(2 * np.pi * ph)
    x = lp_fast(x, 0.3)
    return x * env(n, 0.01, 0.12, 0.7, 0.06)


def kick(dur=0.35):
    n = int(dur * SR)
    t = np.arange(n) / SR
    fr = 45 + 110 * np.exp(-t * 28)
    ph = np.cumsum(fr) / SR
    return np.sin(2 * np.pi * ph) * np.exp(-t * 9)


def snare(dur=0.22):
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - lp_fast(noise, 0.2)
    tone = np.sin(2 * np.pi * 190 * t)
    return (0.75 * noise + 0.35 * tone) * np.exp(-t * 20)


def hat(dur=0.06, open_=False):
    n = int((0.25 if open_ else dur) * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - lp_fast(noise, 0.5)
    return noise * np.exp(-t * (12 if open_ else 60)) * 0.5


def mix_in(buf, x, start, gain=1.0):
    s = int(start * SR)
    e = min(len(buf), s + len(x))
    if e > s:
        buf[s:e] += x[:e - s] * gain


CHORD = {  # 根音（MIDI）と構成音
    "C": (48, [0, 4, 7]), "Dm": (50, [0, 3, 7]), "Em": (52, [0, 3, 7]), "F": (53, [0, 4, 7]),
    "G": (55, [0, 4, 7]), "Am": (57, [0, 3, 7]), "E": (52, [0, 4, 7]), "D": (50, [0, 4, 7]),
    "B7": (47, [0, 4, 7, 10]), "Bm": (47, [0, 3, 7]),
}


def song(bpm, prog, bars_per_chord, style, melody_seed, loops=2):
    beat = 60 / bpm
    bar = beat * 4
    total_bars = len(prog) * bars_per_chord * loops
    n = int(total_bars * bar * SR) + SR
    L = np.zeros(n)
    r = np.random.default_rng(melody_seed)
    bi = 0
    mel_prev = 72
    for lp in range(loops):
        for ch in prog:
            root, iv = CHORD[ch]
            tones = [root + k for k in iv]
            for b in range(bars_per_chord):
                t0 = bi * bar
                # パッド
                if style in ("title", "plan"):
                    mix_in(L, pad([f(x + 12) for x in tones], bar), t0, 0.35 if style == "title" else 0.22)
                # アルペジオ
                steps = 8 if style != "battle" else 16
                for s in range(steps):
                    nt = tones[s % len(tones)] + 24 + (12 if (s // len(tones)) % 2 and style == "title" else 0)
                    if style == "battle":
                        nt = tones[[0, 1, 2, 1][s % 4]] + 24
                    dur = bar / steps
                    mix_in(L, pluck(f(nt), dur * 0.95, 0.25 if style == "title" else 0.4), t0 + s * dur,
                           0.18 if style != "battle" else 0.12)
                # ベース
                if style == "title":
                    for q in (0, 2):
                        mix_in(L, bass(f(root - 12), beat * 1.9), t0 + q * beat, 0.5)
                elif style == "plan":
                    for q in range(8):
                        nt = root - 12 + (7 if q % 4 == 3 else 0) + (12 if q % 2 else 0)
                        mix_in(L, bass(f(nt), beat * 0.45), t0 + q * beat / 2, 0.42)
                else:
                    for q in range(8):
                        mix_in(L, bass(f(root - 12 + (12 if q % 2 else 0)), beat * 0.45, "square"), t0 + q * beat / 2, 0.36)
                # ドラム
                if style == "title":
                    mix_in(L, kick(), t0, 0.5)
                    mix_in(L, kick(), t0 + 2.5 * beat, 0.35)
                    mix_in(L, hat(open_=True), t0 + 2 * beat, 0.12)
                elif style == "plan":
                    for q in range(4):
                        mix_in(L, kick(), t0 + q * beat, 0.45 if q % 2 == 0 else 0.0)
                        if q % 2 == 1:
                            mix_in(L, snare(), t0 + q * beat, 0.28)
                    for q in range(8):
                        mix_in(L, hat(), t0 + q * beat / 2, 0.18)
                else:
                    for q in range(4):
                        mix_in(L, kick(), t0 + q * beat, 0.6)
                        if q % 2 == 1:
                            mix_in(L, snare(), t0 + q * beat, 0.42)
                    for q in range(16):
                        mix_in(L, hat(), t0 + q * beat / 4, 0.14 if q % 2 else 0.2)
                    if (bi % 4) == 3:
                        for q in range(4):
                            mix_in(L, snare(0.12), t0 + 3 * beat + q * beat / 4, 0.25)
                # メロディ（2周目以降／タイトルは後半）
                if lp >= 1 or style == "battle":
                    rhythm = {"title": [2, 1, 1, 2, 2], "plan": [1, 0.5, 0.5, 1, 1], "battle": [0.5, 0.5, 1, 0.5, 0.5, 1]}[style]
                    tt = 0.0
                    k = 0
                    while tt < 4 - 1e-6:
                        d = rhythm[k % len(rhythm)]
                        d = min(d, 4 - tt)
                        cands = [x + 24 for x in tones] + [x + 36 for x in tones]
                        cands.sort(key=lambda x: abs(x - mel_prev) + r.random() * 4)
                        nt = cands[0] if r.random() < 0.7 else cands[1]
                        mel_prev = nt
                        if r.random() > 0.12:
                            mix_in(L, lead(f(nt + (0 if style != "title" else 0)), d * beat * 0.92), t0 + tt * beat,
                                   0.16 if style != "battle" else 0.13)
                        tt += d
                        k += 1
                bi += 1
    L = L[:int(total_bars * bar * SR)]
    L = np.tanh(L * 1.1)
    L = L / (np.max(np.abs(L)) + 1e-9) * 0.8
    return L


def jingle(notes, step, tail, kind="win"):
    n = int((len(notes) * step + tail) * SR)
    L = np.zeros(n)
    for i, nt in enumerate(notes):
        mix_in(L, lead(f(nt), step * 1.4 if i < len(notes) - 1 else tail, False), i * step, 0.4)
        mix_in(L, pluck(f(nt - 12), step, 0.4), i * step, 0.25)
    last = notes[-1]
    third = 4 if kind == "win" else 3
    mix_in(L, pad([f(last - 12), f(last - 12 + third), f(last - 5)], tail), len(notes) * step - step, 0.5)
    L = np.tanh(L * 1.2)
    return L / (np.max(np.abs(L)) + 1e-9) * 0.8


def se_sweep(f0, f1, dur, kind="square", decay=10):
    n = int(dur * SR)
    t = np.arange(n) / SR
    fr = f0 * (f1 / f0) ** (t / dur)
    ph = np.cumsum(fr) / SR
    x = np.where((ph % 1) < 0.5, 1.0, -1.0) if kind == "square" else np.sin(2 * np.pi * ph)
    return x * np.exp(-t * decay)


def se_notes(notes, step, kind="sine", tail=0.2):
    n = int((len(notes) * step + tail) * SR)
    L = np.zeros(n)
    for i, nt in enumerate(notes):
        m = int((step + tail) * SR)
        t = np.arange(m) / SR
        x = osc(kind, f(nt), m) * np.exp(-t * 9)
        mix_in(L, x, i * step, 0.6)
    return L


def se_noise(dur, decay, hp=True):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    if hp:
        x = x - lp_fast(x, 0.3)
    return x * np.exp(-t * decay)


def write(path, x, sr=SR):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    x = np.clip(x, -1, 1)
    data = (x * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data)
    print("wrote", os.path.relpath(path, ROOT), round(len(x) / sr, 1), "s")


def norm(x, peak=0.8):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def main():
    write(os.path.join(ROOT, "bgm", "title.wav"),
          song(84, ["Am", "F", "C", "G", "Am", "F", "G", "E"], 1, "title", 3, loops=2))
    write(os.path.join(ROOT, "bgm", "planning.wav"),
          song(104, ["C", "G", "Am", "F"], 2, "plan", 5, loops=2))
    write(os.path.join(ROOT, "bgm", "battle.wav"),
          song(144, ["Em", "C", "D", "B7"], 2, "battle", 11, loops=2))
    write(os.path.join(ROOT, "bgm", "win.wav"), jingle([72, 76, 79, 84], 0.12, 1.2, "win"))
    write(os.path.join(ROOT, "bgm", "lose.wav"), jingle([76, 72, 69, 64], 0.2, 1.2, "lose"))
    se = os.path.join(ROOT, "se")
    write(os.path.join(se, "click.wav"), norm(se_sweep(900, 700, 0.05, "sine", 60), 0.5))
    write(os.path.join(se, "buy.wav"), norm(se_notes([88, 93], 0.06, "square", 0.12), 0.45))
    write(os.path.join(se, "sell.wav"), norm(se_notes([81, 76], 0.07, "square", 0.1), 0.45))
    write(os.path.join(se, "reroll.wav"), norm(se_noise(0.25, 12) * 0.5 + se_sweep(300, 1200, 0.25, "sine", 6) * 0.3, 0.5))
    write(os.path.join(se, "levelup.wav"), norm(se_notes([72, 76, 79, 84, 88], 0.06, "square", 0.25), 0.5))
    write(os.path.join(se, "starup.wav"), norm(se_notes([84, 88, 91, 96, 100, 103], 0.04, "sine", 0.35), 0.55))
    write(os.path.join(se, "hit.wav"), norm(se_noise(0.08, 45, False) * 0.6 + se_sweep(220, 80, 0.08, "sine", 30), 0.4))
    write(os.path.join(se, "cast.wav"), norm(se_sweep(400, 1600, 0.3, "square", 8) * 0.5 + se_noise(0.3, 10) * 0.3, 0.45))
    sk = se_notes([67, 74, 79, 86, 91], 0.05, "sine", 0.6)
    sk[:int(0.5 * SR)] += se_noise(0.5, 6) * 0.2
    write(os.path.join(se, "skill.wav"), norm(sk, 0.6))
    write(os.path.join(se, "item.wav"), norm(se_notes([79, 83, 86, 91], 0.07, "tri", 0.4), 0.55))
    write(os.path.join(se, "error.wav"), norm(se_sweep(160, 140, 0.18, "square", 8), 0.35))
    write(os.path.join(se, "place.wav"), norm(se_sweep(300, 160, 0.07, "sine", 40) + se_noise(0.07, 60) * 0.2, 0.45))
    write(os.path.join(se, "phase.wav"), norm(se_notes([76, 83], 0.1, "tri", 0.4), 0.5))
    write(os.path.join(se, "die.wav"), norm(se_sweep(500, 90, 0.35, "square", 7), 0.35))


if __name__ == "__main__":
    main()
