# -*- coding: utf-8 -*-
"""ユニットの3Dモデル（外部ファイルを使わず、プログラムで形を組み立てる）

モデルの向き：+Y が正面、+Z が上。足元が z=0。六角マスの半径 = 1。
"""
import math
import zlib
from array import array

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData,
                          GeomVertexFormat, NodePath, Point3, TransformState, TransparencyAttrib, Vec3)

# ---------------- 形を作る道具 ----------------
_FMT = None


def _fmt():
    global _FMT
    if _FMT is None:
        a = GeomVertexArrayFormat()
        a.addColumn("vertex", 3, Geom.NT_float32, Geom.C_point)
        a.addColumn("normal", 3, Geom.NT_float32, Geom.C_normal)
        a.addColumn("color", 4, Geom.NT_float32, Geom.C_color)
        _FMT = GeomVertexFormat.registerFormat(GeomVertexFormat(a))
    return _FMT


def M(pos=(0, 0, 0), hpr=(0, 0, 0), scale=(1, 1, 1)):
    if not isinstance(scale, (tuple, list)):
        scale = (scale, scale, scale)
    return TransformState.makePosHprScale(Point3(*pos), Vec3(*hpr), Vec3(*scale)).getMat()


class MB:
    """三角形を貯めて、最後に1つの GeomNode にする"""

    def __init__(self):
        self.data = array("f")
        self.idx = array("I")
        self.n = 0

    def vert(self, m, p, nrm, c):
        q = m.xformPoint(Point3(*p))
        v = m.xformVec(Vec3(*nrm))
        v.normalize()
        self.data.extend((q[0], q[1], q[2], v[0], v[1], v[2], c[0], c[1], c[2], c[3] if len(c) > 3 else 1.0))
        self.n += 1
        return self.n - 1

    def tri(self, a, b, c):
        self.idx.extend((a, b, c))

    def quad(self, a, b, c, d):
        self.idx.extend((a, b, c, a, c, d))

    def node(self, name="geom"):
        gn = GeomNode(name)
        if not self.n:
            return gn
        vd = GeomVertexData(name, _fmt(), Geom.UHStatic)
        vd.uncleanSetNumRows(self.n)
        arr = vd.modifyArray(0)
        memoryview(arr).cast("B")[:] = self.data.tobytes()
        prim = GeomTriangles(Geom.UHStatic)
        prim.setIndexType(Geom.NT_uint32)
        va = prim.modifyVertices()
        va.uncleanSetNumRows(len(self.idx))
        memoryview(va).cast("B")[:] = self.idx.tobytes()
        g = Geom(vd)
        g.addPrimitive(prim)
        gn.addGeom(g)
        return gn


