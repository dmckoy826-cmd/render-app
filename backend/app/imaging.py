"""Pillow-based imaging: thumbnails, procedural swatches, structure previews and the
simulated ("mock engine") renders.

The scene renderer draws every part of an analyzed model as an isometric (or front/top)
box and maps each assigned finish image onto the faces using the finish's real-world
swatch size, so texture scale in the mock render matches what V-Ray would produce.
"""
from __future__ import annotations

import functools
import heapq
import math
import random
from typing import Callable, Optional

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ISO_C = 0.8660254  # cos(30°)
ISO_S = 0.5        # sin(30°)
NEUTRAL = (154, 149, 142)  # parts with no finish assigned


# --------------------------------------------------------------------------- #
# Thumbnails
# --------------------------------------------------------------------------- #

def make_thumbnail(src: str, dst: str, size: int = 256) -> None:
    im = Image.open(src).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    im.save(dst, "JPEG", quality=86)


# --------------------------------------------------------------------------- #
# Procedural swatch textures (used by the demo seed)
# --------------------------------------------------------------------------- #

def make_procedural_finish(kind: str, size: int = 768) -> Image.Image:
    rng = random.Random(abs(hash(kind)) % 100000)
    if kind.startswith("wood"):
        return _wood(kind, size, rng)
    if kind.startswith("felt"):
        return _felt(kind, size, rng)
    if kind.startswith("matte"):
        return _matte(kind, size, rng)
    if kind.startswith("metal"):
        return _metal(kind, size, rng)
    return _matte(kind, size, rng)


_WOOD_PALETTES = {
    "wood-walnut": ((111, 74, 47), (66, 41, 24), (152, 108, 68)),
    "wood-oak":    ((201, 169, 122), (158, 126, 82), (226, 200, 158)),
    "wood-maple":  ((227, 201, 154), (196, 168, 118), (242, 224, 186)),
    "wood-cherry": ((138, 74, 53), (94, 46, 30), (176, 108, 80)),
}
_FELT_PALETTES = {
    "felt-charcoal": ((59, 62, 66), (92, 96, 101), (34, 36, 39)),
    "felt-dove":     ((203, 207, 210), (232, 235, 237), (168, 173, 177)),
}
_MATTE_PALETTES = {
    "matte-black": ((35, 37, 42), (52, 55, 60), (22, 23, 26)),
}
_METAL_PALETTES = {
    "metal-steel":  ((172, 178, 183), (214, 218, 221), (128, 133, 138)),
    "metal-bronze": ((140, 106, 79), (178, 142, 108), (96, 70, 50)),
}


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _wood(kind: str, size: int, rng: random.Random) -> Image.Image:
    base, dark, light = _WOOD_PALETTES.get(kind, _WOOD_PALETTES["wood-walnut"])
    img = Image.new("RGB", (size, size), base)
    dr = ImageDraw.Draw(img, "RGBA")
    n = 170
    for i in range(n):
        y0 = rng.uniform(-10, size + 10)
        amp = rng.uniform(1.5, 9)
        freq = rng.uniform(0.004, 0.02)
        phase = rng.uniform(0, math.tau)
        t = rng.random()
        col = _lerp(dark, light, t) + (rng.randint(18, 60),)
        wdt = rng.choice([1, 1, 1, 2, 2, 3])
        pts = []
        x = -5
        while x <= size + 5:
            y = y0 + amp * math.sin(x * freq + phase) + amp * 0.4 * math.sin(x * freq * 2.7 + phase * 1.7)
            pts.append((x, y))
            x += 8
        for j in range(len(pts) - 1):
            dr.line([pts[j], pts[j + 1]], fill=col, width=wdt)
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    noise = Image.effect_noise((size, size), 26).convert("L")
    blotch = Image.effect_noise((size, size), 40).convert("L").filter(ImageFilter.GaussianBlur(28))
    img = ImageChops.soft_light(img, noise.convert("RGB"))
    img = ImageChops.soft_light(img, blotch.convert("RGB"))
    return img


