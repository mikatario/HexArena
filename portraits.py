# -*- coding: utf-8 -*-
"""ユニット・モンスター・コントローラーの「絵」（3Dモデルを1回だけ撮影して、画面表示用の画像にする）"""
import math

import pygame
from panda3d.core import (AmbientLight, DirectionalLight, FrameBufferProperties, LightRampAttrib, NodePath,
                          OrthographicLens, Texture, Vec4, AntialiasAttrib)

import models3d as MD

CELL = 128        # 1枚の大きさ（ピクセル）
COLS = 8
S = 1.65          # 1マスの大きさ（3D空間）

_cache = {}       # (種類, ID) -> pygame.Surface


def get(kind, key, size=None):
    s = _cache.get((kind, key))
    if s is None:
        return None
    if size and size != CELL:
        k = (kind, key, size)
        t = _cache.get(k)
        if t is None:
            t = pygame.transform.smoothscale(s, (size, size))
            _cache[k] = t
        return t
    return s


def build(base, units, creeps, controllers):
    """units/creeps/controllers: {id: info}。まとめて撮影してキャッシュに入れる"""
    for k in [k for k in _cache]:
        del _cache[k]
    entries = [("unit", k, v) for k, v in units.items()] + [("creep", k, v) for k, v in creeps.items()] + \
              [("ctrl", k, v) for k, v in controllers.items()]
    per = COLS * COLS
    for start in range(0, len(entries), per):
        try:
            _shoot(base, entries[start:start + per])
        except Exception:   # 撮影できない環境でもゲームは続ける（絵なしで表示）
            import traceback
            traceback.print_exc()
            return


def _shoot(base, entries):
    rows = max(1, math.ceil(len(entries) / COLS))
    w, h = COLS * CELL, rows * CELL
    tex = Texture("portraits")
    fbp = FrameBufferProperties()
    fbp.setRgbColor(True)
    fbp.setRgbaBits(8, 8, 8, 8)
    fbp.setDepthBits(24)
    buf = base.win.makeTextureBuffer("portraits", w, h, tex, True, fbp)
    if buf is None:
        return
    buf.setClearColor(Vec4(0, 0, 0, 0))
    buf.setSort(-100)
    scene = NodePath("portrait_scene")
    scene.setShaderAuto()
    scene.setAntialias(AntialiasAttrib.MMultisample)
    scene.setAttrib(LightRampAttrib.makeDoubleThreshold(0.12, 0.72, 0.5, 1.0))
    al = AmbientLight("a")
    al.setColor(Vec4(0.5, 0.5, 0.56, 1))
    scene.setLight(scene.attachNewNode(al))
    dl = DirectionalLight("d")
    dl.setColor(Vec4(0.85, 0.8, 0.75, 1))
    dn = scene.attachNewNode(dl)
    dn.setHpr(20, -35, 0)
    scene.setLight(dn)
    lens = OrthographicLens()
    lens.setFilmSize(COLS * S, rows * S)
    lens.setNearFar(-50, 50)
    cam = base.makeCamera(buf, lens=lens)
    cam.reparentTo(scene)
    cam.setPos(0, -20, 0)
    cam.lookAt(0, 0, 0)
    for i, (kind, key, info) in enumerate(entries):
        r, c = divmod(i, COLS)
        try:
            if kind == "ctrl":
                m = MD.make_controller(key, info, (80, 190, 255), 1.0, bare=True)
            else:
                m = MD.make_model(key, info, 1, (80, 190, 255), kind == "creep", bare=True)
        except Exception:
            continue
        hgt = max(0.8, m.height)
        s = min(1.2, 1.42 / hgt)
        m.root.reparentTo(scene)
        m.root.setScale(s)
        m.root.setHpr(200, 12, 0)
        cx = (c - (COLS - 1) / 2) * S
        cz = ((rows - 1) / 2 - r) * S
        m.root.setPos(cx, 0, cz - hgt * s * 0.5 - 0.05)
        if m.arm_r and not m.arm_r.isEmpty():
            m.arm_r.setP(25)
    base.graphicsEngine.renderFrame()
    base.graphicsEngine.renderFrame()
    img = tex.getRamImageAs("RGBA")
    if img is not None and len(img) >= w * h * 4:
        surf = pygame.image.frombuffer(bytes(img), (w, h), "RGBA")
        surf = pygame.transform.flip(surf, False, True).convert_alpha() if pygame.display.get_init() and \
            pygame.display.get_surface() else pygame.transform.flip(surf, False, True)
        for i, (kind, key, info) in enumerate(entries):
            r, c = divmod(i, COLS)
            sub = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
            sub.blit(surf, (0, 0), pygame.Rect(c * CELL, r * CELL, CELL, CELL))
            _cache[(kind, key)] = sub
    base.graphicsEngine.removeWindow(buf)
    cam.removeNode()
    scene.removeNode()