def box(mb, m, sx, sy, sz, c):
    """中心が原点、各辺の長さ sx,sy,sz の箱"""
    x, y, z = sx / 2, sy / 2, sz / 2
    faces = [((0, 0, 1), [(-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]),
             ((0, 0, -1), [(-x, y, -z), (x, y, -z), (x, -y, -z), (-x, -y, -z)]),
             ((0, -1, 0), [(-x, -y, -z), (x, -y, -z), (x, -y, z), (-x, -y, z)]),
             ((0, 1, 0), [(x, y, -z), (-x, y, -z), (-x, y, z), (x, y, z)]),
             ((1, 0, 0), [(x, -y, -z), (x, y, -z), (x, y, z), (x, -y, z)]),
             ((-1, 0, 0), [(-x, y, -z), (-x, -y, -z), (-x, -y, z), (-x, y, z)])]
    for n, ps in faces:
        i = [mb.vert(m, p, n, c) for p in ps]
        mb.quad(*i)


def cyl(mb, m, r0, r1, h, c, seg=12, cap=True, c_top=None):
    """z=0 に半径r0、z=h に半径r1 の筒（r1=0で円すい）"""
    slope = (r0 - r1) / h if h else 0
    ring0, ring1 = [], []
    for k in range(seg + 1):
        a = 2 * math.pi * k / seg
        ca, sa = math.cos(a), math.sin(a)
        n = (ca, sa, slope)
        ring0.append(mb.vert(m, (r0 * ca, r0 * sa, 0), n, c))
        ring1.append(mb.vert(m, (r1 * ca, r1 * sa, h), n, c))
    for k in range(seg):
        mb.quad(ring0[k], ring0[k + 1], ring1[k + 1], ring1[k])
    if cap:
        ct = c_top or c
        if r1 > 0:
            cen = mb.vert(m, (0, 0, h), (0, 0, 1), ct)
            rr = [mb.vert(m, (r1 * math.cos(2 * math.pi * k / seg), r1 * math.sin(2 * math.pi * k / seg), h),
                          (0, 0, 1), ct) for k in range(seg + 1)]
            for k in range(seg):
                mb.tri(cen, rr[k], rr[k + 1])
        if r0 > 0:
            cen = mb.vert(m, (0, 0, 0), (0, 0, -1), c)
            rr = [mb.vert(m, (r0 * math.cos(2 * math.pi * k / seg), r0 * math.sin(2 * math.pi * k / seg), 0),
                          (0, 0, -1), c) for k in range(seg + 1)]
            for k in range(seg):
                mb.tri(cen, rr[k + 1], rr[k])


def sphere(mb, m, r, c, seg=12, rings=8, top=1.0):
    """球（top<1 で上だけの半球など）"""
    grid = []
    for i in range(rings + 1):
        th = math.pi * (1 - top) + math.pi * top * i / rings  # 下→上
        th = math.pi - th
        row = []
        for k in range(seg + 1):
            a = 2 * math.pi * k / seg
            n = (math.sin(th) * math.cos(a), math.sin(th) * math.sin(a), math.cos(th))
            row.append(mb.vert(m, (n[0] * r, n[1] * r, n[2] * r), n, c))
        grid.append(row)
    for i in range(rings):
        for k in range(seg):
            mb.quad(grid[i][k], grid[i][k + 1], grid[i + 1][k + 1], grid[i + 1][k])


def plate(mb, m, pts, t, c):
    """XY平面の凸多角形を Z方向に厚み t で押し出した板"""
    top = [mb.vert(m, (x, y, t / 2), (0, 0, 1), c) for x, y in pts]
    bot = [mb.vert(m, (x, y, -t / 2), (0, 0, -1), c) for x, y in pts]
    for k in range(1, len(pts) - 1):
        mb.tri(top[0], top[k], top[k + 1])
        mb.tri(bot[0], bot[k + 1], bot[k])
    n = len(pts)
    for k in range(n):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) % n]
        nn = (y1 - y0, -(x1 - x0), 0)
        if abs(nn[0]) + abs(nn[1]) < 1e-9:
            continue
        a = mb.vert(m, (x0, y0, -t / 2), nn, c)
        b = mb.vert(m, (x1, y1, -t / 2), nn, c)
        cc = mb.vert(m, (x1, y1, t / 2), nn, c)
        d = mb.vert(m, (x0, y0, t / 2), nn, c)
        mb.quad(a, b, cc, d)


def ring(mb, m, r_in, r_out, c, seg=36):
    """上向きの平たい輪"""
    for k in range(seg):
        a0 = 2 * math.pi * k / seg
        a1 = 2 * math.pi * (k + 1) / seg
        p = [(r_in * math.cos(a0), r_in * math.sin(a0), 0), (r_out * math.cos(a0), r_out * math.sin(a0), 0),
             (r_out * math.cos(a1), r_out * math.sin(a1), 0), (r_in * math.cos(a1), r_in * math.sin(a1), 0)]
        i = [mb.vert(m, q, (0, 0, 1), c) for q in p]
        mb.quad(*i)


def hex_prism(mb, m, r, h, c_top, c_side):
    """上が z=0、下が z=-h の六角柱（とがった方向が ±Y）"""
    pts = [(r * math.cos(math.radians(90 + 60 * k)), r * math.sin(math.radians(90 + 60 * k))) for k in range(6)]
    top = [mb.vert(m, (x, y, 0), (0, 0, 1), c_top) for x, y in pts]
    cen = mb.vert(m, (0, 0, 0), (0, 0, 1), c_top)
    for k in range(6):
        mb.tri(cen, top[k], top[(k + 1) % 6])
    for k in range(6):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) % 6]
        nn = ((x0 + x1) / 2, (y0 + y1) / 2, 0)
        a = mb.vert(m, (x0, y0, 0), nn, c_side)
        b = mb.vert(m, (x0, y0, -h), nn, c_side)
        cc = mb.vert(m, (x1, y1, -h), nn, c_side)
        d = mb.vert(m, (x1, y1, 0), nn, c_side)
        mb.quad(a, b, cc, d)


# ---------------- 色 ----------------
def rgb(r, g, b, a=1.0):
    return (r / 255, g / 255, b / 255, a)


def mix(c1, c2, k):
    return tuple(c1[i] * (1 - k) + c2[i] * k for i in range(3)) + (c1[3] if len(c1) > 3 else 1.0,)


def shade(c, k):
    return tuple(min(1.0, max(0.0, v * k)) for v in c[:3]) + (c[3] if len(c) > 3 else 1.0,)