def _felt(kind: str, size: int, rng: random.Random) -> Image.Image:
    base, hi, lo = _FELT_PALETTES.get(kind, _FELT_PALETTES["felt-charcoal"])
    img = Image.new("RGB", (size, size), base)
    noise = Image.effect_noise((size, size), 64).convert("L")
    img = ImageChops.soft_light(img, noise.convert("RGB"))
    dr = ImageDraw.Draw(img, "RGBA")
    for _ in range(size * 14):
        x, y = rng.randrange(size), rng.randrange(size)
        c = hi if rng.random() < 0.5 else lo
        dr.point((x, y), fill=c + (rng.randint(30, 90),))
    img = img.filter(ImageFilter.GaussianBlur(0.4))
    return img


def _matte(kind: str, size: int, rng: random.Random) -> Image.Image:
    base, hi, lo = _MATTE_PALETTES.get(kind, _MATTE_PALETTES["matte-black"])
    img = Image.new("RGB", (size, size), base)
    noise = Image.effect_noise((size, size), 14).convert("L")
    img = ImageChops.soft_light(img, noise.convert("RGB"))
    blotch = Image.effect_noise((size, size), 20).convert("L").filter(ImageFilter.GaussianBlur(40))
    img = ImageChops.soft_light(img, blotch.convert("RGB"))
    return img


def _metal(kind: str, size: int, rng: random.Random) -> Image.Image:
    base, hi, lo = _METAL_PALETTES.get(kind, _METAL_PALETTES["metal-steel"])
    img = Image.new("RGB", (size, size), base)
    dr = ImageDraw.Draw(img, "RGBA")
    for y in range(size):
        t = rng.random()
        col = _lerp(lo, hi, t) + (rng.randint(24, 70),)
        dr.line([(0, y), (size, y)], fill=col, width=1)
    sheen = Image.new("L", (size, size))
    ds = ImageDraw.Draw(sheen)
    for y in range(size):
        v = int(128 + 60 * math.sin(y / size * math.pi * 2))
        ds.line([(0, y), (size, y)], fill=v)
    sheen = sheen.filter(ImageFilter.GaussianBlur(6))
    img = ImageChops.soft_light(img, sheen.convert("RGB"))
    img = img.filter(ImageFilter.GaussianBlur(0.35))
    return img


# --------------------------------------------------------------------------- #
# Scene rendering
# --------------------------------------------------------------------------- #

def _hexrgb(h: str, scale: float = 1.0):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(max(0, min(255, int(c * scale))) for c in (r, g, b))


def _background(w: int, h: int, top, bottom) -> Image.Image:
    base = Image.new("RGB", (w, h))
    dr = ImageDraw.Draw(base)
    for y in range(h):
        t = y / max(1, h - 1)
        dr.line([(0, y), (w, y)], fill=_lerp(top, bottom, t))
    img = base.convert("RGBA")
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dg = ImageDraw.Draw(glow)
    dg.ellipse([w * 0.08, h * 0.02, w * 0.92, h * 0.86], fill=(255, 250, 240, 16))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    return Image.alpha_composite(img, glow)


def _tile(tex: Image.Image, tile_w: float, tile_h: float, w: int, h: int) -> Image.Image:
    tw, th = max(6, int(round(tile_w))), max(6, int(round(tile_h)))
    t = tex if tex.size == (tw, th) else tex.resize((tw, th))
    cols, rows = max(1, math.ceil(w / tw)), max(1, math.ceil(h / th))
    if cols == 1 and rows == 1:
        canvas = Image.new("RGB", (max(tw, w), max(th, h)))
        canvas.paste(t, (0, 0))
        return canvas.crop((0, 0, w, h))
    canvas = Image.new("RGB", (cols * tw, rows * th))
    for r in range(rows):
        for c in range(cols):
            canvas.paste(t, (c * tw, r * th))
    return canvas.crop((0, 0, w, h))


def _shade_overlay(base: Image.Image, quad, shade: int) -> None:
    if not shade:
        return
    ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
    col = (255, 255, 255, shade) if shade > 0 else (0, 0, 0, -shade)
    ImageDraw.Draw(ov).polygon([tuple(p) for p in quad], fill=col)
    base.alpha_composite(ov)


