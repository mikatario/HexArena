# -*- coding: utf-8 -*-
"""3Dの盤面・闘技場・カメラ・ユニットの表示と演出"""
import math
import random

from panda3d.core import (AmbientLight, DirectionalLight, NodePath, Point2, Point3, PointLight, Vec3, Vec4,
                          TransparencyAttrib, AntialiasAttrib)

import models3d as MD
from models3d import MB, M, box, cyl, sphere, ring, hex_prism, rgb, shade, mix

SQ3 = math.sqrt(3)
TILE_R = 1.0
OWN_RGB = (80, 190, 255)
ENEMY_RGB = (240, 90, 90)
SCOUT_RGB = (200, 170, 255)
CAM_FOV = 50      # 横方向の画角
CAM_PITCH = 50    # 見下ろす角度
CAM_DIST = 27.2   # カメラまでの距離
CAM_TY = -3.35    # カメラが見る位置（手前寄り）
BENCH_Y = -7.35   # ベンチの位置


def cell_world(r, c):
    """盤面の (行, 列) → 3D座標。行7が手前（自分側）"""
    return ((c + 0.5 * (r & 1) - 3.25) * SQ3 * TILE_R, (3.5 - r) * 1.5 * TILE_R)


def bench_world(i):
    return ((i - 4) * 1.55, BENCH_Y)


class Actor:
    """画面に出ているユニット1体"""

    def __init__(self, world, key, uid, info, star, team_rgb, creep):
        self.world = world
        self.key = key
        self.sig = (uid, star, team_rgb)
        self.model = MD.make_model(uid, info, star, team_rgb, creep)
        self.np = self.model.root
        self.np.reparentTo(world.units_root)
        self.x = self.y = 0.0
        self.heading = 0.0
        self.phase = random.random() * 6.28
        self.t_attack = -9.0
        self.t_cast = -9.0
        self.t_hit = -9.0
        self.dead_t = None
        self.hop = 0.0
        self.lift = 0.0
        self.dim = False
        self.float = self.model.kind in MD.FLOAT_LOOKS
        self.seen = True
        self.shield = None

    def place(self, x, y, heading=None, hop=0.0, lift=0.0):
        self.x, self.y = x, y
        if heading is not None:
            self.heading = heading
        self.hop = hop
        self.lift = lift

    def set_dim(self, dim):
        if dim != self.dim:
            self.dim = dim
            if dim:
                self.np.setColorScale(0.55, 0.55, 0.65, 0.75)
                self.np.setTransparency(TransparencyAttrib.MAlpha)
            else:
                self.np.clearColorScale()

    def set_shield(self, on):
        if on and self.shield is None:
            self.shield = self.np.attachNewNode(self.world._orb_node((220, 225, 255), 0.62))
            self.shield.setPos(0, 0, self.model.height * 0.45)
            self.shield.setScale(1, 1, 1.25)
            self.shield.setLightOff(1)
            self.shield.setShaderOff(1)
            self.shield.setTransparency(TransparencyAttrib.MAlpha)
            self.shield.setAlphaScale(0.22)
            self.shield.setDepthWrite(False)
            self.shield.setBin("fixed", 15)
        elif not on and self.shield is not None:
            self.shield.removeNode()
            self.shield = None

    def revive(self):
        self.dead_t = None
        self.np.setScale(1)
        self.np.show()

    def head_pos(self):
        return (self.x, self.y, self.model.height + self.lift + self.hop)

    def update(self, now):
        z = self.hop + self.lift
        if self.float:
            z += 0.12 + 0.06 * math.sin(now * 2.2 + self.phase)
        self.np.setPos(self.x, self.y, z)
        self.np.setH(self.heading)
        body = self.model.body
        bob = 0.025 * math.sin(now * 3.0 + self.phase)
        lunge = 0.0
        swing = 20.0 + 6 * math.sin(now * 2.0 + self.phase)
        a = now - self.t_attack
        if 0 <= a < 0.3:
            k = math.sin(a / 0.3 * math.pi)
            lunge = 0.22 * k
            swing = 20 + 85 * k
        c = now - self.t_cast
        spin = 0.0
        if 0 <= c < 0.45:
            k = c / 0.45
            bob += 0.35 * math.sin(k * math.pi)
            spin = 360 * k
            swing = 150 * math.sin(k * math.pi)
        body.setPos(0, lunge, 0.06 + bob)
        body.setH(spin)
        if self.model.arm_r and not self.model.arm_r.isEmpty():
            self.model.arm_r.setP(swing)
        if self.model.arm_l and not self.model.arm_l.isEmpty():
            self.model.arm_l.setP(15 + 5 * math.sin(now * 2.0 + self.phase + 1))
        h = now - self.t_hit
        if not self.dim:
            if 0 <= h < 0.12:
                self.np.setColorScale(1.6, 0.7, 0.7, 1)
            elif self.dead_t is None:
                self.np.clearColorScale()
        if self.dead_t is not None:
            d = now - self.dead_t
            s = max(0.001, 1 - d / 0.5)
            self.np.setScale(s)
            self.np.setZ(z - d * 0.6)
            if d > 0.5:
                self.np.hide()

    def destroy(self):
        self.np.removeNode()


