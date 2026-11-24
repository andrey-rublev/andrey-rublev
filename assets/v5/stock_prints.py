"""Print the number cards on the same ivory stock as the illustrated courts."""
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from pack_order import CARDS

PIPS={
    'A':[(0,0)],'2':[(0,-1),(0,1)],'3':[(0,-1),(0,0),(0,1)],
    '4':[(-1,-1),(1,-1),(-1,1),(1,1)],
    '5':[(-1,-1),(1,-1),(0,0),(-1,1),(1,1)],
    '6':[(x,y) for x in (-1,1) for y in (-1,0,1)],
    '7':[(x,y) for x in (-1,1) for y in (-1,0,1)]+[(0,-.5)],
    '8':[(x,y) for x in (-1,1) for y in (-1,0,1)]+[(0,-.5),(0,.5)],
    '9':[(x,y) for x in (-1,1) for y in (-1,-.33,.33,1)]+[(0,0)],
    '10':[(x,y) for x in (-1,1) for y in (-1,-.33,.33,1)]+[(0,-.70),(0,.70)],
}


def pip(suit, color, size):
    base=Image.new('RGBA',(88,88))
    d=ImageDraw.Draw(base)
    if suit=='diamonds':
        d.polygon(((44,1),(79,44),(44,87),(9,44)),fill=color)
    elif suit=='clubs':
        for x,y in ((44,23),(23,48),(65,48)):
            d.ellipse((x-20,y-20,x+20,y+20),fill=color)
        d.polygon(((44,38),(34,77),(27,86),(60,86),(53,77)), fill=color)
    else:
        a=np.linspace(0,2*math.pi,144)
        x=44+2.5*16*np.sin(a)**3
        y=39-2.53*(13*np.cos(a)-5*np.cos(2*a)-2*np.cos(3*a)-np.cos(4*a))
        if suit=='spades':
            y=78-y*.87
            d.polygon(((44,43),(38,72),(29,86),(59,86),(51,72)),fill=color)
        d.polygon(list(zip(x,y)),fill=color)
    return base.resize((size,size),Image.Resampling.LANCZOS)


def build_faces(textures, typography, mask):
    textures.faces['king-hearts'] = Image.open(Path(__file__).parent / 'plates/king-hearts.png').convert('RGBA')
    textures.faces['king-hearts'].putalpha(mask)
    w, h = mask.size
    y, x = np.mgrid[0:h, 0:w]
    light = (1 - .36*x/w - .64*y/h)[..., None]
    grain = np.random.default_rng(52).normal(0, 1.35, (h,w,1))
    paper = np.array((235,219,192)) + light * np.array((16,20,24)) + grain
    stock = Image.fromarray(paper.clip(0,255).astype('uint8')).convert('RGBA')
    for rank, suit, name in CARDS:
        if name in textures.faces:
            continue
        ink = '#9e362f' if suit in ('hearts','diamonds') else '#17203b'
        field = stock.copy()
        pen = ImageDraw.Draw(field)
        # Small gold corner rules echo the illustrated courts without competing
        # with the rank or the pips when several cards overlap in the spring.
        for xy in [((81,37),(81,28),(151,28)), ((w-81,h-37),(w-81,h-28),(w-151,h-28))]:
            pen.line(xy, fill='#c8aa77', width=2)
        mark = pip(suit, ink, 139 if rank == 'A' else 54)
        for px, py in PIPS[rank]:
            glyph = mark.transpose(Image.Transpose.ROTATE_180) if py > 0 else mark
            cx, cy = w/2 + 80*px, h/2 + 183*py
            field.alpha_composite(glyph,(round(cx-mark.width/2),round(cy-mark.height/2)))
            pen.ellipse((cx-3,cy-3,cx+3,cy+3), fill='#d1af76')
        index = Image.new('RGBA',(82,136))
        index_pen = ImageDraw.Draw(index)
        index_pen.text((40,74),rank,anchor='ms',font=typography.font('display',68 if rank=='10' else 78),fill=ink)
        index.alpha_composite(pip(suit,ink,39),(20,83))
        field.alpha_composite(index,(3,10))
        field.alpha_composite(index.transpose(Image.Transpose.ROTATE_180),(w-85,h-146))
        field.putalpha(mask)
        textures.faces[name] = field
