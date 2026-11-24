"""Project the card models onto a camera with per-pixel depth and stock edges."""

from dataclasses import dataclass
from functools import lru_cache
from math import floor, log2

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from card_geometry import CARD_WIDTH, STOCK, TABLE


CAMERA = 4.8
KEY = np.array((-.52, -.41, .75))
KEY /= np.linalg.norm(KEY)
FILL = np.array((.58, .37, .73))
FILL /= np.linalg.norm(FILL)
HALF_VECTOR = KEY + (0., 0., 1.)
HALF_VECTOR /= np.linalg.norm(HALF_VECTOR)
FACE_AMBIENT = np.array((.75, .77, .82))
FACE_KEY = np.array((.25, .227, .19))
FACE_FILL = np.array((.045, .058, .065))
FACE_SPECULAR = np.array((.048, .033, .021))
EDGE_AMBIENT = np.array((.56, .57, .60))
EDGE_KEY = np.array((.40, .36, .31))
EDGE_FILL = np.array((.085, .100, .115))
UV_WIDTH, UV_HEIGHT = 420, 600
CORNER = .045


@dataclass(frozen=True)
class View:
    basis: np.ndarray
    focus: tuple
    offset: tuple


@dataclass(frozen=True)
class Screen:
    size: tuple
    origin: tuple
    scale: float
    view: View | None = None

    @property
    def eye(self):
        position = np.array((0., 0., CAMERA))
        if self.view is None:
            return position
        return self.view.focus + self.view.basis.T @ (position - self.view.focus)

    def project(self, vertices):
        origin = np.asarray(self.origin)
        if self.view is not None:
            vertices = (vertices - self.view.focus) @ self.view.basis.T + self.view.focus
            origin = origin + self.view.offset
        depths = 1 / (CAMERA - vertices[:, 2])
        positions = vertices[:, :2] * (depths * CAMERA * self.scale)[:, None] + origin
        return positions, depths


class Pyramid:
    def __init__(self, image):
        self.full = image
        self.levels = {(1, 1): image}

    def texture(self, width, height):
        target = (width, height)
        reduction = tuple(
            2 ** min(4, floor(log2(max(1., source / max(1., length * 1.16)))))
            for source, length in zip(self.full.size, target)
        )
        if reduction not in self.levels:
            size = tuple(max(1, round(source / factor)) for source, factor in zip(self.full.size, reduction))
            self.levels[reduction] = self.full.resize(size, Image.Resampling.LANCZOS)
        return self.levels[reduction]


@dataclass(frozen=True)
class Surface:
    vertices: np.ndarray
    texture: Pyramid
    shade: np.ndarray
    bottom_shade: np.ndarray | None = None


def quad_project(positions, texture_size):
    """Fit the backward projection, from cropped image positions to source UV."""
    width, height = texture_size
    us, vs = (0, width, width, 0), (0, 0, height, height)
    rows, values = [], []
    for (x, y), u, v in zip(positions, us, vs):
        rows.extend(((x, y, 1, 0, 0, 0, -u*x, -u*y), (0, 0, 0, x, y, 1, -v*x, -v*y)))
        values.extend((u, v))
    return tuple(np.linalg.solve(rows, values))


def plane_depth(positions, depths, width, height):
    coefficients = np.linalg.solve(
        np.column_stack((positions[:3], np.ones(3))),
        depths[:3],
    )
    y, x = np.ogrid[:height, :width]
    a, b, c = coefficients
    return a * (x + .5) + b * (y + .5) + c


def texture_light(normal, *, edge=False):
    key = max(float(normal @ KEY), 0.)
    fill = max(float(normal @ FILL), 0.)
    if edge:
        return EDGE_AMBIENT + key * EDGE_KEY + fill * EDGE_FILL
    specular = max(float(normal @ HALF_VECTOR), 0.) ** 25
    return FACE_AMBIENT + key * FACE_KEY + fill * FACE_FILL + specular * FACE_SPECULAR


def card_surface(texture, vertices, facing, eye, *, edge=False):
    side1 = vertices[1] - vertices[0]
    side2 = vertices[3] - vertices[0]
    normal = np.cross(side1, side2) * facing
    normal /= np.linalg.norm(normal)
    if normal @ (eye - vertices[0]) <= 0:
        return None
    return Surface(vertices, texture, texture_light(normal, edge=edge))


def bend_z(v, bend):
    return bend * ((v * 2) ** 2 - .33)