ELEMENT_COLORS = {
    "炎": rgb(225, 80, 45), "氷": rgb(140, 205, 245), "雷": rgb(245, 210, 50), "森": rgb(70, 160, 70),
    "闇": rgb(100, 60, 140), "光": rgb(250, 235, 180), "鋼": rgb(150, 160, 175), "砂": rgb(215, 180, 120),
    "海": rgb(40, 130, 190), "獣": rgb(150, 100, 60), "毒": rgb(140, 190, 50), "風": rgb(120, 220, 190),
    "岩": rgb(135, 120, 100), "桜": rgb(245, 160, 200), "竜": rgb(190, 40, 50), "機械": rgb(120, 130, 140),
    "亡霊": rgb(190, 180, 235), "星": rgb(50, 60, 140),
}
SKINS = [rgb(250, 220, 190), rgb(235, 195, 160), rgb(205, 160, 120), rgb(160, 115, 85), rgb(255, 230, 210)]
HAIRS = [rgb(40, 30, 25), rgb(90, 55, 30), rgb(200, 160, 80), rgb(220, 220, 225), rgb(160, 50, 40),
         rgb(60, 70, 120), rgb(30, 30, 40)]
BLACK = rgb(20, 20, 26)
WHITE = rgb(240, 240, 245)
STEEL = rgb(190, 198, 210)
WOOD = rgb(120, 80, 45)
GOLDC = rgb(240, 195, 70)


def _hash(s):
    return zlib.crc32(s.encode("utf-8"))


def element_color(el):
    if el in ELEMENT_COLORS:
        return ELEMENT_COLORS[el]
    h = _hash(el)
    return rgb(80 + h % 160, 80 + (h >> 8) % 160, 80 + (h >> 16) % 160)


# ---------------- モデル本体 ----------------
class Model:
    """組み立て済みモデル。body / arm_r / arm_l を動かしてアニメーションする"""

    def __init__(self, root, body, arm_r, arm_l, height, kind):
        self.root = root
        self.body = body
        self.arm_r = arm_r
        self.arm_l = arm_l
        self.height = height
        self.kind = kind


class Parts:
    def __init__(self):
        self.body = MB()
        self.arm_r = MB()
        self.arm_l = MB()
        self.glow = MB()      # 光る部分（ライトの影響を受けない）
        self.ghost = MB()     # 半透明の部分
        self.shoulder_r = (0.27, 0, 0.82)
        self.shoulder_l = (-0.27, 0, 0.82)


def _eyes(mb, z, y, dx=0.065, c=BLACK, size=0.045):
    box(mb, M((dx, y, z)), size, 0.02, size * 1.3, c)
    box(mb, M((-dx, y, z)), size, 0.02, size * 1.3, c)


def _arm(mb, color, hand, length=0.36, r=0.06):
    cyl(mb, M((0, 0, -length), (0, 0, 0)), r * 0.9, r, length, color, seg=8)
    sphere(mb, M((0, 0, -length)), r * 1.05, hand, seg=8, rings=5)


def _humanoid_base(p, c1, c2, skin, hair, legs=True, robe=False, hair_style=True):
    b = p.body
    if robe:
        cyl(b, M((0, 0, 0)), 0.30, 0.19, 0.86, c1, seg=14)
        cyl(b, M((0, 0, 0)), 0.31, 0.30, 0.06, c2, seg=14)
    elif legs:
        for sx in (-0.1, 0.1):
            box(b, M((sx, 0, 0.22)), 0.14, 0.17, 0.44, shade(c2, 0.7))
            box(b, M((sx, 0.02, 0.04)), 0.16, 0.22, 0.08, BLACK)
    if not robe:
        box(b, M((0, 0, 0.64)), 0.44, 0.27, 0.42, c1)
        box(b, M((0, 0, 0.46)), 0.46, 0.29, 0.07, c2)
    box(b, M((0, 0, 0.88)), 0.12, 0.12, 0.08, skin)
    sphere(b, M((0, 0, 1.03)), 0.18, skin, seg=14, rings=9)
    _eyes(b, 1.04, 0.17)
    if hair_style:
        sphere(b, M((0, -0.025, 1.07)), 0.195, hair, seg=14, rings=6, top=0.55)
        box(b, M((0, -0.12, 0.98)), 0.3, 0.1, 0.2, hair)


def _limbs(p, sleeve, hand):
    _arm(p.arm_r, sleeve, hand)
    _arm(p.arm_l, sleeve, hand)


def _wing(mb, sx, size, c, pos=(0, 0, 0)):
    """横に広がるつばさ（sx=1で右、-1で左）"""
    pts = [(0, 0), (0.2, -0.15), (0.55, -0.2), (0.75, 0.1), (0.8, 0.55), (0.25, 0.25)]
    pts = [(x * size * sx, y * size) for x, y in pts]
    if sx < 0:
        pts.reverse()
    plate(mb, M(pos, (-sx * 25, 90, 0)), pts, 0.03, c)


