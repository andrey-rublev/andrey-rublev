"""Bake the exact card solids used by the native profile for the interactive close-up."""
from itertools import product
from pathlib import Path
import json
import zlib
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'assets/v5'))
from build_loop import FORMATS, PERIOD, print_faces, project_stage
from packet_cut import (
    ACE_BACK_TIME, CUT_PERIOD, FAN_PEAK, OPENING, PIVOT_START, PIVOT_END,
    SPRING_START, SPRING_TIME, deck, expand, playback_time,
)
from card_geometry import CARD_WIDTH, STOCK

FPS=60
FLIP_Y=np.diag((1.,-1.,1.))
CORNERS=np.array(list(product([-1.,1.],repeat=3)))


def affine(basis,center):
    return np.column_stack((FLIP_Y @ basis @ FLIP_Y, FLIP_Y @ center)).flatten()


def bake():
    first=expand(deck(0)[0])
    textures=print_faces()
    faces=list(dict.fromkeys([c.face for c in first]+['back']))
    atlas=Image.new('RGB',(3072,3072),'#ded2bc')
    rectangles={}
    small=[f for f in faces if f not in ('first-ace','back')]
    for name in faces:
        plate=textures.faces[name].convert('RGB')
        if name in ('first-ace','back'):
            x,y=2470,12+(640 if name=='back' else 0)
        else:
            index=small.index(name)
            x,y=8+(index%8)*304,8+(index//8)*431
            plate=plate.resize((284,406),Image.Resampling.LANCZOS)
        atlas.paste(plate,(x,y))
        rectangles[name]=[x,y,*plate.size]
    # Separate little strips keep each packet's exposed stock proportional to
    # its real layer count. The face UVs do not share filtering seams.
    pen=ImageDraw.Draw(atlas)
    for i,count in enumerate(sorted({c.count for c in first})):
        x,y=2470+i*72,1440
        height=max(4,count*8)
        for n in range(height):
            color=('#ae9c81' if n%8<2 else ('#eae0ca' if (n//8)%2==0 else '#d9cbb5'))
            pen.line((x,y+n,x+40,y+n),fill=color)
        rectangles[f'edge-{count}']=[x,y,40,height]
    atlas.save(HERE/'faces.webp',quality=90,method=6)
    samples=[]
    frames=round(PERIOD*FPS)
    for index in range(frames):
        t=playback_time(index/FPS)
        packets,top=deck(t)
        camera=project_stage('film',t,top=top)
        leaves=expand(packets)
        poses=[np.append(affine(card.rotation,card.center),card.bend) for card in leaves]
        counts=[p.count for p in packets]
        assert sum(counts)==52 and len(counts)<=16
        counts += [0]*(16-len(counts))
        corners=np.concatenate([CORNERS*(CARD_WIDTH*.5,.5,p.thickness*.5+.67*abs(p.bend)) @ p.rotation.T+p.center for p in packets])
        center=(corners.max(axis=0)+corners.min(axis=0))*.5
        radius=np.linalg.norm(corners-center,axis=1).max()
        view=affine(camera.basis.T,camera.focus)
        samples.append(np.concatenate((*poses,view,[camera.scale,*camera.origin,*list(FLIP_Y@center),radius],counts)))
    data=np.asarray(samples,dtype='<f4')
    (HERE/'score.bin').write_bytes(zlib.compress(data.tobytes(),level=9))
    meta={'fps':FPS,'frames':frames,'encoding':'deflate-f32le','casterSlots':16,'stride':data.shape[1],'atlasSize':atlas.width,'regions':rectangles,
          'cards':[{'face':c.face,'count':c.count} for c in first],'cardWidth':CARD_WIDTH,'stock':STOCK,
          'filmSize':FORMATS['film'][0],'distance':camera.distance}
    meta['cues']=[{'name':name,'time':round((t-OPENING)%PERIOD,3)} for name,t in (
        ('Deck squeeze',SPRING_START),('Card spring',8.26),
        ('Ace flip',ACE_BACK_TIME),
        ('Ace catch',SPRING_START + SPRING_TIME + .05),
        ('Ace pivot',SPRING_TIME + (PIVOT_START + PIVOT_END) / 2),
        ('Pressure fan',SPRING_TIME + CUT_PERIOD*FAN_PEAK),('Four-packet cut',4.00))]
    (HERE/'scene.json').write_text(json.dumps(meta,separators=(',',':')),encoding='utf8',newline='\n')
    print(f'{frames} exact scene poses, {data.nbytes} bytes')


if __name__=='__main__':
    bake()
