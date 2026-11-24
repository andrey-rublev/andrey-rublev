from math import cos, radians, sin

import numpy as np


CARD_WIDTH = .70
STOCK = .0038
TABLE = -.24


def rotation(angles):
    ax, ay, az = map(radians, angles)
    sx, sy, sz = sin(ax), sin(ay), sin(az)
    cx, cy, cz = cos(ax), cos(ay), cos(az)
    return np.array((
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    ))