def build_knight(p, c1, c2, trim, skin, hair):
    _humanoid_base(p, STEEL, c1, skin, hair, hair_style=False)
    b = p.body
    box(b, M((0, 0.14, 0.66)), 0.3, 0.04, 0.3, c1)                     # 胸の紋章
    sphere(b, M((0.26, 0, 0.84)), 0.11, trim, seg=10, rings=6)           # 肩当て
    sphere(b, M((-0.26, 0, 0.84)), 0.11, trim, seg=10, rings=6)
    cyl(b, M((0, 0, 0.92)), 0.2, 0.19, 0.2, STEEL, seg=14)               # かぶと
    sphere(b, M((0, 0, 1.12)), 0.19, STEEL, seg=14, rings=6, top=0.5)
    box(b, M((0, 0.18, 1.04)), 0.26, 0.03, 0.04, BLACK)                  # のぞき穴
    cyl(b, M((0, -0.02, 1.26), (0, -20, 0)), 0.04, 0.02, 0.28, c1, seg=6)  # 羽飾り
    _limbs(p, STEEL, STEEL)
    ar = p.arm_r                                                         # 剣
    box(ar, M((0, 0.05, -0.36)), 0.05, 0.1, 0.05, WOOD)
    box(ar, M((0, 0.1, -0.36)), 0.2, 0.04, 0.05, trim)
    box(ar, M((0, 0.42, -0.36)), 0.035, 0.6, 0.08, WHITE)
    al = p.arm_l                                                         # 盾
    box(al, M((-0.05, 0.12, -0.3)), 0.06, 0.08, 0.1, WOOD)
    plate(al, M((-0.09, 0.14, -0.28), (0, 0, 90)),
          [(-0.2, 0.22), (0.2, 0.22), (0.2, -0.05), (0, -0.28), (-0.2, -0.05)], 0.05, c1)
    plate(al, M((-0.12, 0.14, -0.28), (0, 0, 90)),
          [(-0.06, 0.12), (0.06, 0.12), (0.06, -0.04), (0, -0.12), (-0.06, -0.04)], 0.02, trim)


def build_warrior(p, c1, c2, trim, skin, hair):
    _humanoid_base(p, c1, c2, skin, hair)
    b = p.body
    box(b, M((0, 0, 1.13)), 0.38, 0.38, 0.05, trim)                      # はちまき
    sphere(b, M((0.27, 0, 0.84)), 0.1, trim, seg=10, rings=6)
    _limbs(p, c1, skin)
    ar = p.arm_r                                                         # 大剣
    box(ar, M((0, 0.06, -0.36)), 0.05, 0.14, 0.05, WOOD)
    box(ar, M((0, 0.14, -0.36)), 0.26, 0.05, 0.06, trim)
    box(ar, M((0, 0.55, -0.36)), 0.04, 0.8, 0.13, STEEL)


def build_lancer(p, c1, c2, trim, skin, hair):
    _humanoid_base(p, c1, c2, skin, hair)
    b = p.body
    cyl(b, M((0, 0, 1.08)), 0.2, 0.0, 0.26, trim, seg=12)                # とんがりかぶと
    _limbs(p, c1, skin)
    ar = p.arm_r                                                         # やり（縦に持つ）
    cyl(ar, M((0, 0.02, -0.9)), 0.028, 0.028, 1.5, WOOD, seg=6)
    cyl(ar, M((0, 0.02, 0.6)), 0.06, 0.0, 0.24, STEEL, seg=6)
    cyl(ar, M((0, 0.02, 0.56)), 0.07, 0.07, 0.05, trim, seg=6)


def build_archer(p, c1, c2, trim, skin, hair):
    _humanoid_base(p, c1, c2, skin, hair, hair_style=False)
    b = p.body
    sphere(b, M((0, -0.03, 1.06)), 0.21, c2, seg=14, rings=7, top=0.62)  # フード
    cyl(b, M((0.08, -0.2, 0.5), (0, 20, 0)), 0.07, 0.07, 0.42, WOOD, seg=8)  # 矢筒
    for dx in (-0.03, 0.03, 0.09):
        cyl(b, M((0.08 + dx * 0.6, -0.2 - 0.02, 0.9), (0, 20, 0)), 0.012, 0.012, 0.14, WHITE, seg=4)
    _limbs(p, c1, skin)
    al = p.arm_l                                                         # 弓
    n = 9
    for k in range(n):
        a0 = math.radians(-70 + 140 * k / n)
        a1 = math.radians(-70 + 140 * (k + 1) / n)
        x0, z0 = 0.38 * math.cos(a0), 0.38 * math.sin(a0)
        x1, z1 = 0.38 * math.cos(a1), 0.38 * math.sin(a1)
        ang = math.degrees(math.atan2(z1 - z0, x1 - x0))
        ln = math.hypot(x1 - x0, z1 - z0)
        box(al, M((0, 0.02 + (x0 + x1) / 2 - 0.2, -0.36 + (z0 + z1) / 2), (0, ang, 0)), 0.04, ln + 0.01, 0.04, WOOD)
    top = (0.02 + 0.38 * math.cos(math.radians(70)) - 0.2, -0.36 + 0.38 * math.sin(math.radians(70)))
    cyl(al, M((0, top[0], -0.36 - 0.38 * math.sin(math.radians(70)))), 0.006, 0.006,
        2 * 0.38 * math.sin(math.radians(70)), WHITE, seg=4, cap=False)