def _draw_face_textured(base: Image.Image, quad, tex: Image.Image, ppi: float,
                        sw_w: float, sw_h: float, lu: float, lv: float, shade: int) -> None:
    (ax, ay), (bx, by), (_, _), (dx, dy) = quad
    ux, uy = bx - ax, by - ay
    vx, vy = dx - ax, dy - ay
    w = max(4, math.ceil(lu * ppi))
    h = max(4, math.ceil(lv * ppi))
    tiled = _tile(tex, sw_w * ppi, sw_h * ppi, w, h)
    det = ux * vy - uy * vx
    if abs(det) < 1e-9:
        return
    ia, ib = vy / det, -vx / det
    ic_, id_ = -uy / det, ux / det
    ie = -(ia * ax + ib * ay)
    iff = -(ic_ * ax + id_ * ay)
    warped = tiled.transform(base.size, Image.Transform.AFFINE,
                             (ia, ib, ie, ic_, id_, iff),
                             resample=Image.Resampling.BILINEAR)
    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).polygon([tuple(p) for p in quad], fill=255)
    base.paste(warped, (0, 0), mask)
    _shade_overlay(base, quad, shade)
    dr = ImageDraw.Draw(base, "RGBA")
    dr.line([tuple(p) for p in quad] + [tuple(quad[0])], fill=(10, 10, 12, 120), width=2)


def _draw_face_flat(base: Image.Image, quad, color, shade: int) -> None:
    factor = 1.0 + shade / 190.0
    fill = _hexrgb("#%02x%02x%02x" % color, factor) if isinstance(color, tuple) else _hexrgb(color, factor)
    dr = ImageDraw.Draw(base, "RGBA")
    pts = [tuple(p) for p in quad]
    dr.polygon(pts, fill=fill + (255,))
    dr.line(pts + [pts[0]], fill=(10, 10, 12, 130), width=2)


def _bbox_overlap(A: dict, B: dict) -> bool:
    qa, qb = A["quad"], B["quad"]
    ax0, ax1 = min(q[0] for q in qa), max(q[0] for q in qa)
    ay0, ay1 = min(q[1] for q in qa), max(q[1] for q in qa)
    bx0, bx1 = min(q[0] for q in qb), max(q[0] for q in qb)
    by0, by1 = min(q[1] for q in qb), max(q[1] for q in qb)
    return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)


def _occludes(A: dict, B: dict, view) -> bool:
    """True if face A occludes any sample point of face B (centroid + corners):
    the view ray from that point toward the camera enters A's plane inside A."""
    ai = A["axis"]
    d = view[ai]
    if abs(d) < 1e-9:
        return False
    u, v = A["uv"]
    e = 1e-6
    for q in (B["centroid"], *B["corners3d"]):
        t = (A["plane"] - q[ai]) / d
        if t <= 1e-6:
            continue
        r = [q[i] + t * view[i] for i in range(3)]
        if (A["u0"] - e <= r[u] <= A["u1"] + e) and (A["v0"] - e <= r[v] <= A["v1"] + e):
            return True
    return False


def _face_cmp(A: dict, B: dict, view) -> int:
    bydepth = -1 if A["depth"] < B["depth"] else (1 if A["depth"] > B["depth"] else 0)
    qa, qb = A["quad"], B["quad"]
    ax0, ax1 = min(p[0] for p in qa), max(p[0] for p in qa)
    ay0, ay1 = min(p[1] for p in qa), max(p[1] for p in qa)
    bx0, bx1 = min(p[0] for p in qb), max(p[0] for p in qb)
    by0, by1 = min(p[1] for p in qb), max(p[1] for p in qb)
    if ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0:
        return bydepth
    if _occludes(A, B, view):
        return 1
    if _occludes(B, A, view):
        return -1
    return bydepth


