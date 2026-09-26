# -*- coding: utf-8 -*-
"""ユニット・コントローラーの3Dモデル（外部ファイルを使わず、プログラムで形を組み立てる）

モデルの向き：+Y が正面、+Z が上。足元が z=0。六角マスの半径 = 1。
見た目の工夫：
  ・パーツごとに黒いふち（アウトライン）を付けてアニメ調にする
  ・コストが高いほど豪華（2:胸の紋章 3:属性のオーラ 4:マント 5:光の輪）
  ・脚・腕・体を別々に動かせるようにして、歩き・攻撃・詠唱の動きを付ける
"""
import math
import zlib
from array import array

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat, GeomVertexData,
                          GeomVertexFormat, NodePath, Point3, TransformState, TransparencyAttrib, Vec3)

# ---------------- 形を作る道具 ----------------
_FMT = None
OL = 0.02                       # アウトラインの太さ
OL_COLOR = (0.07, 0.06, 0.1, 1.0)


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


def mul(a, b):
    """a（ローカル）→ b（親）の順に変換"""
    return a * b


class MB:
    """三角形を貯めて、最後に1つの GeomNode にする。outline=True ならふち用の形も同時に作る"""

    def __init__(self, outline=False, flip=False):
        self.data = array("f")
        self.idx = array("I")
        self.n = 0
        self.flip = flip
        self.ol = MB(False, True) if outline else None

    def vert(self, m, p, nrm, c):
        q = m.xformPoint(Point3(*p))
        v = m.xformVec(Vec3(*nrm))
        v.normalize()
        self.data.extend((q[0], q[1], q[2], v[0], v[1], v[2], c[0], c[1], c[2], c[3] if len(c) > 3 else 1.0))
        self.n += 1
        return self.n - 1

    def tri(self, a, b, c):
        if self.flip:
            self.idx.extend((a, c, b))
        else:
            self.idx.extend((a, b, c))

    def quad(self, a, b, c, d):
        self.tri(a, b, c)
        self.tri(a, c, d)

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


def box(mb, m, sx, sy, sz, c, outline=True):
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
    if outline and mb.ol is not None and min(sx, sy, sz) > 0.025:
        box(mb.ol, m, sx + 2 * OL, sy + 2 * OL, sz + 2 * OL, OL_COLOR, False)


def cyl(mb, m, r0, r1, h, c, seg=14, cap=True, c_top=None, outline=True):
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
    if outline and mb.ol is not None and max(r0, r1) > 0.018:
        cyl(mb.ol, mul(M((0, 0, -OL)), m), r0 + OL, r1 + OL if r1 > 0 else 0, h + 2 * OL, OL_COLOR, seg, cap, None,
            False)


def sphere(mb, m, r, c, seg=16, rings=10, top=1.0, outline=True):
    """球（top<1 で上だけの半球など）"""
    grid = []
    for i in range(rings + 1):
        th = math.pi - (math.pi * (1 - top) + math.pi * top * i / rings)
        row = []
        for k in range(seg + 1):
            a = 2 * math.pi * k / seg
            n = (math.sin(th) * math.cos(a), math.sin(th) * math.sin(a), math.cos(th))
            row.append(mb.vert(m, (n[0] * r, n[1] * r, n[2] * r), n, c))
        grid.append(row)
    for i in range(rings):
        for k in range(seg):
            mb.quad(grid[i][k], grid[i][k + 1], grid[i + 1][k + 1], grid[i + 1][k])
    if outline and mb.ol is not None and r > 0.03:
        sphere(mb.ol, m, r + OL, OL_COLOR, seg, rings, top, False)


def capsule(mb, m, r, h, c, seg=14, outline=True, r_top=None):
    """z=0〜h の丸い棒（手足・胴に使う）"""
    rt = r if r_top is None else r_top
    sphere(mb, m, r, c, seg, 7, outline=outline)
    cyl(mb, m, r, rt, h, c, seg, cap=False, outline=outline)
    sphere(mb, mul(M((0, 0, h)), m), rt, c, seg, 7, outline=outline)


def torus(mb, m, R, r, c, seg=24, seg2=8, outline=True):
    """横向きの輪（光の輪・ベルトなど）"""
    grid = []
    for i in range(seg + 1):
        a = 2 * math.pi * i / seg
        row = []
        for k in range(seg2 + 1):
            b = 2 * math.pi * k / seg2
            n = (math.cos(a) * math.cos(b), math.sin(a) * math.cos(b), math.sin(b))
            p = ((R + r * math.cos(b)) * math.cos(a), (R + r * math.cos(b)) * math.sin(a), r * math.sin(b))
            row.append(mb.vert(m, p, n, c))
        grid.append(row)
    for i in range(seg):
        for k in range(seg2):
            mb.quad(grid[i][k], grid[i + 1][k], grid[i + 1][k + 1], grid[i][k + 1])
    if outline and mb.ol is not None and r > 0.012:
        torus(mb.ol, m, R, r + OL * 0.8, OL_COLOR, seg, seg2, False)


def plate(mb, m, pts, t, c, outline=True):
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
    if outline and mb.ol is not None:
        cx = sum(p[0] for p in pts) / n
        cy = sum(p[1] for p in pts) / n
        big = []
        for x, y in pts:
            dx, dy = x - cx, y - cy
            d = math.hypot(dx, dy) or 1
            big.append((x + dx / d * OL, y + dy / d * OL))
        plate(mb.ol, m, big, t + 2 * OL, OL_COLOR, False)


def gem(mb, m, r, c, outline=True):
    """八面体の宝石"""
    pts = [(r, 0, 0), (0, r, 0), (-r, 0, 0), (0, -r, 0)]
    top, bot = (0, 0, r * 1.4), (0, 0, -r * 1.4)
    for k in range(4):
        a, b = pts[k], pts[(k + 1) % 4]
        for tip, flip in ((top, False), (bot, True)):
            nx = (a[0] + b[0] + tip[0]) / 3
            ny = (a[1] + b[1] + tip[1]) / 3
            nz = (a[2] + b[2] + tip[2]) / 3
            i = [mb.vert(m, p, (nx, ny, nz), c) for p in ((a, b, tip) if not flip else (b, a, tip))]
            mb.tri(*i)
    if outline and mb.ol is not None:
        gem(mb.ol, m, r + OL, OL_COLOR, False)


def ring(mb, m, r_in, r_out, c, seg=36):
    """上向きの平たい輪"""
    for k in range(seg):
        a0 = 2 * math.pi * k / seg
        a1 = 2 * math.pi * (k + 1) / seg
        p = [(r_in * math.cos(a0), r_in * math.sin(a0), 0), (r_out * math.cos(a0), r_out * math.sin(a0), 0),
             (r_out * math.cos(a1), r_out * math.sin(a1), 0), (r_in * math.cos(a1), r_in * math.sin(a1), 0)]
        i = [mb.vert(m, q, (0, 0, 1), c) for q in p]
        mb.quad(*i)


def hex_prism(mb, m, r, h, c_top, c_side, bevel=0.0, c_edge=None):
    """上が z=0、下が z=-h の六角柱（とがった方向が ±Y）。bevel>0 で上面のふちを面取り"""
    def pts(rr):
        return [(rr * math.cos(math.radians(90 + 60 * k)), rr * math.sin(math.radians(90 + 60 * k))) for k in range(6)]
    inner = pts(r - bevel)
    outer = pts(r)
    zt = 0.0
    top = [mb.vert(m, (x, y, zt), (0, 0, 1), c_top) for x, y in inner]
    cen = mb.vert(m, (0, 0, zt), (0, 0, 1), c_top)
    for k in range(6):
        mb.tri(cen, top[k], top[(k + 1) % 6])
    ze = zt
    if bevel > 0:
        ce = c_edge or c_top
        ze = zt - bevel
        for k in range(6):
            x0, y0 = inner[k]
            x1, y1 = inner[(k + 1) % 6]
            X0, Y0 = outer[k]
            X1, Y1 = outer[(k + 1) % 6]
            nn = ((X0 + X1) / 2, (Y0 + Y1) / 2, r * 0.9)
            a = mb.vert(m, (x0, y0, zt), nn, ce)
            b = mb.vert(m, (X0, Y0, ze), nn, ce)
            c = mb.vert(m, (X1, Y1, ze), nn, ce)
            d = mb.vert(m, (x1, y1, zt), nn, ce)
            mb.quad(a, b, c, d)
    for k in range(6):
        x0, y0 = outer[k]
        x1, y1 = outer[(k + 1) % 6]
        nn = ((x0 + x1) / 2, (y0 + y1) / 2, 0)
        a = mb.vert(m, (x0, y0, ze), nn, c_side)
        b = mb.vert(m, (x0, y0, -h), nn, c_side)
        cc = mb.vert(m, (x1, y1, -h), nn, c_side)
        d = mb.vert(m, (x1, y1, ze), nn, c_side)
        mb.quad(a, b, cc, d)