def build_mage(p, c1, c2, trim, skin, hair):
    _humanoid_base(p, c1, trim, skin, hair, robe=True)
    b = p.body
    cyl(b, M((0, 0, 1.12)), 0.34, 0.33, 0.03, c1, seg=16)                # ぼうし
    cyl(b, M((0, 0, 1.14), (0, -8, 0)), 0.19, 0.0, 0.42, c1, seg=12)
    cyl(b, M((0, 0, 1.14)), 0.195, 0.19, 0.05, trim, seg=12)
    _limbs(p, c1, skin)
    ar = p.arm_r                                                         # つえ
    cyl(ar, M((0, 0.05, -0.85)), 0.025, 0.03, 1.2, WOOD, seg=6)
    sphere(p.glow, M((0.27, 0.05, 0.82 + 0.4)), 0.09, mix(c2, WHITE, 0.4), seg=10, rings=6)


def build_assassin(p, c1, c2, trim, skin, hair):
    dark = shade(c1, 0.45)
    _humanoid_base(p, dark, c1, skin, hair)
    b = p.body
    box(b, M((0, 0.1, 0.99)), 0.3, 0.16, 0.12, dark)                     # 口元の布
    box(b, M((0, 0, 1.11)), 0.39, 0.39, 0.05, c1)                        # はちがね
    plate(b, M((0.1, -0.2, 1.08), (0, 0, 90)), [(0, 0.0), (0.5, -0.1), (0.5, -0.02)], 0.03, c1)  # なびく布
    _limbs(p, dark, skin)
    for arm in (p.arm_r, p.arm_l):                                       # 短刀
        box(arm, M((0, 0.04, -0.36)), 0.04, 0.08, 0.04, BLACK)
        box(arm, M((0, 0.2, -0.36)), 0.025, 0.28, 0.06, STEEL)


def build_beast(p, c1, c2, trim, skin, hair):
    fur = c1
    _humanoid_base(p, shade(c1, 0.8), c2, mix(fur, WHITE, 0.25), fur, hair_style=True)
    b = p.body
    for sx in (-0.11, 0.11):                                             # 耳
        cyl(b, M((sx, -0.02, 1.16), (0, 0, sx * 120)), 0.06, 0.0, 0.18, fur, seg=6)
    box(b, M((0, 0.19, 0.99)), 0.1, 0.06, 0.07, BLACK)                   # 鼻
    for k in range(4):                                                   # しっぽ
        cyl(b, M((0, -0.16 - k * 0.07, 0.45 + k * 0.05), (0, -60 + k * 10, 0)), 0.06 - k * 0.01, 0.05 - k * 0.01,
            0.12, fur, seg=6)
    _limbs(p, shade(c1, 0.8), fur)
    for arm in (p.arm_r, p.arm_l):                                       # つめ
        for dx in (-0.03, 0, 0.03):
            cyl(arm, M((dx, 0.04, -0.4), (0, 60, 0)), 0.015, 0.0, 0.1, WHITE, seg=4)


def build_dragonkin(p, c1, c2, trim, skin, hair):
    scale_c = c1
    _humanoid_base(p, scale_c, shade(c1, 0.6), mix(scale_c, WHITE, 0.2), shade(c1, 0.5))
    b = p.body
    for sx in (-0.1, 0.1):                                               # つの
        cyl(b, M((sx, -0.04, 1.14), (0, -30, sx * 150)), 0.04, 0.0, 0.2, GOLDC, seg=6)
    for sx in (-1, 1):                                                   # つばさ
        _wing(b, sx, 0.6, shade(c1, 0.75), pos=(sx * 0.12, -0.16, 0.78))
    for k in range(5):
        cyl(b, M((0, -0.15 - k * 0.08, 0.4 - k * 0.06), (0, -70, 0)), 0.07 - k * 0.012, 0.06 - k * 0.012, 0.12,
            scale_c, seg=6)
    _limbs(p, scale_c, mix(scale_c, WHITE, 0.2))
    ar = p.arm_r                                                         # 竜の剣
    box(ar, M((0, 0.06, -0.36)), 0.05, 0.12, 0.05, BLACK)
    plate(ar, M((0, 0.4, -0.36), (0, 0, 90)), [(-0.06, -0.28), (0.06, -0.28), (0.09, 0.2), (0, 0.34), (-0.09, 0.2)],
          0.03, mix(trim, WHITE, 0.3))


