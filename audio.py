# -*- coding: utf-8 -*-
"""BGM・効果音・ボイスの再生（pygame.mixer を使う）

音のファイル：
  assets/bgm/   title.wav planning.wav battle.wav win.wav lose.wav
  assets/se/    click buy sell reroll levelup starup hit cast skill item error place phase die（.wav）
  assets/voice/ announce_*.wav、ctrl_<コントローラーID>_pick.wav / _skill.wav
同じ名前のファイルを置き換えると、その音に差し替えられます（exeの隣に assets フォルダを作って置いてもOK）。
"""
import json
import os
import sys
import time

import pygame

_ok = False
_sounds = {}
_music = None
_voice_ch = None
_last = {}
SETTINGS = {"bgm": True, "se": True, "voice": True, "bgm_vol": 0.45, "se_vol": 0.7, "voice_vol": 0.9}


def _base_dirs():
    dirs = []
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(sys.executable))       # exeの隣の assets（差し替え用）
    dirs.append(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
    return dirs


def _find(rel):
    for d in _base_dirs():
        p = os.path.join(d, "assets", rel)
        if os.path.exists(p):
            return p
    return None


def _settings_path():
    d = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    return os.path.join(d, "hexarena_settings.json")


def load_settings():
    try:
        with open(_settings_path(), encoding="utf-8") as f:
            SETTINGS.update({k: v for k, v in json.load(f).items() if k in SETTINGS})
    except (OSError, ValueError):
        pass


def save_settings():
    try:
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(SETTINGS, f, ensure_ascii=False)
    except OSError:
        pass


def init():
    global _ok, _voice_ch
    load_settings()
    try:
        pygame.mixer.pre_init(44100, -16, 2, 1024)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(24)
        _voice_ch = pygame.mixer.Channel(23)
        pygame.mixer.set_reserved(1)
        _ok = True
    except pygame.error:
        _ok = False     # 音が出せない環境（スピーカーなし等）でもゲームは動く
    return _ok


def _sound(rel):
    s = _sounds.get(rel)
    if s is None and rel not in _sounds:
        p = _find(rel)
        try:
            s = pygame.mixer.Sound(p) if p else None
        except pygame.error:
            s = None
        _sounds[rel] = s
    return s


def se(name, gap=0.0):
    """効果音。gap 秒以内の連続再生は間引く"""
    if not _ok or not SETTINGS["se"]:
        return
    now = time.monotonic()
    if gap and now - _last.get(name, 0) < gap:
        return
    _last[name] = now
    s = _sound(os.path.join("se", name + ".wav"))
    if s:
        s.set_volume(SETTINGS["se_vol"])
        s.play()


def voice(name, fallback=None):
    if not _ok or not SETTINGS["voice"]:
        return
    s = _sound(os.path.join("voice", name + ".wav"))
    if s is None and fallback:
        s = _sound(os.path.join("voice", fallback + ".wav"))
    if s and _voice_ch is not None:
        s.set_volume(SETTINGS["voice_vol"])
        _voice_ch.play(s)


def music(name, loop=True):
    """BGMを切り替える（同じ曲なら何もしない）"""
    global _music
    if not _ok:
        return
    if name == _music and pygame.mixer.music.get_busy():
        return
    _music = name
    if not SETTINGS["bgm"] or name is None:
        pygame.mixer.music.stop()
        return
    p = _find(os.path.join("bgm", name + ".wav"))
    if not p:
        return
    try:
        pygame.mixer.music.load(p)
        pygame.mixer.music.set_volume(SETTINGS["bgm_vol"])
        pygame.mixer.music.play(-1 if loop else 0, fade_ms=600)
    except pygame.error:
        pass


def jingle(name):
    """勝ち負けの短い曲（効果音チャンネルで鳴らす）"""
    if not _ok or not SETTINGS["bgm"]:
        return
    s = _sound(os.path.join("bgm", name + ".wav"))
    if s:
        s.set_volume(min(1.0, SETTINGS["bgm_vol"] + 0.25))
        s.play()


def toggle(kind):
    SETTINGS[kind] = not SETTINGS[kind]
    if kind == "bgm" and _ok:
        if SETTINGS["bgm"]:
            name, globals()["_music"] = _music, None
            music(name)
        else:
            pygame.mixer.music.stop()
    save_settings()
    return SETTINGS[kind]


def toggle_all():
    on = not (SETTINGS["bgm"] or SETTINGS["se"] or SETTINGS["voice"])
    for k in ("bgm", "se", "voice"):
        if SETTINGS[k] != on:
            toggle(k)
    return on