class World:
    def __init__(self, base):
        self.base = base
        self.render = base.render
        self.now = 0.0
        base.setBackgroundColor(0.06, 0.07, 0.11, 1)
        base.disableMouse()
        self.render.setAntialias(AntialiasAttrib.MMultisample)
        self._lights()
        self._sky()
        self._arena()
        self._board()
        self.units_root = self.render.attachNewNode("units")
        self.fx_root = self.render.attachNewNode("fx")
        self.fx_root.setLightOff(1)
        self.fx_root.setShaderOff(1)
        self.fx_root.setTransparency(TransparencyAttrib.MAlpha)
        self.fx_root.setDepthWrite(False)
        self.fx_root.setBin("fixed", 20)
        self.actors = {}
        self.fx = []
        self._fx_cache = {}
        # カメラ（右ドラッグで回す、ホイールで寄る）
        self.cam_yaw = 0.0
        self.cam_pitch = CAM_PITCH
        self.cam_dist = CAM_DIST
        self.cam_target = Vec3(0, CAM_TY, 0)
        self.auto_orbit = False
        base.camLens.setFov(CAM_FOV)
        base.camLens.setNearFar(0.5, 200)
        self.update_camera()

    # ---------- 作成 ----------
    def _lights(self):
        r = self.render
        al = AmbientLight("amb")
        al.setColor(Vec4(0.42, 0.44, 0.52, 1))
        r.setLight(r.attachNewNode(al))
        dl = DirectionalLight("sun")
        dl.setColor(Vec4(0.95, 0.88, 0.78, 1))
        self.sun = r.attachNewNode(dl)
        self.sun.setHpr(35, -58, 0)
        try:
            dl.setShadowCaster(True, 2048, 2048)
            lens = dl.getLens()
            lens.setFilmSize(34, 34)
            lens.setNearFar(-40, 40)
        except Exception:
            pass
        r.setLight(self.sun)
        fill = DirectionalLight("fill")
        fill.setColor(Vec4(0.18, 0.22, 0.35, 1))
        fn = r.attachNewNode(fill)
        fn.setHpr(-140, -25, 0)
        r.setLight(fn)
        r.setShaderAuto()

    def _sky(self):
        mb = MB()
        seg, rings = 24, 10
        rad = 90
        grid = []
        for i in range(rings + 1):
            th = math.pi * i / rings
            k = i / rings
            col = mix(rgb(10, 12, 24), rgb(40, 52, 88), min(1, k * 1.6)) if k < 0.62 else mix(rgb(40, 52, 88), rgb(14, 14, 20), (k - 0.62) / 0.38)
            row = []
            for s in range(seg + 1):
                a = 2 * math.pi * s / seg
                p = (math.sin(th) * math.cos(a) * rad, math.sin(th) * math.sin(a) * rad, math.cos(th) * rad)
                row.append(mb.vert(M(), p, (-p[0], -p[1], -p[2]), col))
            grid.append(row)
        for i in range(rings):
            for s in range(seg):
                mb.quad(grid[i][s], grid[i + 1][s], grid[i + 1][s + 1], grid[i][s + 1])
        sky = self.render.attachNewNode(mb.node("sky"))
        sky.setLightOff(1)
        sky.setShaderOff(1)
        sky.setTwoSided(True)
        sky.setBin("background", 0)
        sky.setDepthWrite(False)
        # 星
        mb = MB()
        rnd = random.Random(7)
        for _ in range(160):
            a = rnd.random() * 6.283
            e = rnd.uniform(0.15, 1.3)
            d = 80
            p = (math.cos(e) * math.cos(a) * d, math.cos(e) * math.sin(a) * d, math.sin(e) * d)
            s = rnd.uniform(0.15, 0.35)
            box(mb, M(p), s, s, s, rgb(220, 225, 255))
        st = self.render.attachNewNode(mb.node("stars"))
        st.setLightOff(1)
        st.setShaderOff(1)
        st.setBin("background", 1)
        st.setDepthWrite(False)

    def _arena(self):
        mb = MB()
        stone = rgb(58, 60, 72)
        dark = rgb(34, 35, 44)
        # 土台（大きな六角形の石舞台）
        hex_prism(mb, M((0, -1.2, -0.22)), 11.5, 1.2, rgb(52, 54, 66), dark)
        hex_prism(mb, M((0, -1.2, -1.42), (30, 0, 0)), 13.5, 1.0, rgb(40, 42, 52), rgb(26, 27, 34))
        # 地面
        cyl(mb, M((0, 0, -2.6)), 60, 60, 0.2, rgb(18, 20, 28), seg=32)
        # 柱と灯り
        glow = MB()
        for k in range(6):
            a = math.radians(30 + 60 * k)
            x, y = 12.3 * math.cos(a), 12.3 * math.sin(a) - 1.2
            cyl(mb, M((x, y, -1.4)), 0.55, 0.45, 4.2, stone, seg=10)
            box(mb, M((x, y, 2.9)), 1.3, 1.3, 0.35, shade(stone, 1.2))
            cyl(mb, M((x, y, 3.05)), 0.35, 0.5, 0.4, dark, seg=10)
            sphere(glow, M((x, y, 3.65)), 0.32, rgb(255, 180, 90), seg=10, rings=6)
        # 旗（青＝自分側、赤＝相手側）
        for sx in (-1, 1):
            for side, col in ((-1, rgb(50, 120, 210)), (1, rgb(200, 60, 60))):
                x, y = sx * 7.4, side * 6.5 - 1.2 + (0 if side > 0 else 0.0)
                if side < 0:
                    y = -11.0
                cyl(mb, M((x, y, -0.2)), 0.07, 0.07, 3.2, rgb(140, 120, 90), seg=6)
                box(mb, M((x + sx * -0.45, y, 2.55)), 0.9, 0.05, 1.1, col)
        n = self.render.attachNewNode(mb.node("arena"))
        g = self.render.attachNewNode(glow.node("lamps"))
        g.setLightOff(1)
        g.setShaderOff(1)
        for k in (0, 2, 4):
            a = math.radians(30 + 60 * k)
            pl = PointLight("lamp")
            pl.setColor(Vec4(0.5, 0.33, 0.16, 1))
            pl.setAttenuation(Vec3(1, 0.0, 0.012))
            pn = self.render.attachNewNode(pl)
            pn.setPos(12.3 * math.cos(a), 12.3 * math.sin(a) - 1.2, 3.8)
            self.render.setLight(pn)

    def _board(self):
        self.tiles = {}
        root = self.render.attachNewNode("board")
        for r in range(8):
            for c in range(7):
                mb = MB()
                own = r >= 4
                top = rgb(62, 80, 118) if own else rgb(64, 60, 70)
                if (r + c) % 2:
                    top = shade(top, 1.08)
                hex_prism(mb, M(), TILE_R * 0.93, 0.28, top, shade(top, 0.55))
                n =root.attachNewNode(mb.node(f"t{r}{c}"))
                x, y = cell_world(r, c)
                n.setPos(x, y, 0)
                self.tiles[(r, c)] = n
        # 真ん中の線
        mb = MB()
        box(mb, M((0, 0, 0.005)), 13.5, 0.06, 0.01, rgb(200, 210, 240))
        ln = root.attachNewNode(mb.node("mid"))
        ln.setLightOff(1)
        ln.setShaderOff(1)
        # ベンチ
        self.bench_pads = []
        for i in range(9):
            mb = MB()
            box(mb, M((0, 0, -0.14)), 1.38, 1.38, 0.28, rgb(52, 58, 78))
            box(mb, M((0, 0, 0.005)), 1.26, 1.26, 0.01, rgb(66, 74, 100))
            n = root.attachNewNode(mb.node(f"b{i}"))
            x, y = bench_world(i)
            n.setPos(x, y, 0)
            self.bench_pads.append(n)
        mb = MB()
        box(mb, M((0, BENCH_Y, -0.3)), 14.6, 1.75, 0.3, rgb(38, 42, 56))
        root.attachNewNode(mb.node("bench_base"))

    # ---------- カメラ ----------
    def update_camera(self):
        yaw = math.radians(self.cam_yaw)
        pit = math.radians(self.cam_pitch)
        d = self.cam_dist
        t = self.cam_target
        x = t.x + d * math.cos(pit) * math.sin(yaw)
        y = t.y - d * math.cos(pit) * math.cos(yaw)
        z = t.z + d * math.sin(pit)
        self.base.cam.setPos(x, y, z)
        self.base.cam.lookAt(Point3(t.x, t.y, t.z))

    def rotate_camera(self, dx, dy):
        self.cam_yaw = max(-60, min(60, self.cam_yaw + dx * 0.25))
        self.cam_pitch = max(22, min(75, self.cam_pitch + dy * 0.2))
        self.update_camera()

    def zoom(self, k):
        self.cam_dist = max(12, min(30, self.cam_dist * k))
        self.update_camera()

    def reset_camera(self):
        self.cam_yaw, self.cam_pitch, self.cam_dist = 0.0, CAM_PITCH, CAM_DIST
        self.update_camera()

    # ---------- 座標変換 ----------
    def ground_at(self, ndc, z=0.0):
        """画面上の位置（-1〜1）→ 地面(z)との交点"""
        near, far = Point3(), Point3()
        if not self.base.camLens.extrude(Point2(ndc[0], ndc[1]), near, far):
            return None
        near = self.render.getRelativePoint(self.base.cam, near)
        far = self.render.getRelativePoint(self.base.cam, far)
        dz = far.z - near.z
        if abs(dz) < 1e-6:
            return None
        k = (z - near.z) / dz
        if k < 0:
            return None
        return (near.x + (far.x - near.x) * k, near.y + (far.y - near.y) * k)

    def project(self, p):
        """3D座標 → 画面上の位置（-1〜1）。後ろなら None"""
        cp = self.base.cam.getRelativePoint(self.render, Point3(*p))
        out = Point2()
        if cp.y <= 0 or not self.base.camLens.project(cp, out):
            if cp.y <= 0:
                return None
        return (out.x, out.y)

    def cell_at(self, g):
        if g is None:
            return None
        best, bd = None, 0.95
        for r in range(8):
            for c in range(7):
                x, y = cell_world(r, c)
                d = math.hypot(g[0] - x, g[1] - y)
                if d < bd:
                    bd, best = d, (r, c)
        return best

    def bench_at(self, g):
        if g is None:
            return None
        for i in range(9):
            x, y = bench_world(i)
            if abs(g[0] - x) < 0.77 and abs(g[1] - y) < 0.8:
                return i
        return None

    def highlight(self, cells=(), bench=()):
        for key, n in self.tiles.items():
            if key in cells:
                n.setColorScale(1.5, 1.6, 1.9, 1)
            else:
                n.clearColorScale()
        for i, n in enumerate(self.bench_pads):
            if i in bench:
                n.setColorScale(1.5, 1.6, 1.9, 1)
            else:
                n.clearColorScale()

    # ---------- ユニット ----------
    def begin_sync(self):
        for a in self.actors.values():
            a.seen = False

    def actor(self, key, uid, info, star, team_rgb, creep=False):
        a = self.actors.get(key)
        sig = (uid, star, team_rgb)
        if a is not None and a.sig != sig:
            a.destroy()
            a = None
        if a is None:
            a = Actor(self, key, uid, info, star, team_rgb, creep)
            self.actors[key] = a
        a.seen = True
        return a

    def end_sync(self):
        for k in [k for k, a in self.actors.items() if not a.seen]:
            self.actors[k].destroy()
            del self.actors[k]

    def clear_units(self):
        for a in self.actors.values():
            a.destroy()
        self.actors = {}

    # ---------- 演出 ----------
    def _orb_node(self, color, r=0.14):
        key = ("orb", color, r)
        n = self._fx_cache.get(key)
        if n is None:
            mb = MB()
            sphere(mb, M(), r, rgb(*color), seg=8, rings=5)
            n = mb.node("orb")
            self._fx_cache[key] = n
        return n

    def _ring_node(self, color):
        key = ("ring", color)
        n = self._fx_cache.get(key)
        if n is None:
            mb = MB()
            ring(mb, M(), 0.8, 1.0, rgb(*color, 0.85), seg=32)
            n = mb.node("ring")
            self._fx_cache[key] = n
        return n

    def fx_projectile(self, a, b, color=(255, 240, 180), dur=0.14, r=0.12):
        np = self.fx_root.attachNewNode(self._orb_node(color, r))
        self.fx.append({"np": np, "t0": self.now, "dur": dur, "kind": "proj", "a": a, "b": b})

    def fx_ring(self, p, color=(120, 200, 255), size=1.6, dur=0.45):
        np = self.fx_root.attachNewNode(self._ring_node(color))
        np.setPos(p[0], p[1], 0.1)
        self.fx.append({"np": np, "t0": self.now, "dur": dur, "kind": "ring", "size": size})

    def fx_burst(self, p, color=(255, 200, 120), n=6, dur=0.5, up=1.0, spread=0.6):
        for _ in range(n):
            np = self.fx_root.attachNewNode(self._orb_node(color, 0.07))
            v = (random.uniform(-spread, spread), random.uniform(-spread, spread), random.uniform(0.6, 1.4) * up)
            self.fx.append({"np": np, "t0": self.now, "dur": dur, "kind": "spark", "p": p, "v": v})

    def fx_bubble(self, p, color=(220, 220, 255), dur=0.6):
        np = self.fx_root.attachNewNode(self._orb_node(color, 0.7))
        np.setPos(p[0], p[1], p[2])
        np.setAlphaScale(0.3)
        self.fx.append({"np": np, "t0": self.now, "dur": dur, "kind": "bubble"})

    def update(self, dt):
        self.now += dt
        if self.auto_orbit:
            self.cam_yaw = 18 * math.sin(self.now * 0.15)
            self.update_camera()
        for a in self.actors.values():
            a.update(self.now)
        keep = []
        for f in self.fx:
            k = (self.now - f["t0"]) / f["dur"]
            np = f["np"]
            if k >= 1:
                np.removeNode()
                continue
            kind = f["kind"]
            if kind == "proj":
                a, b = f["a"], f["b"]
                np.setPos(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k,
                          a[2] + (b[2] - a[2]) * k + 0.4 * math.sin(k * math.pi))
            elif kind == "ring":
                s = 0.3 + f["size"] * k
                np.setScale(s, s, 1)
                np.setAlphaScale(1 - k)
            elif kind == "spark":
                p, v = f["p"], f["v"]
                t = k * f["dur"]
                np.setPos(p[0] + v[0] * t, p[1] + v[1] * t, p[2] + v[2] * t - 1.2 * t * t)
                np.setAlphaScale(1 - k)
            elif kind == "bubble":
                np.setAlphaScale(0.35 * (1 - k))
                np.setScale(1 + 0.2 * k)
            keep.append(f)
        self.fx = keep

    def clear_fx(self):
        for f in self.fx:
            f["np"].removeNode()
        self.fx = []