def build_robot(p, c1, c2, trim, skin, hair):
    metal = mix(c1, STEEL, 0.5)
    b = p.body
    for sx in (-0.11, 0.11):
        box(b, M((sx, 0, 0.22)), 0.15, 0.18, 0.44, shade(metal, 0.7))
        box(b, M((sx, 0.03, 0.04)), 0.18, 0.26, 0.08, BLACK)
    box(b, M((0, 0, 0.66)), 0.5, 0.32, 0.46, metal)
    box(b, M((0, 0.165, 0.68)), 0.22, 0.02, 0.16, trim)
    box(b, M((0, 0, 0.91)), 0.1, 0.1, 0.06, BLACK)
    box(b, M((0, 0, 1.06)), 0.32, 0.3, 0.26, metal)
    cyl(b, M((0.1, 0, 1.19)), 0.012, 0.012, 0.16, BLACK, seg=4)
    box(p.glow, M((0, 0.155, 1.07)), 0.24, 0.02, 0.06, mix(trim, WHITE, 0.5))
    sphere(p.glow, M((0.1, 0, 1.36)), 0.035, rgb(255, 80, 80), seg=6, rings=4)
    for arm, sx in ((p.arm_r, 1), (p.arm_l, -1)):
        box(arm, M((0, 0, -0.18)), 0.12, 0.12, 0.36, shade(metal, 0.85))
        box(arm, M((0, 0.02, -0.38)), 0.15, 0.15, 0.1, BLACK)
    cyl(p.arm_r, M((0, 0.0, -0.38), (0, -90, 0)), 0.05, 0.05, 0.34, shade(metal, 0.6), seg=8)  # 腕の砲
    p.shoulder_r = (0.31, 0, 0.84)
    p.shoulder_l = (-0.31, 0, 0.84)


def build_ghost(p, c1, c2, trim, skin, hair):
    pale = mix(c1, WHITE, 0.35)
    g = p.ghost
    cyl(g, M((0, 0, 0.12)), 0.08, 0.3, 0.6, pale[:3] + (0.75,), seg=14, cap=False)
    sphere(g, M((0, 0, 0.72)), 0.3, pale[:3] + (0.75,), seg=14, rings=8, top=0.55)
    sphere(g, M((0, 0, 1.0)), 0.2, pale[:3] + (0.8,), seg=14, rings=9)
    cyl(g, M((0, 0, 1.12)), 0.24, 0.0, 0.3, shade(c1, 0.6)[:3] + (0.85,), seg=12)
    for sx in (-0.07, 0.07):
        sphere(p.glow, M((sx, 0.18, 1.02)), 0.035, rgb(120, 230, 255), seg=6, rings=4)
    _arm(p.arm_r, pale[:3] + (0.75,), pale[:3] + (0.75,))
    _arm(p.arm_l, pale[:3] + (0.75,), pale[:3] + (0.75,))
    cyl(p.arm_r, M((0, 0.05, -0.9)), 0.02, 0.02, 1.25, BLACK, seg=5)     # 大鎌
    plate(p.arm_r, M((0, 0.05, 0.35), (0, 0, 90)), [(0, 0), (0.08, 0.02), (0.45, -0.1), (0.1, -0.08)], 0.02, STEEL)


def build_goblin(p, c1, c2, trim, skin, hair):
    green = rgb(110, 160, 70)
    _humanoid_base(p, rgb(120, 90, 60), rgb(90, 70, 50), green, green, hair_style=False)
    b = p.body
    for sx in (-1, 1):
        cyl(b, M((sx * 0.16, 0, 1.05), (0, 0, -sx * 80)), 0.06, 0.0, 0.22, green, seg=6)
    box(b, M((0, 0.18, 1.0)), 0.06, 0.08, 0.06, shade(green, 0.8))
    _limbs(p, green, green)
    cyl(p.arm_r, M((0, 0.05, -0.4), (0, -90, 0)), 0.04, 0.09, 0.5, WOOD, seg=8)  # こん棒


