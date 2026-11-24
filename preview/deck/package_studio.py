"""Package the orbit viewer for both the local review and a GitHub-downloadable ZIP.

Run npm ci and npm run build in this directory, then python bake.py and
python package_studio.py. The ZIP contains one offline HTML file.
"""
from base64 import b64encode
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import json
import subprocess
import sys
from PIL import Image

HERE=Path(__file__).resolve().parent
MEDIA=HERE.parents[1]/'assets/v5'
sys.path.insert(0,str(MEDIA))
from profile_type import embedded_faces


def text(name):
    return (HERE/name).read_text(encoding='utf8')


def stylesheet():
    return embedded_faces() + text('dialog.css')


def image(path):
    return 'data:image/'+path.suffix[1:]+';base64,'+b64encode(path.read_bytes()).decode('ascii')


def shell(movie,still,avif='',dialog=False):
    body=text('shell.html')
    close='<button type="button" data-close autofocus>Close</button>' if dialog else ''
    for key,value in (('CLOSE',close),('AVIF',avif),('MOVIE',movie),('STILL',still)):
        body=body.replace('{{'+key+'}}',value)
    tag='dialog' if dialog else 'main'
    if not dialog: body=body.replace('<h2 ','<h1 ').replace('</h2>','</h1>')
    return f'<{tag} id="deck-film" aria-labelledby="film-title">{body}</{tag}>'


def payload():
    parts={'info':json.loads(text('scene.json')),'score':b64encode((HERE/'score.bin').read_bytes()).decode('ascii'),
           'image':b64encode((HERE/'faces.webp').read_bytes()).decode('ascii')}
    runtime=text('viewer.iife.js').replace('</script','<\\/script')
    return ('<script type="application/json" id="deck-packet">'+json.dumps(parts,separators=(',',':'))+'</script>'+
            '<script type="application/x-deck-program" id="deck-program">/*'+text('three-license.txt')+'*/\n'+runtime+'</script>')


def package(destination):
    with TemporaryDirectory() as scratch:
        fallback=Path(scratch)/'film.webp'
        cmd=['ffmpeg','-v','error','-nostdin','-y','-i',str(MEDIA/'film.avif'),'-map','0:v:1','-vf',
             'fps=20,scale=480:-2:flags=lanczos','-c:v','libwebp','-q:v','69','-compression_level','4','-loop','0','-an',str(fallback)]
        subprocess.run(cmd,check=True)
        with Image.open(fallback) as check:
            if check.n_frames<2 or check.info.get('loop')!=0:raise RuntimeError('Expected a repeating fallback')
        stage=shell(image(fallback),image(MEDIA/'film-still.webp'))
        css=stylesheet()+text('standalone.css')
        markup=('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'+
                '<meta name="color-scheme" content="light"><title>The topographic deck · Nikhil Kolli</title><style>'+css+'</style></head><body>'+
                stage+payload()+'<script>'+text('inspector.js')+'\n'+text('standalone.js')+'</script></body></html>')
    entry=ZipInfo('The topographic deck.html',date_time=(2026,11,24,0,0,0))
    entry.compress_type=ZIP_DEFLATED
    temp=destination.with_suffix('.packing')
    with ZipFile(temp,'w') as z:z.writestr(entry,markup.encode('utf8'))
    temp.replace(destination)
    print(destination, destination.stat().st_size)


if __name__=='__main__':
    package(MEDIA/'topographic-deck.zip')