@lru_cache(maxsize=54)
def stock_texture(count):
    palette = ((216, 204, 186), (220, 207, 188), (207, 191, 175), (224, 211, 194))
    image = Image.new('RGBA', (2, count * 3))
    draw = ImageDraw.Draw(image)
    for index in range(count):
        y = index * 3
        draw.line((0, y, 2, y), fill=(166, 149, 127, 255))
        fill = palette[index % len(palette)] + (255,)
        draw.line((0, y+1, 2, y+1), fill=fill)
        draw.line((0, y+2, 2, y+2), fill=fill)
    return Pyramid(image)


class Textures:
    def __init__(self, directory):
        self.faces = {}
        mask = Image.new('L', (UV_WIDTH, UV_HEIGHT))
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, UV_WIDTH - 1, UV_HEIGHT - 1),
            radius=round(CORNER * UV_HEIGHT),
            fill=255,
        )
        for path in directory.glob('*.png'):
            with Image.open(path) as source:
                image = source.convert('RGBA').resize(mask.size, Image.Resampling.LANCZOS)
            image.putalpha(mask)
            self.faces[path.stem] = image

    @lru_cache(maxsize=240)
    def rows(self, name, start, stop, *, reverse=False):
        image = self.faces[name].crop((0, start, UV_WIDTH, stop))
        return Pyramid(image.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if reverse else image)


def surfaces(card, textures, eye):
    rotation = card.rotation
    thickness = getattr(card, "thickness", STOCK * card.count) / 2

    def world(local):
        return np.asarray(local) @ rotation.T + card.center

    def local(u, v, face):
        return u, v * (1 - .42 * abs(card.bend)), face * thickness + bend_z(v, card.bend)

    divisions = 10 if abs(card.bend) > .008 else 1
    steps = np.linspace(0, UV_HEIGHT, divisions + 1).round().astype(int)
    for start, stop in zip(steps, steps[1:]):
        top, bottom = start / UV_HEIGHT - .5, stop / UV_HEIGHT - .5
        for face, texture in ((1, card.face), (-1, 'back')):
            left, right = -CARD_WIDTH / 2, CARD_WIDTH / 2
            vertices = world((
                local(left, top, face), local(right, top, face),
                local(right, bottom, face), local(left, bottom, face),
            ))
            texture = textures.rows(texture, start, stop, reverse=face == -1)
            if (surface := card_surface(texture, vertices, face, eye)) is not None:
                if divisions>1:
                    shades=[]
                    for v in (top,bottom):
                        local_normal=np.array((0.,-8*card.bend*v,1-.42*abs(card.bend)))
                        normal=face*rotation@local_normal
                        shades.append(texture_light(normal/np.linalg.norm(normal)))
                    surface=Surface(surface.vertices,surface.texture,*shades)
                yield surface

    # Two straight edges per axis and four round card corners. Split the two
    # long edges at the same pitch as the texture strips on curved cards.
    left, right = -CARD_WIDTH / 2, CARD_WIDTH / 2
    top, bottom = -.5, .5
    sides = [(left + CORNER, top), (right - CORNER, top)]
    for x, y, start, stop in (
        (right - CORNER, top + CORNER, -np.pi/2, 0.),
        (right - CORNER, bottom - CORNER, 0., np.pi/2),
        (left + CORNER, bottom - CORNER, np.pi/2, np.pi),
        (left + CORNER, top + CORNER, np.pi, 1.5*np.pi),
    ):
        sides.extend((x + CORNER*np.cos(a), y + CORNER*np.sin(a)) for a in np.linspace(start, stop, 4))
    edge = stock_texture(card.count)
    for start, stop in zip(sides, sides[1:] + sides[:1]):
        if np.linalg.norm(np.asarray(start) - stop) < .0001:
            continue
        samples = divisions if abs(start[0] - stop[0]) < .001 and abs(start[1] - stop[1]) > .4 else 1
        end_points = np.linspace(start, stop, samples + 1)
        for a, b in zip(end_points, end_points[1:]):
            vertices = world((local(*a, -1), local(*b, -1), local(*b, 1), local(*a, 1)))
            if (surface := card_surface(edge, vertices, 1, eye, edge=True)) is not None:
                yield surface