def build_slime(p, c1, c2, trim, skin, hair):
    col = rgb(90, 200, 120, 0.82)
    sphere(p.ghost, M((0, 0, 0.3), (0, 0, 0), (1.0, 1.0, 0.7)), 0.42, col, seg=16, rings=10)
    sphere(p.ghost, M((0, 0, 0.05), (0, 0, 0), (1.0, 1.0, 0.25)), 0.44, col, seg=16, rings=6)
    _eyes(p.body, 0.42, 0.37, dx=0.12, size=0.07)
    box(p.body, M((0, 0.38, 0.3)), 0.12, 0.02, 0.03, BLACK)
    p.shoulder_r = p.shoulder_l = (0, 0, 0.3)


def build_wolf(p, c1, c2, trim, skin, hair):
    fur = rgb(130, 130, 140)
    b = p.body
    box(b, M((0, -0.05, 0.5)), 0.32, 0.72, 0.3, fur)
    box(b, M((0, 0.35, 0.62)), 0.3, 0.26, 0.26, fur)                     # 頭
    box(b, M((0, 0.53, 0.56)), 0.16, 0.2, 0.13, mix(fur, WHITE, 0.3))    # 鼻先
    box(b, M((0, 0.64, 0.6)), 0.06, 0.03, 0.05, BLACK)
    for sx in (-0.08, 0.08):
        cyl(b, M((sx, 0.3, 0.74)), 0.05, 0.0, 0.15, fur, seg=5)
        box(b, M((sx, 0.48, 0.66)), 0.04, 0.02, 0.03, rgb(255, 220, 60))
    for sx in (-0.11, 0.11):
        for sy in (-0.3, 0.22):
            box(b, M((sx, sy, 0.18)), 0.09, 0.09, 0.36, shade(fur, 0.8))
    cyl(b, M((0, -0.4, 0.55), (0, -120, 0)), 0.06, 0.02, 0.35, fur, seg=6)
    p.shoulder_r = p.shoulder_l = (0, 0.3, 0.5)


def build_golem(p, c1, c2, trim, skin, hair):
    stone = rgb(125, 115, 105)
    b = p.body
    for sx in (-0.15, 0.15):
        box(b, M((sx, 0, 0.22)), 0.2, 0.22, 0.44, shade(stone, 0.8))
    box(b, M((0, 0, 0.72)), 0.66, 0.4, 0.56, stone)
    box(b, M((0, 0.05, 1.08)), 0.3, 0.28, 0.24, shade(stone, 0.9))
    box(b, M((0.2, 0.1, 0.95)), 0.12, 0.2, 0.1, rgb(90, 140, 70))       # こけ
    for sx in (-0.07, 0.07):
        box(p.glow, M((sx, 0.2, 1.1)), 0.06, 0.02, 0.04, rgb(255, 170, 60))
    for arm in (p.arm_r, p.arm_l):
        box(arm, M((0, 0, -0.22)), 0.2, 0.2, 0.46, stone)
        box(arm, M((0, 0.02, -0.5)), 0.26, 0.26, 0.2, shade(stone, 0.8))
    p.shoulder_r = (0.44, 0, 0.9)
    p.shoulder_l = (-0.44, 0, 0.9)


def build_dragon(p, c1, c2, trim, skin, hair):
    sc = rgb(170, 40, 45)
    belly = rgb(235, 190, 120)
    b = p.body
    sphere(b, M((0, -0.05, 0.55), (0, 0, 0), (0.8, 1.2, 0.75)), 0.4, sc, seg=14, rings=8)
    sphere(b, M((0, 0.05, 0.5), (0, 0, 0), (0.6, 1.0, 0.6)), 0.38, belly, seg=12, rings=6)
    cyl(b, M((0, 0.3, 0.7), (0, 40, 0)), 0.16, 0.11, 0.45, sc, seg=10)  # 首
    box(b, M((0, 0.62, 1.07)), 0.26, 0.4, 0.2, sc)                       # 頭
    box(b, M((0, 0.8, 1.01)), 0.18, 0.2, 0.1, shade(sc, 0.85))
    for sx in (-0.08, 0.08):
        cyl(b, M((sx, 0.5, 1.15), (0, -60, sx * 100)), 0.04, 0.0, 0.2, GOLDC, seg=5)
        box(p.glow, M((sx, 0.72, 1.12)), 0.04, 0.02, 0.03, rgb(255, 230, 60))
    for sx in (-0.2, 0.2):
        for sy in (-0.3, 0.18):
            box(b, M((sx, sy, 0.15)), 0.12, 0.14, 0.3, shade(sc, 0.8))
    for k in range(5):
        cyl(b, M((0, -0.42 - k * 0.12, 0.45 - k * 0.07), (0, -80, 0)), 0.12 - k * 0.02, 0.1 - k * 0.02, 0.15,
            sc, seg=8)
    for sx in (-1, 1):
        _wing(p.arm_r if sx > 0 else p.arm_l, sx, 1.0, shade(sc, 0.7))
    p.shoulder_r = (0.2, -0.05, 0.85)
    p.shoulder_l = (-0.2, -0.05, 0.85)


