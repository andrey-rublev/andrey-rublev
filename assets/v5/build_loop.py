"""Render the continuous poker cover and its optional close-up.

Use Python with Pillow, NumPy, FontTools, Brotli and FFmpeg (libaom-av1), then run
python assets/v5/build_loop.py --layout wide mid mobile film
The covers use the profile palettes. The close-up uses its original studio lighting.
"""
import argparse
from dataclasses import dataclass
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
from stock_prints import build_faces
from engraving import engraved_back
from lettering import Typography
from profile_type import COVER_PALETTES, draw_masthead
from render_cards import Textures, UV_HEIGHT, UV_WIDTH, render

from packet_cut import CUT_PERIOD, FAN_START, FAN_PEAK, FAN_END, OPENING, PERIOD, playback_time, SPRING_START, SPRING_TIME, smooth, beat, deck, optics
FPS = 30
FORMATS = {
    # canvas, stage origin, projected card height, horizontal image crop
    "wide": ((846, 328), (592, 170), 151, 312),
    "mid": ((560, 255), (390, 136), 107, 175),
    "mobile": ((360, 342), (180, 225), 106, 0),
    "film": ((740, 482), (374, 243), 217, 0),
}


def print_faces():
    """Recover the photographed front face using four points inside its stock edge."""
    textures = Textures(HERE / "faces")
    photo = Image.open(HERE.parent / "v2" / "hero-deck.webp").convert("RGB")
    size = (UV_WIDTH, UV_HEIGHT)
    original_ace = photo.transform(size, Image.Transform.QUAD,
        (351, 75, 167, 557, 517, 644, 650, 146), Image.Resampling.BICUBIC)
    mask = textures.faces["ace-spades"].getchannel("A")
    original_ace.putalpha(mask)
    textures.faces["first-ace"] = original_ace
    textures.faces["back"] = engraved_back(size, mask)
    build_faces(textures, Typography(), mask)
    return textures


def background(layout, scale, theme="light"):
    (w,h), origin, _, _ = FORMATS[layout]
    width, height = round(w*scale),round(h*scale)
    if layout != "film":
        palette = COVER_PALETTES[theme]
        canvas = Image.new("RGB", (width, height), palette["surface"])
        draw_masthead(canvas, layout, scale, palette)
        return canvas

    # The standalone close-up retains its original studio lighting.
    y,x = np.ogrid[:height,:width]
    xx, yy = x/scale, y/scale
    light = np.exp(-2.8*((xx/w-.60)**2+(yy/h-.28)**2))
    vignette = np.clip((xx/w-.45)**2+(yy/h-.5)**2, 0,1)
    rgb = np.array((231,229,216)) + light[:,:,None]*[16,15,15] - vignette[:,:,None]*[5,5,7]
    return Image.fromarray(np.uint8(rgb)).convert("RGB")



@dataclass(frozen=True)
class TrackingCamera:
    size: tuple
    origin: tuple
    scale: float
    basis: np.ndarray
    focus: np.ndarray
    distance: float = 7.5

    @property
    def eye(self):
        return self.focus + self.distance*self.basis[2]

    def project(self, vertices):
        view = (vertices-self.focus) @ self.basis.T
        depth = 1./(self.distance-view[:,2])
        xy = view[:,:2] * (depth*self.distance*self.scale)[:,None] + self.origin
        return xy, depth


def project_stage(layout, t, density=1., top=None):
    size, origin, card_height, left = FORMATS[layout]
    if top is None:
        _, top = deck(t)
    basis, cut, ribbon, turn, fold, cut_time = optics(t)
    zoom = (1.22 if layout in ("wide","film") else 1.12) - .29*cut - .20*ribbon - .10*turn
    lead = {"wide":11, "mid":8, "mobile":1, "film":2}[layout]
    wheel = beat(cut_time / CUT_PERIOD,FAN_START,FAN_PEAK,FAN_END)
    zoom -= .15*wheel
    zoom = zoom*(1-fold) + (.713 if layout in ("wide","film") else .698)*fold
    follow_x = .25*card_height*ribbon*(1-fold) - .135*card_height*fold
    follow_y = card_height*.14*beat(cut_time / CUT_PERIOD,.58,.70,.80)*(1-fold) + .038*card_height*fold - .27*card_height*wheel
    center = ((origin[0]-left-lead-follow_x)*density, (origin[1]-5+follow_y)*density)
    focus = np.array((0.,0.,(top-.21)*.52))
    time=t%PERIOD
    source_track=1-smooth((time-SPRING_START)/.72)
    catch_track=smooth((time-(SPRING_START+SPRING_TIME-.65))/.65)
    end_weight=fold*(source_track+catch_track)
    zoom+=.28*end_weight
    focus[0]+=.61*fold*(catch_track-source_track)
    focus[1]+=.095*fold*(catch_track-source_track)
    stage_size = (round(size[0]*density)-round(left*density),round(size[1]*density))
    return TrackingCamera(stage_size,center,card_height*density*zoom,basis,focus)