def composite_surface(canvas, depth, screen, surface):
    points, distances = screen.project(surface.vertices)
    x0, y0 = np.floor(np.min(points, axis=0)).astype(int) - 1
    x1, y1 = np.ceil(np.max(points, axis=0)).astype(int) + 1
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(screen.size[0], x1), min(screen.size[1], y1)
    width, height = x1 - x0, y1 - y0
    if width <= 0 or height <= 0:
        return
    local = points - (x0, y0)
    sx, sy = local[1] - local[0]
    tx, ty = local[3] - local[0]
    area = abs(sx * ty - sy * tx)
    if area < .21:
        return
    u = max(np.hypot(sx, sy), np.linalg.norm(local[2] - local[3]))
    v = max(np.hypot(tx, ty), np.linalg.norm(local[2] - local[1]))
    texture = surface.texture.texture(u, v)
    try:
        inverse = quad_project(local, texture.size)
        plane = plane_depth(local, distances, width, height)
    except np.linalg.LinAlgError:  # an edge-on surface has no projected area
        return

    stock = texture.transform(
        (width, height), Image.Transform.PERSPECTIVE, inverse, Image.Resampling.BICUBIC,
    )
    rgba = np.asarray(stock)
    z = depth[y0:y1, x0:x1]
    exposed = (rgba[:, :, 3] > 96) & (plane > z)
    if not exposed.any():
        return
    z[exposed] = plane[exposed]
    shade=surface.shade
    if surface.bottom_shade is not None:
        # Shade the continuous bowed paper at its texture coordinate. Flat
        # shading per raster strip produces false horizontal bands in flight.
        rows,cols=np.nonzero(exposed)
        x,y=cols+.5,rows+.5
        _,_,_,d,e,f,g,h=inverse
        ratio=np.clip((d*x+e*y+f)/((g*x+h*y+1)*texture.height),0,1)[:,None]
        shade=shade+ratio*(surface.bottom_shade-shade)
    canvas[y0:y1, x0:x1][exposed] = np.clip(rgba[:, :, :3][exposed] * shade, 0, 255)


SHADOW_POINTS = np.array((
    (-.30, -.50, 0.), (.30, -.50, 0.), (.35, -.45, 0.), (.35, .45, 0.),
    (.30, .50, 0.), (-.30, .50, 0.), (-.35, .45, 0.), (-.35, -.45, 0.),
))


def shadows(background, screen, cards, shadow_color):
    """Place the warm key's soft cast shadow onto the table plane."""
    composite = Image.new('L', screen.size)
    ordered = sorted(cards, key=lambda card: card.count)
    for minimum, maximum, softness in ((0., .12, 2.2), (.12, .31, 4.2), (.31, .54, 8.), (.54, 10., 13.)):
        mask = Image.new('L', screen.size)
        draw = ImageDraw.Draw(mask)
        for card in ordered:
            altitude = max(.01, card.center[2] - TABLE)
            if not minimum <= altitude < maximum:
                continue
            vertices = SHADOW_POINTS @ card.rotation.T + card.center
            distance = np.maximum(vertices[:, 2] - TABLE, .005)
            vertices[:, 0] += distance * .56
            vertices[:, 1] += distance * .46
            vertices[:, 2] = TABLE
            points, _ = screen.project(vertices)
            transparency = (.51 if card.count > 1 else .29) * np.exp(-1.6 * altitude)
            draw.polygon([tuple(point) for point in points], fill=round(255 * transparency))
        softened = mask.filter(ImageFilter.GaussianBlur(softness * screen.scale / 120))
        composite = ImageChops.lighter(composite, softened)
    return Image.composite(Image.new('RGB', screen.size, shadow_color), background, composite)


def contact_occlusion(canvas, depth, scale):
    """Soften contact shadows where one card passes directly above another."""
    occlusion = np.zeros_like(depth)
    for reach, strength in ((.017, .22), (.036, .18), (.065, .12)):
        shift = max(1, round(reach * scale))
        y, x = shift, max(1, round(shift * .71))
        toward_light = depth[:-y, :-x]
        current = depth[y:, x:]
        valid = (toward_light > 0) & (current > 0)
        difference = np.zeros_like(current)
        np.subtract(toward_light, current, out=difference, where=valid)
        weight = np.clip((difference - .0027) / .008, 0., 1.) * strength
        target = occlusion[y:, x:]
        np.maximum(target, weight, out=target)
    canvas[:] = canvas * (1. - occlusion[:, :, None])


def render(background, screen, cards, textures, shadow_color):
    base = shadows(background, screen, cards, shadow_color)
    canvas = np.asarray(base).copy()
    depth = np.full(canvas.shape[:2], -np.inf)
    eye = screen.eye
    for card in cards:
        for surface in surfaces(card, textures, eye):
            composite_surface(canvas, depth, screen, surface)
    contact_occlusion(canvas, depth, screen.scale)
    return Image.fromarray(canvas)