def _camera(camera: str, extents, W: int, H: int, pad: float = 0.80):
    """Returns (proj, S, part_faces, view). part_faces(mn, mx) yields all six
    axis-aligned faces of a box as dicts carrying screen quad, texture extents,
    shading and 3D plane data used for exact pairwise occlusion ordering."""
    (x0, y0, z0), (x1, y1, z1) = extents
    ex, ey, ez = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6), max(z1 - z0, 1e-6)

    if camera == "front":
        S = min(W * pad / ex, H * pad / ez)
        ox = W / 2 - S * (x0 + x1) / 2
        oy = H / 2 + S * (z0 + z1) / 2
        proj = lambda p: (ox + p[0] * S, oy - p[2] * S)
        view = (0.0, -1.0, 0.0)
        shades = {("y", 0): -6, ("z", 1): 10, ("x", 1): -22,
                  ("x", 0): -22, ("y", 1): 0, ("z", 0): 0}
        visible = {("y", 0)}
    elif camera == "top":
        S = min(W * pad / ex, H * pad / ey)
        ox = W / 2 - S * (x0 + x1) / 2
        oy = H / 2 - S * (y0 + y1) / 2
        proj = lambda p: (ox + p[0] * S, oy + p[1] * S)
        view = (0.0, 0.0, 1.0)
        shades = {("z", 1): 12, ("z", 0): 0, ("y", 0): -18,
                  ("y", 1): -18, ("x", 0): -18, ("x", 1): -18}
        visible = {("z", 1)}
    else:  # iso — Y is mirrored in view space so the camera sits at world (+x, -y, +z)
        w_in = (ex + ey) * ISO_C
        h_in = (ex + ey) * ISO_S + ez
        S = min(W * pad / w_in, H * pad / h_in)
        vcx, vcy, vcz = (x0 + x1) / 2, -(y0 + y1) / 2, (z0 + z1) / 2
        ox = W / 2 - (vcx - vcy) * ISO_C * S
        oy = H / 2 + vcz * S - (vcx + vcy) * ISO_S * S
        _proj = lambda p: (ox + (p[0] - p[1]) * ISO_C * S,
                           oy + (p[0] + p[1]) * ISO_S * S - p[2] * S)
        proj = lambda p: _proj((p[0], -p[1], p[2]))
        view = (1.0, -1.0, 1.0)
        shades = {("y", 0): -62, ("x", 1): -28, ("z", 1): 26,
                  ("y", 1): 0, ("x", 0): 0, ("z", 0): 0}
        visible = {("y", 0), ("x", 1), ("z", 1)}

    AXES = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}
    AIDX = {"x": 0, "y": 1, "z": 2}

    def part_faces(mn, mx):
        out = []
        for axis in ("x", "y", "z"):
            u, v = AXES[axis]
            ai = AIDX[axis]
            for which in (0, 1):
                if (axis, which) not in visible:
                    continue  # back-face culling
                plane = mn[ai] if which == 0 else mx[ai]
                corner = [0.0, 0.0, 0.0]
                corner[ai] = plane
                corner[u], corner[v] = mn[u], mn[v]
                a = tuple(corner)
                c2 = list(corner)
                c2[u] = mx[u]
                b = tuple(c2)
                c3 = list(corner)
                c3[v] = mx[v]
                d = tuple(c3)
                pa, pb, pd = proj(a), proj(b), proj(d)
                cc = tuple(b[i] + d[i] - a[i] for i in range(3))
                quad = [pa, pb, (pb[0] + pd[0] - pa[0], pb[1] + pd[1] - pa[1]), pd]
                cen = [0.0, 0.0, 0.0]
                cen[ai] = plane
                cen[u] = (mn[u] + mx[u]) / 2
                cen[v] = (mn[v] + mx[v]) / 2
                out.append({
                    "quad": quad,
                    "lu": mx[u] - mn[u],
                    "lv": mx[v] - mn[v],
                    "shade": shades.get((axis, which), 0),
                    "axis": ai,
                    "plane": plane,
                    "uv": (u, v),
                    "u0": mn[u], "u1": mx[u], "v0": mn[v], "v1": mx[v],
                    "centroid": tuple(cen),
                    "corners3d": (a, b, cc, d),
                    "depth": sum(c * w for c, w in zip(cen, view)),
                })
        return out

    return proj, S, part_faces, view


