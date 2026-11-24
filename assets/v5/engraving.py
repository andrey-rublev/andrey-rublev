"""Two-way engraved back for the topographic deck."""
import math

import numpy as np
from PIL import Image, ImageDraw


def engraved_back(size, mask):
    w,h=size
    yy,xx=np.mgrid[-1:1:complex(h),-1:1:complex(w)]
    grain=np.random.default_rng(58).normal(0,1.5,(h,w))
    # Symmetric island contours stay recognizable when the card turns over.
    terrain=np.zeros_like(xx)
    for sign in (-1,1):
        x=sign*xx; y=sign*yy
        terrain+=np.exp(-((x-.16+.16*np.sin(y*8))/.69)**2-((y-.44)/.34)**2)
        terrain+=.32*np.exp(-((x+.64)/.31)**2-((y-.25)/.21)**2)
    phase=12*terrain
    line=np.exp(-((phase-np.rint(phase))/.17)**2)*np.clip(terrain*4,0,1)
    contour=(np.rint(phase).astype(int)%3==0)
    light=(.26+.18*np.cos(1.4*xx-1.7*yy))[...,None]
    base=np.array((11,21,87))+light*np.array((17,33,100))
    ink=np.where(contour[...,None],np.array((129,172,218)),np.array((66,100,175)))
    rgb=base + line[...,None]*ink*.85 + grain[...,None]
    field=Image.fromarray(np.uint8(np.clip(rgb,0,255))).convert('RGBA')
    d=ImageDraw.Draw(field)
    for m,c in ((8,'#6078b1'),(16,'#98aad0'),(21,'#354a87')):
        d.rounded_rectangle((m,m,w-m-1,h-m-1),radius=19,outline=c,width=2)
    cx,cy=w/2,h/2
    for r,c,sw in ((42,'#b2bfd4',2),(35,'#768bc5',2)):
        d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=c,width=sw)
    for i in range(32):
        a=math.pi*2*i/32
        ri=43 if i%4 else 40
        d.line([(cx+ri*math.cos(a),cy+ri*math.sin(a)),
                (cx+47*math.cos(a),cy+47*math.sin(a))],fill='#adbbcf',width=2)
    for i in range(4):
        angle=i*math.pi/2
        tip=(cx+30*math.cos(angle),cy+30*math.sin(angle))
        left=(cx+7*math.cos(angle-.77),cy+7*math.sin(angle-.77))
        right=(cx+7*math.cos(angle+.77),cy+7*math.sin(angle+.77))
        d.polygon([tip,left,(cx,cy)],fill='#d2d7c8')
        d.polygon([tip,(cx,cy),right],fill='#839cca')
    d.ellipse((cx-4,cy-4,cx+4,cy+4),fill='#d5df90')
    for x,y in ((w*.35,h*.295),(w*.65,h*.705)):
        d.ellipse((x-4,y-4,x+4,y+4),fill='#d4e58a')
    field.putalpha(mask)
    return field