def create_shot(layout, density, theme="light"):
    output_density = density
    density *= 1.52
    size, origin, card_height, left = FORMATS[layout]
    textures = print_faces()
    plate = background(layout, density, theme)
    shadow_color = (79, 75, 75) if layout == "film" else COVER_PALETTES[theme]["shadow"]
    box = (round(left*density),0,*plate.size)
    stage = plate.crop(box)
    def shot(t):
        t = playback_time(t)
        cards, top = deck(t)
        screen = project_stage(layout,t,density,top)
        result = render(stage,screen,cards,textures,shadow_color)
        image = plate.copy()
        image.paste(result,box[:2])
        return image.resize(tuple(round(x*output_density) for x in size), Image.Resampling.LANCZOS)
    return shot


def write_avif(frames, fps, target):
    """Give supporting browsers motion-compensated frames; WebP is the fallback."""
    w,h=frames[0].size
    temporary=target.with_suffix(".avif.tmp")
    command=["ffmpeg","-v","error","-y","-f","rawvideo","-pix_fmt","rgb24",
             "-s",f"{w}x{h}","-framerate",str(fps),"-i","pipe:0","-an",
             "-c:v","libaom-av1","-cpu-used","7","-threads","4","-row-mt","1",
             "-crf","29","-b:v","0","-g",str(4*fps),"-pix_fmt","yuv420p","-loop","0","-f","avif",str(temporary)]
    try:
        with subprocess.Popen(command,stdin=subprocess.PIPE) as encoder:
            for frame in frames:
                encoder.stdin.write(frame.tobytes())
            encoder.stdin.close()
            if encoder.wait():
                raise RuntimeError(f"AVIF encoding failed for {target.name}")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layout", nargs="+", choices=FORMATS, default=list(FORMATS))
    parser.add_argument("--theme", nargs="+", choices=COVER_PALETTES, default=list(COVER_PALETTES),
                        help="Cover palettes to export (default: both).")
    parser.add_argument("--output", type=Path, default=HERE)
    parser.add_argument("--proof", action="store_true")
    parser.add_argument("--fps", type=int, default=FPS)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    editions = [(layout, theme) for layout in args.layout
                for theme in (("light",) if layout == "film" else args.theme)]
    for layout, theme in editions:
        name = layout if theme == "light" else f"{layout}-{theme}"
        shot = create_shot(layout, 1., theme)
        if args.proof:
            for i in (0, 2, 3.1, 4.7, 5.3, 7.3, 8.7, 10.8):
                shot(i).save(args.output/f"{name}-{i:.1f}.png")
            continue
        frame_count=round(args.fps*PERIOD)
        frames=[shot(PERIOD*i/frame_count) for i in range(frame_count)]
        milliseconds=[round(PERIOD*1000*i/frame_count) for i in range(frame_count+1)]
        durations=[b-a for a,b in zip(milliseconds,milliseconds[1:])]
        end = args.output/f"{name}.webp"
        temp = end.with_suffix(".tmp")
        # Inter-frame WebP deltas leave rectangular trails in the soft moving shadow.
        frames[0].save(temp,format="WEBP",save_all=True,append_images=frames[1:],loop=0,
                       duration=durations,quality=71,method=5,kmin=0,kmax=1)
        temp.replace(end)
        shot(-OPENING).save(args.output/f"{name}-still.webp",quality=91,method=6)
        write_avif(frames,args.fps,end.with_suffix(".avif"))
        del frames
        print(end.name,end.stat().st_size,end.with_suffix(".avif").stat().st_size,flush=True)


if __name__ == "__main__":
    main()