def render_scene(structure: dict,
                 finish_lookup: Optional[dict] = None,
                 layer_colors: Optional[dict] = None,
                 size: tuple[int, int] = (1600, 1200),
                 camera: str = "iso",
                 textured: bool = True,
                 watermark: str = "") -> Image.Image:
    """Draw the model. finish_lookup: {layer_name: (PIL.Image, swatch_w_in, swatch_h_in)}."""
    W, H = size
    finish_lookup = finish_lookup or {}
    layer_colors = layer_colors or {}
    parts = structure.get("parts", [])
    ext = structure.get("extents")
    if not ext and parts:
        mins = [p["bbox"]["min"] for p in parts]
        maxs = [p["bbox"]["max"] for p in parts]
        ext = {"min": [min(m[i] for m in mins) for i in range(3)],
               "max": [max(m[i] for m in maxs) for i in range(3)]}
    if not ext:
        ext = {"min": [0, 0, 0], "max": [10, 10, 10]}
    extents = (tuple(ext["min"]), tuple(ext["max"]))

    base = _background(W, H, (35, 38, 43), (15, 16, 19))
    proj, S, part_faces, view = _camera(camera, extents, W, H)

    # floor shadow
    if camera == "iso":
        (x0, y0, z0), (x1, y1, _) = extents
        foot = [proj((x0, -y1, z0)), proj((x1, -y1, z0)), proj((x1, -y0, z0)), proj((x0, -y0, z0))]
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ds = ImageDraw.Draw(sh)
        cx = sum(p[0] for p in foot) / 4
        cy = sum(p[1] for p in foot) / 4
        big = [(cx + (p[0] - cx) * 1.14, cy + (p[1] - cy) * 1.14 + 8) for p in foot]
        ds.polygon(big, fill=(0, 0, 0, 96))
        sh = sh.filter(ImageFilter.GaussianBlur(22))
        base.alpha_composite(sh)
        sh2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(sh2).polygon(foot, fill=(0, 0, 0, 70))
        sh2 = sh2.filter(ImageFilter.GaussianBlur(6))
        base.alpha_composite(sh2)

    ppi = min(S, 120.0)
    all_faces: list[dict] = []
    for part in parts:
        mn = part["bbox"]["min"]
        mx = part["bbox"]["max"]
        layer = part.get("layer") or ""
        fin = finish_lookup.get(layer)
        color = layer_colors.get(layer) or NEUTRAL
        if isinstance(color, str):
            color = _hexrgb(color)
        for f in part_faces(mn, mx):
            f["fin"] = fin
            f["color"] = tuple(color)
            all_faces.append(f)
    # Exact painter ordering: occlusion constraints form a DAG (occluder paints
    # later); face depth along the view is only a tie-break priority.
    n = len(all_faces)
    adj: list[list[int]] = [[] for _ in range(n)]
    indeg = [0] * n
    for i in range(n):
        fi = all_faces[i]
        for j in range(i + 1, n):
            fj = all_faces[j]
            if not _bbox_overlap(fi, fj):
                continue
            if _occludes(fi, fj, view):
                adj[j].append(i)
                indeg[i] += 1
            elif _occludes(fj, fi, view):
                adj[i].append(j)
                indeg[j] += 1
    heap = [(all_faces[i]["depth"], i) for i in range(n) if indeg[i] == 0]
    heapq.heapify(heap)
    order: list[int] = []
    while heap:
        _, i = heapq.heappop(heap)
        order.append(i)
        for j in adj[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                heapq.heappush(heap, (all_faces[j]["depth"], j))
    if len(order) < n:  # interpenetrating geometry: break cycles by depth
        done = set(order)
        order.extend(sorted((i for i in range(n) if i not in done),
                            key=lambda i: all_faces[i]["depth"]))
    all_faces = [all_faces[i] for i in order]

    for f in all_faces:
        if f["fin"] and textured:
            tex, sw_w, sw_h = f["fin"]
            _draw_face_textured(base, f["quad"], tex, ppi, max(sw_w, 0.5),
                                max(sw_h, 0.5), f["lu"], f["lv"], f["shade"])
        else:
            _draw_face_flat(base, f["quad"], f["color"],
                            f["shade"] if textured else int(f["shade"] * 0.8))

    if watermark:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", max(14, H // 55))
        except Exception:
            try:
                font = ImageFont.load_default(max(14, H // 55))
            except Exception:
                font = ImageFont.load_default()
        dr = ImageDraw.Draw(base, "RGBA")
        dr.text((W - 18, H - 16), watermark, font=font, fill=(255, 255, 255, 110), anchor="rs")

    return base.convert("RGB")


def structure_preview(structure: dict, out_path: str) -> str:
    layer_colors = {l["name"]: l.get("color", "#8d929a") for l in structure.get("layers", [])}
    img = render_scene(structure, layer_colors=layer_colors, size=(1200, 900),
                       camera="iso", textured=False)
    img.save(out_path, "PNG")
    return out_path