# ---------------- 色 ----------------
def rgb(r, g, b, a=1.0):
    return (r / 255, g / 255, b / 255, a)


def hexcol(s, default=(0.6, 0.6, 0.6, 1.0)):
    try:
        s = s.lstrip("#")
        return rgb(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except (ValueError, AttributeError, IndexError):
        return default


def mix(c1, c2, k):
    return tuple(c1[i] * (1 - k) + c2[i] * k for i in range(3)) + (c1[3] if len(c1) > 3 else 1.0,)


def shade(c, k):
    return tuple(min(1.0, max(0.0, v * k)) for v in c[:3]) + (c[3] if len(c) > 3 else 1.0,)


def alpha(c, a):
    return tuple(c[:3]) + (a,)


ELEMENT_COLORS = {
    "炎": rgb(225, 80, 45), "氷": rgb(140, 205, 245), "雷": rgb(245, 210, 50), "森": rgb(70, 160, 70),
    "闇": rgb(100, 60, 140), "光": rgb(250, 235, 180), "鋼": rgb(150, 160, 175), "砂": rgb(215, 180, 120),
    "海": rgb(40, 130, 190), "獣": rgb(150, 100, 60), "毒": rgb(140, 190, 50), "風": rgb(120, 220, 190),
    "岩": rgb(135, 120, 100), "桜": rgb(245, 160, 200), "竜": rgb(190, 40, 50), "機械": rgb(120, 130, 140),
    "亡霊": rgb(190, 180, 235), "星": rgb(60, 70, 160),
}
ELEMENT_GLOW = {
    "炎": rgb(255, 150, 60), "氷": rgb(170, 230, 255), "雷": rgb(255, 240, 110), "森": rgb(140, 240, 120),
    "闇": rgb(190, 120, 255), "光": rgb(255, 250, 200), "鋼": rgb(220, 230, 245), "砂": rgb(255, 220, 150),
    "海": rgb(100, 200, 255), "獣": rgb(255, 190, 120), "毒": rgb(190, 255, 90), "風": rgb(170, 255, 225),
    "岩": rgb(230, 200, 150), "桜": rgb(255, 190, 230), "竜": rgb(255, 110, 90), "機械": rgb(120, 230, 255),
    "亡霊": rgb(160, 230, 255), "星": rgb(255, 230, 120),
}
SKINS = [rgb(252, 224, 196), rgb(240, 200, 166), rgb(214, 170, 130), rgb(170, 122, 90), rgb(255, 232, 214)]
HAIRS = [rgb(46, 36, 32), rgb(98, 60, 34), rgb(214, 170, 88), rgb(226, 226, 232), rgb(172, 58, 44),
         rgb(62, 78, 140), rgb(34, 34, 44), rgb(236, 150, 180), rgb(90, 150, 100)]
BLACK = rgb(24, 22, 30)
WHITE = rgb(242, 242, 246)
STEEL = rgb(196, 204, 218)
DARKSTEEL = rgb(110, 118, 136)
WOOD = rgb(128, 84, 48)
LEATHER = rgb(96, 64, 44)
GOLDC = rgb(242, 196, 72)
COST_TRIM = {1: (150, 150, 160), 2: (60, 175, 95), 3: (60, 130, 230), 4: (175, 85, 225), 5: (240, 185, 40)}


def _hash(s):
    return zlib.crc32(s.encode("utf-8"))


def element_color(el):
    if el in ELEMENT_COLORS:
        return ELEMENT_COLORS[el]
    h = _hash(el)
    return rgb(80 + h % 160, 80 + (h >> 8) % 160, 80 + (h >> 16) % 160)


def element_glow(el):
    return ELEMENT_GLOW.get(el) or mix(element_color(el), WHITE, 0.5)


# ---------------- モデルの入れ物 ----------------
class Model:
    """組み立て済みモデル。body / arm_r / arm_l / leg_r / leg_l / aura を動かしてアニメーションする"""

    def __init__(self, root, body, arm_r, arm_l, leg_r, leg_l, aura, height, kind):
        self.root = root
        self.body = body
        self.arm_r = arm_r
        self.arm_l = arm_l
        self.leg_r = leg_r
        self.leg_l = leg_l
        self.aura = aura
        self.height = height
        self.kind = kind


class Parts:
    """パーツごとの形。腕・脚は肩・腰を原点にして作る"""

    def __init__(self):
        self.body = MB(True)
        self.arm_r = MB(True)
        self.arm_l = MB(True)
        self.leg_r = MB(True)
        self.leg_l = MB(True)
        self.glow = MB()          # 光る部分（ライトの影響を受けない）
        self.glow_r = MB()        # 右腕についた光る部分
        self.ghost = MB(True)     # 半透明の部分
        self.aura = MB()          # 周りを回る光
        self.shoulder_r = (0.25, 0, 0.8)
        self.shoulder_l = (-0.25, 0, 0.8)
        self.hip_r = (0.1, 0, 0.42)
        self.hip_l = (-0.1, 0, 0.42)
        self.height = 1.3


# ---------------- 人型の部品 ----------------
def face(mb, glow, z, y, style="normal", eye_col=None, skin=None):
    """顔（白目・黒目・ハイライト・ほお）"""
    ec = eye_col or rgb(40, 34, 50)
    if style == "visor":
        return
    for sx in (-1, 1):
        x = sx * 0.072
        sphere(mb, M((x, y - 0.012, z), (0, 0, 0), (0.8, 0.35, 1.15)), 0.042, ec, seg=10, rings=6, outline=False)
        sphere(mb, M((x - sx * 0.01, y + 0.004, z + 0.017)), 0.012, WHITE, seg=6, rings=4, outline=False)
        if skin is not None:
            box(mb, M((x + sx * 0.03, y - 0.01, z - 0.06)), 0.05, 0.02, 0.025, mix(skin, rgb(255, 120, 130), 0.45),
                outline=False)
    box(mb, M((0, y, z - 0.085)), 0.05, 0.02, 0.014, shade(skin or WHITE, 0.55), outline=False)


def hair(mb, h, head_z, hair_c, r=0.2):
    """髪型（ハッシュで5種類から選ぶ）"""
    style = h % 5
    sphere(mb, M((0, -0.03, head_z + 0.03)), r * 1.03, hair_c, seg=16, rings=6, top=0.55)
    sphere(mb, M((0, -0.07, head_z - 0.02)), r * 0.95, hair_c, seg=14, rings=6, top=0.75)
    if style == 0:      # つんつん
        for k in range(6):
            a = math.radians(-150 + k * 60)
            cyl(mb, M((math.cos(a) * 0.1, -0.05 + math.sin(a) * 0.08, head_z + 0.15), (k * 60, -35, 0)),
                0.06, 0.0, 0.16, hair_c, seg=6)
    elif style == 1:    # ポニーテール
        capsule(mb, M((0, -0.2, head_z - 0.02), (0, 30, 0)), 0.06, 0.22, hair_c, seg=10, r_top=0.035)
    elif style == 2:    # 前髪ぱっつん
        box(mb, M((0, 0.1, head_z + 0.1)), 0.34, 0.1, 0.08, hair_c)
    elif style == 3:    # 左右のおだんご
        for sx in (-1, 1):
            sphere(mb, M((sx * 0.17, -0.05, head_z + 0.12)), 0.075, hair_c, seg=10, rings=6)
    else:               # 長髪
        box(mb, M((0, -0.13, head_z - 0.17)), 0.34, 0.12, 0.3, hair_c)


def head(p, z, skin, hair_c, h, hair_on=True, face_style="normal", r=0.2):
    b = p.body
    sphere(b, M((0, 0, z)), r, skin, seg=18, rings=12)
    face(b, p.glow, z - 0.01, r * 0.93, face_style, skin=skin)
    for sx in (-1, 1):
        sphere(b, M((sx * r * 0.98, 0, z - 0.01)), 0.045, skin, seg=8, rings=5)
    if hair_on:
        hair(b, h, z, hair_c, r)


def torso(p, c1, c2, trim, robe=False, bulk=1.0, z0=0.42):
    b = p.body
    if robe:
        cyl(b, M((0, 0, 0.02)), 0.3 * bulk, 0.18 * bulk, z0 + 0.4, c1, seg=16)
        torus(b, M((0, 0, 0.05)), 0.29 * bulk, 0.035, c2, seg=20)
        torus(b, M((0, 0, z0 + 0.06)), 0.21 * bulk, 0.03, trim, seg=18)
    else:
        capsule(b, M((0, 0, z0 + 0.06), (0, 0, 0), (1.12 * bulk, 0.82 * bulk, 1)), 0.2, 0.2, c1, seg=16)
        torus(b, M((0, 0, z0 + 0.04), (0, 0, 0), (1.1 * bulk, 0.8 * bulk, 1)), 0.2, 0.035, c2, seg=20)
        box(b, M((0, 0.165 * bulk, z0 + 0.04)), 0.07, 0.02, 0.06, GOLDC, outline=False)   # バックル
    box(b, M((0, 0, z0 + 0.46)), 0.1, 0.1, 0.08, shade(c1, 0.8))                        # 首


def legs(p, pants, boots, short=False):
    ln = 0.3 if short else 0.36
    for mb, sx in ((p.leg_r, 1), (p.leg_l, -1)):
        capsule(mb, M((0, 0, -ln)), 0.07, ln - 0.02, pants, seg=10)
        capsule(mb, M((0, 0.03, -ln - 0.02), (0, -90, 0)), 0.075, 0.06, boots, seg=10)
    p.hip_r = (0.1, 0, ln + 0.08)
    p.hip_l = (-0.1, 0, ln + 0.08)


def arms(p, sleeve, hand, r=0.058, ln=0.3):
    for mb in (p.arm_r, p.arm_l):
        capsule(mb, M((0, 0, -ln)), r, ln, sleeve, seg=10)
        sphere(mb, M((0, 0.01, -ln - 0.03)), r * 1.12, hand, seg=10, rings=6)


def cape(p, c, z_top=0.86, ln=0.62, w=0.42):
    plate(p.body, M((0, -0.2, z_top - ln / 2), (0, 90 - 8, 0)),
          [(-w / 2, ln / 2), (w / 2, ln / 2), (w / 2 + 0.07, -ln / 2), (-w / 2 - 0.07, -ln / 2)], 0.03, c)
    for sx in (-1, 1):   # 留め具
        gem(p.body, M((sx * 0.16, 0.12, z_top - 0.04)), 0.028, GOLDC, outline=False)


def pauldrons(p, c, z=0.82, r=0.11):
    for sx in (-1, 1):
        sphere(p.body, M((sx * 0.25, 0, z), (0, 0, 0), (1.1, 1, 0.8)), r, c, seg=12, rings=7, top=0.6)


# ---------------- 武器 ----------------
def w_sword(mb, blade, hilt, gemc, big=False, glow_mb=None, glow=None):
    """右手の剣（手は z=-0.33 付近、刃は前方やや上）"""
    L = 0.78 if big else 0.56
    W = 0.12 if big else 0.075
    base = (0, 0.05, -0.34)
    mm = M(base, (0, -50, 0))   # 前向きに少し立てて持つ
    capsule(mb, mul(M((0, 0, -0.08)), mm), 0.028, 0.16, hilt, seg=8)
    box(mb, mul(M((0, 0, 0.1)), mm), 0.26 if big else 0.2, 0.06, 0.05, GOLDC)
    # 刃（幅＝X、長さ＝上向き）
    plate(mb, mul(M((0, 0, 0.12), (0, 90, 0)), mm),
          [(-W / 2, 0), (W / 2, 0), (W / 2, L * 0.82), (0, L), (-W / 2, L * 0.82)], 0.028, blade)
    gem(mb, mul(M((0, 0, -0.1)), mm), 0.03, gemc)
    if glow_mb is not None and glow is not None:
        box(glow_mb, mul(M((0, 0, 0.12 + L * 0.45)), mm), 0.012, 0.035, L * 0.8, glow, outline=False)


def w_spear(mb, shaft, head_c, flag=None):
    cyl(mb, M((0, 0.04, -0.95)), 0.024, 0.024, 1.55, shaft, seg=8)
    gem(mb, M((0, 0.04, 0.72), (0, 0, 0), (0.6, 0.6, 1.6)), 0.07, head_c)
    torus(mb, M((0, 0.04, 0.58)), 0.035, 0.018, GOLDC, seg=10, seg2=6)
    if flag is not None:
        plate(mb, M((0, 0.04, 0.42), (0, 0, 90)), [(0, 0), (0.0, -0.22), (0.24, -0.16), (0.2, -0.06)], 0.015,
              flag)


def w_staff(mb, glow_mb, wood, orb, glow_offset):
    cyl(mb, M((0, 0.05, -0.85)), 0.026, 0.032, 1.25, wood, seg=8)
    torus(mb, M((0, 0.05, 0.42), (0, 90, 0)), 0.1, 0.022, GOLDC, seg=16, seg2=6)
    gem(glow_mb, M((0, 0.05, 0.42)), 0.07, orb, outline=False)


def w_bow(mb, wood, string):
    n = 10
    R = 0.4
    for k in range(n):
        a0 = math.radians(-65 + 130 * k / n)
        a1 = math.radians(-65 + 130 * (k + 1) / n)
        x0, z0 = R * math.cos(a0), R * math.sin(a0)
        x1, z1 = R * math.cos(a1), R * math.sin(a1)
        ang = math.degrees(math.atan2(z1 - z0, x1 - x0))
        ln = math.hypot(x1 - x0, z1 - z0)
        th = 0.045 - 0.02 * abs(k - n / 2) / (n / 2)
        box(mb, M((0, 0.04 + (x0 + x1) / 2 - 0.22, -0.34 + (z0 + z1) / 2), (0, ang, 0)), th, ln + 0.012, th, wood)
    ys = 0.04 + R * math.cos(math.radians(65)) - 0.22
    zs = R * math.sin(math.radians(65))
    cyl(mb, M((0, ys, -0.34 - zs)), 0.006, 0.006, 2 * zs, string, seg=4, cap=False, outline=False)


def w_dagger(mb, blade):
    box(mb, M((0, 0.03, -0.35)), 0.04, 0.07, 0.04, BLACK)
    plate(mb, M((0, 0.2, -0.35), (0, 0, 90)), [(-0.03, -0.14), (0.03, -0.14), (0.02, 0.1), (0, 0.16), (-0.02, 0.1)],
          0.02, blade)


# ---------------- 見た目ごとの組み立て ----------------
def build_knight(p, c1, c2, trim, skin, hair_c, h, glow):
    legs(p, DARKSTEEL, STEEL)
    torso(p, STEEL, c1, trim, bulk=1.1)
    b = p.body
    plate(b, M((0, 0.19, 0.66), (0, 90, 0)), [(-0.12, 0.13), (0.12, 0.13), (0.12, -0.05), (0, -0.15), (-0.12, -0.05)],
          0.02, c1)                                                            # 胸の紋章
    pauldrons(p, trim, 0.84, 0.12)
    sphere(b, M((0, 0, 1.06)), 0.215, STEEL, seg=18, rings=12)                   # かぶと
    box(b, M((0, 0.19, 1.04)), 0.28, 0.04, 0.05, BLACK, outline=False)
    box(b, M((0, 0.2, 0.96)), 0.05, 0.03, 0.12, DARKSTEEL, outline=False)
    plate(b, M((0, -0.02, 1.3), (90, 0, 90)), [(-0.16, -0.02), (0.1, -0.06), (0.14, 0.08), (-0.1, 0.1)], 0.04, c1)
    arms(p, STEEL, DARKSTEEL, r=0.065)
    w_sword(p.arm_r, WHITE, LEATHER, c1, glow_mb=p.glow_r, glow=glow)
    al = p.arm_l
    plate(al, M((-0.04, 0.14, -0.26), (0, 90, 0)),
          [(-0.18, 0.22), (0.18, 0.22), (0.18, -0.04), (0, -0.28), (-0.18, -0.04)], 0.05, c1)
    plate(al, M((-0.04, 0.175, -0.26), (0, 90, 0)),
          [(-0.08, 0.12), (0.08, 0.12), (0.08, -0.03), (0, -0.13), (-0.08, -0.03)], 0.02, trim)


def build_warrior(p, c1, c2, trim, skin, hair_c, h, glow):
    legs(p, shade(c2, 0.8), LEATHER)
    torso(p, c1, LEATHER, trim)
    head(p, 1.05, skin, hair_c, h)
    b = p.body
    torus(b, M((0, 0, 1.12), (0, -8, 0)), 0.19, 0.03, trim, seg=20)            # はちまき
    capsule(b, M((0.05, -0.2, 1.1), (0, -70, 20)), 0.02, 0.18, trim, seg=6)
    sphere(b, M((0.27, 0, 0.82), (0, 0, 0), (1, 1, 0.8)), 0.11, DARKSTEEL, seg=12, rings=7, top=0.6)
    capsule(b, M((0, 0.02, 0.62), (0, 0, 35)), 0.03, 0.34, LEATHER, seg=6)       # たすき
    arms(p, skin, skin, r=0.062)
    w_sword(p.arm_r, STEEL, LEATHER, trim, big=True, glow_mb=p.glow_r, glow=glow)


def build_lancer(p, c1, c2, trim, skin, hair_c, h, glow):
    legs(p, shade(c2, 0.85), LEATHER)
    torso(p, c1, c2, trim)
    head(p, 1.05, skin, hair_c, h, hair_on=False)
    b = p.body
    sphere(b, M((0, 0, 1.08)), 0.21, STEEL, seg=18, rings=8, top=0.58)
    cyl(b, M((0, 0, 1.2)), 0.08, 0.0, 0.18, trim, seg=10)
    box(b, M((0, 0.19, 1.14)), 0.3, 0.05, 0.04, STEEL)
    pauldrons(p, STEEL, 0.82, 0.1)
    arms(p, c1, skin)
    w_spear(p.arm_r, WOOD, STEEL, flag=trim)


def build_archer(p, c1, c2, trim, skin, hair_c, h, glow):
    legs(p, shade(c2, 0.8), LEATHER)
    torso(p, c1, LEATHER, trim)
    head(p, 1.05, skin, hair_c, h, hair_on=True)
    b = p.body
    sphere(b, M((0, -0.04, 1.08)), 0.225, c2, seg=16, rings=8, top=0.6)         # フード
    cyl(b, M((0, -0.22, 1.02), (0, -60, 0)), 0.1, 0.0, 0.2, c2, seg=8)
    capsule(b, M((0.08, -0.2, 0.5), (0, 18, 0)), 0.07, 0.36, LEATHER, seg=10)   # 矢筒
    for dx in (-0.03, 0.02, 0.07):
        cyl(b, M((0.08 + dx, -0.24, 0.92), (0, 18, 0)), 0.01, 0.01, 0.12, WOOD, seg=4, outline=False)
        gem(b, M((0.08 + dx, -0.26, 1.05)), 0.02, WHITE, outline=False)
    arms(p, c1, skin)
    w_bow(p.arm_l, WOOD, WHITE)


def build_mage(p, c1, c2, trim, skin, hair_c, h, glow):
    torso(p, c1, trim, trim, robe=True)
    head(p, 1.05, skin, hair_c, h)
    b = p.body
    cyl(b, M((0, 0, 1.12)), 0.36, 0.34, 0.03, shade(c1, 0.9), seg=20)          # ぼうし
    cyl(b, M((0, 0.0, 1.14), (0, -10, 0)), 0.2, 0.0, 0.48, c1, seg=16)
    torus(b, M((0, 0, 1.17)), 0.19, 0.03, trim, seg=18)
    gem(p.glow, M((0, 0.19, 1.19)), 0.035, glow, outline=False)
    arms(p, c1, skin, r=0.065)
    w_staff(p.arm_r, p.glow_r, WOOD, glow, p.shoulder_r)
    p.hip_r = p.hip_l = None


def build_assassin(p, c1, c2, trim, skin, hair_c, h, glow):
    dark = shade(c1, 0.42)
    legs(p, dark, BLACK)
    torso(p, dark, c1, trim, bulk=0.92)
    head(p, 1.05, skin, hair_c, h)
    b = p.body
    box(b, M((0, 0.1, 0.97)), 0.32, 0.18, 0.12, dark)                          # 口元の布
    torus(b, M((0, 0, 1.12)), 0.2, 0.03, c1, seg=18)
    box(b, M((0, 0.2, 1.12)), 0.1, 0.02, 0.05, STEEL, outline=False)
    plate(b, M((0.06, -0.24, 1.06), (0, 0, 90)), [(0, 0), (0.55, -0.12), (0.52, -0.03)], 0.03, c1)
    arms(p, dark, skin)
    w_dagger(p.arm_r, STEEL)
    w_dagger(p.arm_l, STEEL)


def build_beast(p, c1, c2, trim, skin, hair_c, h, glow):
    fur = c1
    light = mix(fur, WHITE, 0.35)
    legs(p, shade(fur, 0.8), shade(fur, 0.55))
    torso(p, shade(fur, 0.9), LEATHER, trim, bulk=1.05)
    b = p.body
    sphere(b, M((0, 0, 1.05)), 0.21, fur, seg=18, rings=12)
    sphere(b, M((0, 0.14, 1.0), (0, 0, 0), (1, 0.9, 0.7)), 0.1, light, seg=12, rings=7)   # 鼻先
    box(b, M((0, 0.23, 1.02)), 0.06, 0.03, 0.04, BLACK, outline=False)
    face(b, p.glow, 1.08, 0.19, eye_col=rgb(230, 160, 40))
    for sx in (-1, 1):                                                           # 耳
        cyl(b, M((sx * 0.12, -0.02, 1.18), (0, 0, sx * 25)), 0.07, 0.0, 0.2, fur, seg=8)
        cyl(b, M((sx * 0.12, 0.0, 1.19), (0, 0, sx * 25)), 0.035, 0.0, 0.13, light, seg=6, outline=False)
    for k in range(5):                                                           # しっぽ
        sphere(b, M((0, -0.2 - k * 0.07, 0.42 + k * 0.06)), 0.07 - k * 0.006, fur if k < 4 else light, seg=10,
               rings=6)
    arms(p, shade(fur, 0.9), fur, r=0.066)
    for arm in (p.arm_r, p.arm_l):
        for dx in (-0.035, 0, 0.035):
            cyl(arm, M((dx, 0.05, -0.4), (0, 70, 0)), 0.016, 0.0, 0.1, WHITE, seg=5, outline=False)


def build_dragonkin(p, c1, c2, trim, skin, hair_c, h, glow):
    sc = c1
    belly = mix(sc, rgb(255, 220, 160), 0.55)
    legs(p, shade(sc, 0.8), shade(sc, 0.5))
    torso(p, sc, shade(sc, 0.6), trim, bulk=1.08)
    b = p.body
    capsule(b, M((0, 0.1, 0.5)), 0.12, 0.24, belly, seg=10)
    sphere(b, M((0, 0, 1.05)), 0.21, sc, seg=18, rings=12)
    sphere(b, M((0, 0.14, 1.0), (0, 0, 0), (0.9, 1.1, 0.6)), 0.11, shade(sc, 0.9), seg=12, rings=7)
    face(b, p.glow, 1.08, 0.19, eye_col=rgb(255, 200, 40))
    for sx in (-1, 1):
        cyl(b, M((sx * 0.1, -0.06, 1.17), (0, -35, sx * 20)), 0.05, 0.0, 0.26, GOLDC, seg=8)
        _wing(b, sx, 0.62, shade(sc, 0.72), pos=(sx * 0.12, -0.16, 0.8))
    for k in range(6):
        sphere(b, M((0, -0.18 - k * 0.08, 0.38 - k * 0.05)), 0.085 - k * 0.011, sc, seg=10, rings=6)
    arms(p, sc, belly, r=0.064)
    w_sword(p.arm_r, mix(trim, WHITE, 0.4), BLACK, glow, big=True, glow_mb=p.glow_r, glow=glow)


def build_robot(p, c1, c2, trim, skin, hair_c, h, glow):
    metal = mix(c1, STEEL, 0.55)
    darkm = shade(metal, 0.6)
    for mb in (p.leg_r, p.leg_l):
        box(mb, M((0, 0, -0.17)), 0.14, 0.16, 0.32, darkm)
        box(mb, M((0, 0.04, -0.37)), 0.18, 0.26, 0.08, BLACK)
        sphere(mb, M((0, 0, 0)), 0.07, BLACK, seg=8, rings=5)
    p.hip_r, p.hip_l = (0.12, 0, 0.42), (-0.12, 0, 0.42)
    b = p.body
    box(b, M((0, 0, 0.64)), 0.5, 0.32, 0.42, metal)
    box(b, M((0, 0, 0.44)), 0.38, 0.26, 0.08, darkm)
    box(p.glow, M((0, 0.165, 0.68)), 0.16, 0.012, 0.16, glow, outline=False)
    box(b, M((0, 0, 0.9)), 0.1, 0.1, 0.08, BLACK)
    box(b, M((0, 0, 1.06)), 0.34, 0.3, 0.26, metal)
    box(b, M((0, 0.155, 1.06)), 0.28, 0.02, 0.1, BLACK, outline=False)
    box(p.glow, M((0, 0.168, 1.06)), 0.22, 0.01, 0.045, glow, outline=False)
    cyl(b, M((0.11, 0, 1.19)), 0.012, 0.012, 0.16, BLACK, seg=4, outline=False)
    sphere(p.glow, M((0.11, 0, 1.37)), 0.035, rgb(255, 80, 80), seg=6, rings=4, outline=False)
    for sx in (-1, 1):
        cyl(b, M((sx * 0.3, 0, 0.8), (0, 0, 90 * sx)), 0.08, 0.08, 0.06, darkm, seg=10)
    for arm in (p.arm_r, p.arm_l):
        box(arm, M((0, 0, -0.16)), 0.12, 0.12, 0.3, shade(metal, 0.85))
        box(arm, M((0, 0.02, -0.36)), 0.15, 0.15, 0.12, BLACK)
    cyl(p.arm_r, M((0, 0.0, -0.36), (0, -90, 0)), 0.055, 0.055, 0.34, darkm, seg=10)
    torus(p.glow_r, M((0, 0.34, -0.36), (0, 90, 0)), 0.045, 0.012, glow, seg=12, seg2=5, outline=False)
    p.shoulder_r = (0.33, 0, 0.82)
    p.shoulder_l = (-0.33, 0, 0.82)


def build_ghost(p, c1, c2, trim, skin, hair_c, h, glow):
    pale = alpha(mix(c1, WHITE, 0.35), 0.78)
    g = p.ghost
    cyl(g, M((0, 0, 0.12)), 0.06, 0.3, 0.62, pale, seg=16, cap=False)
    sphere(g, M((0, 0, 0.72)), 0.3, pale, seg=16, rings=8, top=0.55)
    sphere(g, M((0, 0, 1.02)), 0.21, alpha(pale, 0.85), seg=16, rings=10)
    cyl(g, M((0, -0.02, 1.1), (0, -12, 0)), 0.25, 0.0, 0.32, alpha(shade(c1, 0.55), 0.9), seg=14)
    for sx in (-1, 1):
        sphere(p.glow, M((sx * 0.07, 0.19, 1.02)), 0.038, glow, seg=8, rings=5, outline=False)
    capsule(p.arm_r, M((0, 0, -0.3)), 0.05, 0.3, pale, seg=10)
    capsule(p.arm_l, M((0, 0, -0.3)), 0.05, 0.3, pale, seg=10)
    cyl(p.arm_r, M((0, 0.05, -0.9)), 0.02, 0.02, 1.28, BLACK, seg=6)          # 大鎌
    plate(p.arm_r, M((0, 0.05, 0.36), (0, 0, 90)), [(0, 0), (0.08, 0.03), (0.48, -0.12), (0.1, -0.08)], 0.02, STEEL)
    p.hip_r = p.hip_l = None


def build_goblin(p, c1, c2, trim, skin, hair_c, h, glow):
    green = rgb(118, 168, 76)
    legs(p, rgb(110, 84, 56), LEATHER, short=True)
    torso(p, rgb(128, 96, 64), LEATHER, trim, bulk=0.95, z0=0.34)
    b = p.body
    sphere(b, M((0, 0, 0.96)), 0.22, green, seg=18, rings=12)
    face(b, p.glow, 0.98, 0.2, eye_col=rgb(230, 40, 40), skin=green)
    for sx in (-1, 1):
        cyl(b, M((sx * 0.18, 0, 1.0), (0, 0, -sx * 75)), 0.07, 0.0, 0.26, green, seg=8)
    sphere(b, M((0, 0.21, 0.95), (0, 0, 0), (1, 1, 1.3)), 0.05, shade(green, 0.85), seg=8, rings=5)
    arms(p, green, green)
    cyl(p.arm_r, M((0, 0.05, -0.36), (0, -90, 0)), 0.04, 0.1, 0.5, WOOD, seg=8)
    for k in range(3):
        cyl(p.arm_r, M((0.05, 0.3 + k * 0.08, -0.33), (0, 0, -90)), 0.015, 0.0, 0.07, WHITE, seg=4, outline=False)
    p.shoulder_r, p.shoulder_l = (0.25, 0, 0.72), (-0.25, 0, 0.72)
    p.height = 1.2


def build_slime(p, c1, c2, trim, skin, hair_c, h, glow):
    col = rgb(96, 206, 128, 0.82)
    sphere(p.ghost, M((0, 0, 0.32), (0, 0, 0), (1.0, 1.0, 0.72)), 0.44, col, seg=18, rings=12)
    sphere(p.ghost, M((0, 0, 0.06), (0, 0, 0), (1.0, 1.0, 0.25)), 0.46, col, seg=18, rings=6)
    sphere(p.glow, M((-0.14, 0.18, 0.5)), 0.06, rgb(210, 255, 220, 0.9), seg=8, rings=5, outline=False)
    for sx in (-1, 1):
        sphere(p.body, M((sx * 0.13, 0.37, 0.4), (0, 0, 0), (1, 0.5, 1.3)), 0.06, BLACK, seg=10, rings=6,
               outline=False)
        sphere(p.body, M((sx * 0.13 - 0.02, 0.4, 0.43)), 0.018, WHITE, seg=6, rings=4, outline=False)
    box(p.body, M((0, 0.4, 0.3)), 0.1, 0.02, 0.025, BLACK, outline=False)
    p.shoulder_r = p.shoulder_l = (0, 0, 0.3)
    p.hip_r = p.hip_l = None
    p.height = 0.9


def build_wolf(p, c1, c2, trim, skin, hair_c, h, glow):
    fur = rgb(134, 136, 150)
    light = mix(fur, WHITE, 0.45)
    b = p.body
    capsule(b, M((0, -0.32, 0.52), (0, -90, 0)), 0.19, 0.6, fur, seg=14)
    sphere(b, M((0, 0.1, 0.52), (0, 0, 0), (0.9, 1, 0.9)), 0.17, light, seg=12, rings=8)
    sphere(b, M((0, 0.4, 0.7)), 0.17, fur, seg=16, rings=10)
    capsule(b, M((0, 0.47, 0.64), (0, -90, 0)), 0.08, 0.14, light, seg=10)
    sphere(b, M((0, 0.7, 0.66)), 0.04, BLACK, seg=8, rings=5, outline=False)
    for sx in (-1, 1):
        cyl(b, M((sx * 0.09, 0.36, 0.83), (0, 0, sx * 15)), 0.06, 0.0, 0.16, fur, seg=6)
        box(p.glow, M((sx * 0.08, 0.55, 0.74)), 0.045, 0.02, 0.03, rgb(255, 220, 60), outline=False)
    for k in range(4):
        sphere(b, M((0, -0.4 - k * 0.09, 0.58 + k * 0.05)), 0.07 - k * 0.008, fur if k < 3 else light, seg=10,
               rings=6)
    for mb, sx in ((p.leg_r, 1), (p.leg_l, -1)):
        capsule(mb, M((0, 0.18, -0.36)), 0.055, 0.34, shade(fur, 0.85), seg=8)
        capsule(mb, M((0, -0.3, -0.36)), 0.055, 0.34, shade(fur, 0.85), seg=8)
    p.hip_r, p.hip_l = (0.12, 0, 0.4), (-0.12, 0, 0.4)
    p.shoulder_r = p.shoulder_l = (0, 0.3, 0.5)
    p.height = 1.05


def build_golem(p, c1, c2, trim, skin, hair_c, h, glow):
    stone = rgb(128, 118, 108)
    moss = rgb(92, 142, 72)
    for mb in (p.leg_r, p.leg_l):
        box(mb, M((0, 0, -0.2)), 0.22, 0.24, 0.4, shade(stone, 0.85))
    p.hip_r, p.hip_l = (0.16, 0, 0.42), (-0.16, 0, 0.42)
    b = p.body
    box(b, M((0, 0, 0.74)), 0.7, 0.42, 0.56, stone)
    box(b, M((0, 0.05, 1.12)), 0.32, 0.3, 0.26, shade(stone, 0.92))
    box(b, M((0.2, 0.12, 0.98)), 0.16, 0.22, 0.08, moss)
    box(b, M((-0.25, -0.1, 1.03)), 0.2, 0.2, 0.06, moss)
    gem(p.glow, M((0, 0.23, 0.76)), 0.07, rgb(255, 170, 60), outline=False)
    for sx in (-1, 1):
        box(p.glow, M((sx * 0.07, 0.21, 1.14)), 0.06, 0.02, 0.04, rgb(255, 170, 60), outline=False)
    for arm in (p.arm_r, p.arm_l):
        box(arm, M((0, 0, -0.22)), 0.2, 0.2, 0.46, stone)
        box(arm, M((0, 0.02, -0.52)), 0.27, 0.27, 0.2, shade(stone, 0.8))
    p.shoulder_r = (0.46, 0, 0.92)
    p.shoulder_l = (-0.46, 0, 0.92)
    p.height = 1.35


def build_dragon(p, c1, c2, trim, skin, hair_c, h, glow):
    sc = rgb(176, 42, 48)
    belly = rgb(238, 196, 126)
    b = p.body
    sphere(b, M((0, -0.05, 0.58), (0, 0, 0), (0.85, 1.25, 0.8)), 0.4, sc, seg=16, rings=10)
    sphere(b, M((0, 0.12, 0.52), (0, 0, 0), (0.6, 0.8, 0.62)), 0.36, belly, seg=14, rings=8)
    capsule(b, M((0, 0.3, 0.74), (0, 38, 0)), 0.15, 0.36, sc, seg=12, r_top=0.12)
    capsule(b, M((0, 0.6, 1.08), (0, -90, 0)), 0.13, 0.26, sc, seg=12, r_top=0.1)
    for sx in (-1, 1):
        cyl(b, M((sx * 0.08, 0.52, 1.18), (0, -60, sx * 25)), 0.045, 0.0, 0.24, GOLDC, seg=6)
        box(p.glow, M((sx * 0.08, 0.72, 1.14)), 0.04, 0.02, 0.03, rgb(255, 230, 60), outline=False)
    for k in range(5):
        cyl(b, M((0, 0.3 - k * 0.2, 0.96 - k * 0.02 + (0.2 if k == 0 else 0)), (0, 0, 0)), 0.05, 0.0, 0.12, GOLDC,
            seg=5)
    for k in range(6):
        sphere(b, M((0, -0.44 - k * 0.12, 0.44 - k * 0.06)), 0.13 - k * 0.018, sc, seg=10, rings=6)
    for mb in (p.leg_r, p.leg_l):
        capsule(mb, M((0, 0.18, -0.3)), 0.08, 0.26, shade(sc, 0.8), seg=8)
        capsule(mb, M((0, -0.28, -0.3)), 0.08, 0.26, shade(sc, 0.8), seg=8)
    p.hip_r, p.hip_l = (0.22, 0, 0.36), (-0.22, 0, 0.36)
    for sx in (-1, 1):
        _wing(p.arm_r if sx > 0 else p.arm_l, sx, 1.0, shade(sc, 0.7))
    p.shoulder_r = (0.2, -0.05, 0.85)
    p.shoulder_l = (-0.2, -0.05, 0.85)
    p.height = 1.3


def _wing(mb, sx, size, c, pos=(0, 0, 0)):
    """横に広がるつばさ（sx=1で右、-1で左）"""
    pts = [(0, 0), (0.2, -0.15), (0.55, -0.2), (0.75, 0.1), (0.8, 0.55), (0.25, 0.25)]
    pts = [(x * size * sx, y * size) for x, y in pts]
    if sx < 0:
        pts.reverse()
    plate(mb, M(pos, (-sx * 25, 90, 0)), pts, 0.03, c)


BUILDERS = {"knight": build_knight, "warrior": build_warrior, "lancer": build_lancer, "archer": build_archer,
            "mage": build_mage, "assassin": build_assassin, "beast": build_beast, "dragonkin": build_dragonkin,
            "robot": build_robot, "ghost": build_ghost, "goblin": build_goblin, "slime": build_slime,
            "wolf": build_wolf, "golem": build_golem, "dragon": build_dragon}
LOOK_SCALE = {"golem": 1.3, "dragon": 1.25, "slime": 1.0, "wolf": 1.0, "goblin": 0.85}
FLOAT_LOOKS = {"ghost"}
HUMANOID = {"knight", "warrior", "lancer", "archer", "mage", "assassin", "beast", "dragonkin", "robot"}


def _decorate(p, look, cost, element, glow, trim):
    """コストに応じた豪華さ"""
    if look not in HUMANOID:
        return
    if cost >= 2:
        gem(p.glow, M((0, 0.2, 0.7) if look != "mage" else (0, 0.2, 0.78)), 0.04, glow, outline=False)
    if cost >= 3:
        for k in range(4 if cost < 5 else 6):
            a = 2 * math.pi * k / (4 if cost < 5 else 6)
            gem(p.aura, M((math.cos(a) * 0.48, math.sin(a) * 0.48, 0.25 + 0.2 * (k % 2))), 0.04, glow,
                outline=False)
    if cost >= 4 and look not in ("robot",):
        cape(p, shade(trim, 0.85))
    if cost >= 5:
        torus(p.glow, M((0, 0, 1.45 if look not in ("mage",) else 1.72)), 0.16, 0.02, rgb(255, 225, 120),
              seg=24, seg2=6, outline=False)


# ---------------- テンプレートの組み立て ----------------
_templates = {}


def _assemble(p, look):
    """Parts → 動かせるノードの木"""
    root = NodePath("tmpl")
    body = root.attachNewNode("body")

    def attach(parent, mb, name, glow=False, ghost=False):
        n = parent.attachNewNode(mb.node(name))
        if glow:
            n.setLightOff(1)
            n.setShaderOff(1)
        if ghost:
            n.setTransparency(TransparencyAttrib.MAlpha)
            n.setDepthWrite(False)
            n.setBin("transparent", 10)
        if mb.ol is not None and mb.ol.n:
            o = parent.attachNewNode(mb.ol.node(name + "_ol"))
            o.setLightOff(1)
            o.setShaderOff(1)
            if ghost:
                o.setTransparency(TransparencyAttrib.MAlpha)
                o.setAlphaScale(0.5)
        return n

    attach(body, p.body, "b")
    attach(body, p.glow, "glow", glow=True)
    attach(body, p.ghost, "ghost", ghost=True)
    aura = body.attachNewNode("aura")
    attach(aura, p.aura, "aura_g", glow=True)
    nodes = {}
    for key, mb, pos in (("arm_r", p.arm_r, p.shoulder_r), ("arm_l", p.arm_l, p.shoulder_l),
                         ("leg_r", p.leg_r, p.hip_r), ("leg_l", p.leg_l, p.hip_l)):
        if pos is None or mb.n == 0:
            if key.startswith("leg") and mb.n:
                attach(body, mb, key + "_g")
            continue
        piv = body.attachNewNode(key)
        piv.setPos(*pos)
        attach(piv, mb, key + "_g", ghost=look in ("ghost",))
        nodes[key] = piv
    ar = body.find("arm_r")
    if not ar.isEmpty() and p.glow_r.n:
        attach(ar, p.glow_r, "glow_r", glow=True)
    return root


def _template(look, key, element, cost):
    tk = (look, key, element, cost)
    t = _templates.get(tk)
    if t is not None:
        return t
    h = _hash(key)
    c1 = element_color(element)
    c2 = shade(mix(c1, WHITE, 0.15), 0.62)
    glow = element_glow(element)
    skin = SKINS[h % len(SKINS)]
    hair_c = HAIRS[(h >> 4) % len(HAIRS)]
    trim = rgb(*COST_TRIM.get(cost, (150, 95, 70)))
    p = Parts()
    BUILDERS.get(look, build_warrior)(p, c1, c2, trim, skin, hair_c, h >> 8, glow)
    _decorate(p, look, cost, element, glow, trim)
    root = _assemble(p, look)
    root.setPythonTag("height", p.height)
    _templates[tk] = root
    return root


_base_cache = {}


def _base_node(team_color, trim, star):
    k = (team_color, trim, star)
    n = _base_cache.get(k)
    if n is None:
        mb = MB()
        tc = rgb(*trim)
        cyl(mb, M((0, 0, 0.0)), 0.5, 0.48, 0.05, shade(tc, 0.45), seg=28, c_top=shade(tc, 0.75))
        cyl(mb, M((0, 0, 0.05)), 0.4, 0.37, 0.03, shade(tc, 0.9), seg=28, c_top=rgb(58, 62, 78))
        for k2 in range(6):
            a = 2 * math.pi * k2 / 6 + math.pi / 6
            gem(mb, M((math.cos(a) * 0.45, math.sin(a) * 0.45, 0.06)), 0.025, mix(tc, WHITE, 0.3))
        base = mb.node("base")
        mb2 = MB()
        ring(mb2, M((0, 0, 0.056)), 0.49, 0.6, rgb(*team_color, 0.9), seg=36)
        if star >= 3:
            ring(mb2, M((0, 0, 0.09)), 0.6, 0.66, rgb(255, 215, 90, 0.9), seg=36)
        team = mb2.node("team")
        n = (base, team)
        _base_cache[k] = n
    return n


def _finish(root, holder, tmpl, s, look):
    tmpl.getChild(0).copyTo(holder)
    body = holder.find("body")
    body.setZ(0.07)
    holder.setScale(s)
    h = tmpl.getPythonTag("height") or 1.3
    return Model(root, body, body.find("arm_r"), body.find("arm_l"), body.find("leg_r"), body.find("leg_l"),
                 body.find("aura"), h * s + 0.12, look)


def make_model(uid, info, star, team_color, is_creep=False, bare=False):
    """ユニット1体分のモデル（テンプレートをコピー）。bare=True で台座なし（絵を作る用）"""
    look = info.get("look") or ("slime" if is_creep else "warrior")
    element = info["traits"][0] if not is_creep else "_creep"
    cost = 0 if is_creep else info.get("cost", 1)
    trim = (150, 95, 70) if is_creep else COST_TRIM.get(cost, (150, 150, 160))
    tmpl = _template(look, uid, element, cost)
    root = NodePath("unit")
    if not bare:
        base_n, team_n = _base_node(tuple(team_color), trim, star)
        root.attachNewNode(base_n)
        tn = root.attachNewNode(team_n)
        tn.setLightOff(1)
        tn.setShaderOff(1)
        tn.setTransparency(TransparencyAttrib.MAlpha)
    holder = root.attachNewNode("holder")
    s = LOOK_SCALE.get(look, 1.0) * [1.0, 1.12, 1.25][star - 1]
    return _finish(root, holder, tmpl, s, look)


# ================= コントローラー（プレイヤーの分身） =================
def _chibi(p, outfit, outfit2, skin, hair_c, h, hair_on=True, robe=False):
    """頭の大きいかわいい体型"""
    if robe:
        cyl(p.body, M((0, 0, 0.0)), 0.3, 0.2, 0.62, outfit, seg=18)
        torus(p.body, M((0, 0, 0.04)), 0.29, 0.035, outfit2, seg=20)
    else:
        for mb in (p.leg_r, p.leg_l):
            capsule(mb, M((0, 0, -0.22)), 0.07, 0.2, shade(outfit2, 0.8), seg=10)
            capsule(mb, M((0, 0.03, -0.25), (0, -90, 0)), 0.075, 0.05, LEATHER, seg=10)
        p.hip_r, p.hip_l = (0.1, 0, 0.3), (-0.1, 0, 0.3)
        capsule(p.body, M((0, 0, 0.36), (0, 0, 0), (1.15, 0.9, 1)), 0.2, 0.16, outfit, seg=16)
    torus(p.body, M((0, 0, 0.4)), 0.22, 0.03, outfit2, seg=20)
    p.body_head_z = 0.95
    sphere(p.body, M((0, 0, 0.95)), 0.28, skin, seg=20, rings=14)
    face(p.body, p.glow, 0.93, 0.265, skin=skin)
    if hair_on:
        hair(p.body, h, 0.95, hair_c, 0.28)
    for mb in (p.arm_r, p.arm_l):
        capsule(mb, M((0, 0, -0.24)), 0.055, 0.24, outfit, seg=10)
        sphere(mb, M((0, 0.01, -0.27)), 0.065, skin, seg=10, rings=6)
    p.shoulder_r, p.shoulder_l = (0.24, 0, 0.66), (-0.24, 0, 0.66)
    p.height = 1.35


def ctrl_merchant(p, col, h):
    _chibi(p, col, GOLDC, SKINS[0], HAIRS[1], h, hair_on=False)
    b = p.body
    cyl(b, M((0, 0, 1.13)), 0.36, 0.36, 0.03, BLACK, seg=20)                      # シルクハット
    cyl(b, M((0, 0, 1.15)), 0.2, 0.2, 0.3, BLACK, seg=18)
    torus(b, M((0, 0, 1.2)), 0.2, 0.025, GOLDC, seg=18)
    box(b, M((0, 0.26, 0.85)), 0.2, 0.03, 0.05, HAIRS[1])                          # ひげ
    capsule(b, M((0, 0.06, 0.38), (0, 0, 0), (1.25, 1, 1)), 0.22, 0.05, col, seg=16)  # おなか
    sphere(p.arm_l, M((-0.05, 0.12, -0.35)), 0.14, rgb(160, 110, 60), seg=12, rings=8)  # 金貨袋
    for k in range(3):
        cyl(p.glow, M((0.35 + k * 0.03, 0.25, 0.1 + k * 0.035)), 0.07, 0.07, 0.025, GOLDC, seg=14, outline=False)
    gem(p.aura, M((0.4, 0, 0.9)), 0.05, GOLDC, outline=False)
    gem(p.aura, M((-0.4, 0, 0.7)), 0.05, GOLDC, outline=False)


def ctrl_sage(p, col, h):
    _chibi(p, col, rgb(230, 230, 240), SKINS[4], WHITE, h, hair_on=False, robe=True)
    b = p.body
    cyl(b, M((0, 0, 1.12)), 0.26, 0.0, 0.42, col, seg=16)
    cyl(b, M((0, 0.22, 0.42)), 0.02, 0.14, 0.4, WHITE, seg=10)                     # 長いひげ
    cyl(p.arm_r, M((0, 0.05, -0.7)), 0.025, 0.03, 1.2, WOOD, seg=8)
    gem(p.glow_r, M((0, 0.05, 0.55)), 0.08, rgb(150, 210, 255), outline=False)
    box(p.aura, M((0.45, 0.1, 0.95)), 0.2, 0.26, 0.05, rgb(250, 230, 170), outline=False)   # 浮かぶ本
    box(p.aura, M((0.45, 0.1, 0.98)), 0.21, 0.27, 0.02, rgb(130, 70, 50), outline=False)


def ctrl_smith(p, col, h):
    _chibi(p, rgb(120, 90, 70), col, SKINS[2], HAIRS[4], h)
    b = p.body
    plate(b, M((0, 0.2, 0.36), (0, 90, 0)), [(-0.16, 0.22), (0.16, 0.22), (0.18, -0.2), (-0.18, -0.2)], 0.02,
          LEATHER)                                                                  # 前かけ
    sphere(b, M((0, 0.2, 0.72), (0, 0, 0), (1.2, 0.8, 1.0)), 0.16, HAIRS[4], seg=12, rings=8)  # ひげ
    box(b, M((0, 0.1, 1.2)), 0.3, 0.2, 0.06, DARKSTEEL)                            # ゴーグル
    for sx in (-1, 1):
        torus(b, M((sx * 0.08, 0.22, 1.12), (0, 90, 0)), 0.045, 0.02, DARKSTEEL, seg=12, seg2=5)
    cyl(p.arm_r, M((0, 0.05, -0.6)), 0.025, 0.025, 0.5, WOOD, seg=8)              # ハンマー
    box(p.arm_r, M((0, 0.05, -0.08)), 0.28, 0.14, 0.14, DARKSTEEL)
    box(p.glow_r, M((0.15, 0.05, -0.08)), 0.02, 0.1, 0.1, rgb(255, 150, 60), outline=False)


def ctrl_summoner(p, col, h):
    _chibi(p, col, rgb(250, 220, 255), SKINS[4], HAIRS[7], h, robe=True)
    b = p.body
    for sx in (-1, 1):
        cyl(b, M((sx * 0.15, -0.02, 1.16), (0, -20, sx * 25)), 0.05, 0.0, 0.18, rgb(250, 220, 255), seg=8)
    cyl(p.arm_r, M((0, 0.05, -0.6)), 0.022, 0.028, 1.0, rgb(230, 230, 250), seg=8)
    gem(p.glow_r, M((0, 0.05, 0.46)), 0.09, rgb(220, 150, 255), outline=False)
    for k in range(3):
        a = 2 * math.pi * k / 3
        sphere(p.aura, M((math.cos(a) * 0.5, math.sin(a) * 0.5, 0.8)), 0.07, rgb(200, 140, 255), seg=10, rings=6,
               outline=False)


def ctrl_seer(p, col, h):
    _chibi(p, col, GOLDC, SKINS[1], HAIRS[6], h, robe=True)
    b = p.body
    sphere(b, M((0, -0.03, 0.98)), 0.3, col, seg=18, rings=10, top=0.6)          # フード
    cyl(b, M((0, -0.2, 1.1), (0, -55, 0)), 0.14, 0.0, 0.3, col, seg=10)
    for k in range(4):
        gem(b, M((math.cos(k) * 0.1 - 0.05, 0.24, 0.62 + 0.04 * k)), 0.022, GOLDC, outline=False)
    sphere(p.glow, M((0, 0.4, 0.45)), 0.16, rgb(170, 220, 255, 0.95), seg=16, rings=10, outline=False)  # 水晶玉
    cyl(b, M((0, 0.4, 0.26)), 0.1, 0.06, 0.08, GOLDC, seg=12)
    for k in range(5):
        a = 2 * math.pi * k / 5
        gem(p.aura, M((math.cos(a) * 0.55, math.sin(a) * 0.55, 1.0)), 0.03, rgb(255, 240, 170), outline=False)


def ctrl_guardian(p, col, h):
    _chibi(p, STEEL, col, SKINS[2], HAIRS[0], h, hair_on=False)
    b = p.body
    sphere(b, M((0, 0, 0.97)), 0.3, STEEL, seg=20, rings=14)
    box(b, M((0, 0.27, 0.95)), 0.32, 0.04, 0.06, BLACK, outline=False)
    capsule(b, M((0, -0.02, 1.25), (0, -25, 0)), 0.05, 0.22, col, seg=8, r_top=0.02)
    pauldrons(p, col, 0.66, 0.13)
    plate(p.arm_l, M((-0.04, 0.18, -0.2), (0, 90, 0)),
          [(-0.24, 0.3), (0.24, 0.3), (0.24, -0.1), (0, -0.36), (-0.24, -0.1)], 0.06, col)     # 大盾
    plate(p.arm_l, M((-0.04, 0.225, -0.2), (0, 90, 0)),
          [(-0.11, 0.16), (0.11, 0.16), (0.11, -0.04), (0, -0.18), (-0.11, -0.04)], 0.02, GOLDC)
    cyl(p.arm_r, M((0, 0.05, -0.6)), 0.03, 0.03, 1.0, WOOD, seg=8)
    gem(p.arm_r, M((0, 0.05, 0.45), (0, 0, 0), (0.6, 0.6, 1.8)), 0.07, STEEL)


def ctrl_strategist(p, col, h):
    _chibi(p, col, rgb(240, 240, 240), SKINS[0], HAIRS[6], h, robe=True)
    b = p.body
    box(b, M((0, 0, 1.22)), 0.46, 0.46, 0.03, BLACK)                             # 軍師の帽子
    cyl(b, M((0, 0, 1.12)), 0.2, 0.18, 0.12, BLACK, seg=16)
    capsule(b, M((0.18, -0.25, 0.3)), 0.02, 0.9, WOOD, seg=6)                    # 旗
    plate(b, M((0.18, -0.25, 1.0), (0, 0, 90)), [(0, 0), (0, -0.4), (0.32, -0.34), (0.32, -0.06)], 0.02, col)
    for k in range(5):                                                           # 扇
        a = math.radians(-50 + k * 25)
        plate(p.arm_r, M((0, 0.1, -0.32), (0, 0, 90)),
              [(0, 0), (math.cos(a) * 0.26 - 0.03, math.sin(a) * 0.26), (math.cos(a) * 0.26 + 0.03, math.sin(a) * 0.26)],
              0.01, WHITE)
    gem(p.aura, M((0.45, 0.2, 0.9)), 0.05, rgb(140, 200, 255), outline=False)


def ctrl_alchemist(p, col, h):
    _chibi(p, col, rgb(90, 70, 60), SKINS[3], HAIRS[8], h)
    b = p.body
    box(b, M((0, 0.1, 1.15)), 0.5, 0.2, 0.06, LEATHER)                          # ゴーグル
    for sx in (-1, 1):
        torus(b, M((sx * 0.1, 0.24, 1.1), (0, 90, 0)), 0.055, 0.022, GOLDC, seg=12, seg2=5)
        sphere(p.glow, M((sx * 0.1, 0.25, 1.1)), 0.045, rgb(140, 255, 180, 0.9), seg=8, rings=5, outline=False)
    capsule(b, M((0, 0, 0.44), (0, 0, 40), (1, 1, 1)), 0.025, 0.4, LEATHER, seg=6)
    for k, c in enumerate((rgb(255, 90, 120), rgb(90, 200, 255), rgb(160, 255, 90))):
        sphere(p.glow, M((-0.12 + k * 0.12, 0.2, 0.3)), 0.04, c, seg=8, rings=5, outline=False)
    cyl(p.arm_r, M((0, 0.08, -0.36)), 0.07, 0.03, 0.18, rgb(220, 240, 255, 0.9), seg=12)    # フラスコ
    sphere(p.glow_r, M((0, 0.08, -0.33)), 0.075, rgb(140, 255, 120), seg=10, rings=6, outline=False)
    for k in range(3):
        sphere(p.aura, M((0.3, 0.3, 0.6 + k * 0.18)), 0.03 + k * 0.01, rgb(160, 255, 140, 0.9), seg=8, rings=5,
               outline=False)


CONTROLLER_BUILDERS = {"merchant": ctrl_merchant, "sage": ctrl_sage, "smith": ctrl_smith,
                       "summoner": ctrl_summoner, "seer": ctrl_seer, "guardian": ctrl_guardian,
                       "strategist": ctrl_strategist, "alchemist": ctrl_alchemist}
_ctrl_templates = {}


def make_controller(cid, info, team_color, scale=1.25, bare=False):
    """コントローラー（プレイヤーの分身）のモデル"""
    look = info.get("look") or "merchant"
    col = hexcol(info.get("color", ""), rgb(120, 120, 200))
    key = (look, cid, info.get("color", ""))
    tmpl = _ctrl_templates.get(key)
    if tmpl is None:
        p = Parts()
        CONTROLLER_BUILDERS.get(look, ctrl_merchant)(p, col, _hash(cid) >> 8)
        tmpl = _assemble(p, look)
        tmpl.setPythonTag("height", p.height)
        _ctrl_templates[key] = tmpl
    root = NodePath("controller")
    if not bare:
        mb = MB()
        cyl(mb, M((0, 0, 0)), 0.62, 0.58, 0.08, shade(col, 0.45), seg=32, c_top=shade(col, 0.7))
        root.attachNewNode(mb.node("pedestal"))
        mb2 = MB()
        ring(mb2, M((0, 0, 0.085)), 0.6, 0.7, rgb(*team_color, 0.9), seg=40)
        tn = root.attachNewNode(mb2.node("team"))
        tn.setLightOff(1)
        tn.setShaderOff(1)
        tn.setTransparency(TransparencyAttrib.MAlpha)
    holder = root.attachNewNode("holder")
    m = _finish(root, holder, tmpl, 1.1 * scale, look)
    m.body.setZ(0.09)
    return m