BUILDERS = {"knight": build_knight, "warrior": build_warrior, "lancer": build_lancer, "archer": build_archer,
            "mage": build_mage, "assassin": build_assassin, "beast": build_beast, "dragonkin": build_dragonkin,
            "robot": build_robot, "ghost": build_ghost, "goblin": build_goblin, "slime": build_slime,
            "wolf": build_wolf, "golem": build_golem, "dragon": build_dragon}
LOOK_SCALE = {"golem": 1.3, "dragon": 1.25, "slime": 1.0, "wolf": 1.0, "goblin": 0.85}
FLOAT_LOOKS = {"ghost"}

_templates = {}


def _template(look, key, element, trim):
    tk = (look, key, element, trim)
    t = _templates.get(tk)
    if t is not None:
        return t
    h = _hash(key)
    c1 = element_color(element)
    c2 = shade(mix(c1, WHITE, 0.15), 0.62)
    skin = SKINS[h % len(SKINS)]
    hair = HAIRS[(h >> 4) % len(HAIRS)]
    trim_c = rgb(*trim)
    p = Parts()
    BUILDERS.get(look, build_warrior)(p, c1, c2, trim_c, skin, hair)
    root = NodePath("tmpl")
    body = root.attachNewNode("body")
    body.attachNewNode(p.body.node("b"))
    glow = body.attachNewNode(p.glow.node("glow"))
    glow.setLightOff(1)
    glow.setShaderOff(1)
    gh = body.attachNewNode(p.ghost.node("ghost"))
    gh.setTransparency(TransparencyAttrib.MAlpha)
    gh.setDepthWrite(False)
    gh.setBin("transparent", 10)
    ar = body.attachNewNode("arm_r")
    ar.setPos(*p.shoulder_r)
    ar.attachNewNode(p.arm_r.node("ar"))
    al = body.attachNewNode("arm_l")
    al.setPos(*p.shoulder_l)
    al.attachNewNode(p.arm_l.node("al"))
    if look in ("mage",):
        glow.reparentTo(ar)
        glow.setPos(-p.shoulder_r[0], -p.shoulder_r[1], -p.shoulder_r[2])
    if look in ("ghost", "slime"):
        ar.find("ar").setTransparency(TransparencyAttrib.MAlpha)
        al.find("al").setTransparency(TransparencyAttrib.MAlpha)
    _templates[tk] = root
    return root


_base_cache = {}


def _base_node(team_color, trim):
    k = (team_color, trim)
    n = _base_cache.get(k)
    if n is None:
        mb = MB()
        cyl(mb, M((0, 0, 0.0)), 0.5, 0.47, 0.06, shade(rgb(*trim), 0.55), seg=24, c_top=rgb(*trim))
        n = mb.node("base")
        mb2 = MB()
        ring(mb2, M((0, 0, 0.065)), 0.5, 0.6, rgb(*team_color, 0.9), seg=32)
        n2 = mb2.node("team")
        _base_cache[k] = (n, n2)
        n = _base_cache[k]
    return n


def make_model(uid, info, star, team_color, is_creep=False):
    """ユニット1体分のモデル（テンプレートをコピー）"""
    look = info.get("look") or ("slime" if is_creep else "warrior")
    element = info["traits"][0] if not is_creep else "_creep"
    trim = (150, 95, 70) if is_creep else {1: (150, 150, 160), 2: (60, 175, 95), 3: (60, 130, 230),
                                            4: (175, 85, 225), 5: (240, 185, 40)}.get(info.get("cost", 1), (150, 150, 160))
    tmpl = _template(look, uid, element, trim)
    root = NodePath("unit")
    base_n, team_n = _base_node(tuple(team_color), trim)
    root.attachNewNode(base_n)
    tn = root.attachNewNode(team_n)
    tn.setLightOff(1)
    tn.setShaderOff(1)
    tn.setTransparency(TransparencyAttrib.MAlpha)
    holder = root.attachNewNode("holder")
    tmpl.getChild(0).copyTo(holder)
    body = holder.find("body")
    body.setZ(0.06)
    s = LOOK_SCALE.get(look, 1.0) * [1.0, 1.12, 1.25][star - 1]
    holder.setScale(s)
    return Model(root, body, body.find("arm_r"), body.find("arm_l"), 1.3 * s + 0.1, look)
