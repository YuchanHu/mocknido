"""Check physical proportions and that cropping changes the sampled source area."""
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from image_crop import manual_crop
from render_instant import film_texture, FILMS, paper_surface, render_instant
from render_photobook import book_geometry


def main():
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'halves.png'
        image=Image.new('RGB',(800,800),'red')
        image.paste('blue',(400,0,800,800));image.save(path)
        for key,spec in FILMS.items():
            pw,ph=spec['paper'];iw,ih=spec['image'];aspect=iw/ih
            w=min(.45,.8*aspect);h=w/aspect
            for x,color in [(0,(255,0,0)),(.55,(0,0,255))]:
                texture,_,box=film_texture(path,key,800,fit='manual',crop={'x':x,'y':.1,'w':w,'h':h},gloss=0)
                k=texture.width/pw
                assert abs(texture.height/k-ph)<=.5/k
                assert abs((box[2]-box[0])/k-iw)<=1/k
                assert abs((box[3]-box[1])/k-ih)<=1/k
                assert texture.getpixel(((box[0]+box[2])//2,(box[1]+box[3])//2))==color
                assert box[1]>0 and texture.height-box[3]>box[1]
                # Reference-calibrated offsets must not regress to top == side.
                expected={'mini':(4,7,17),'wide':(4.5,8,16)}
                if key in expected:
                    left,top,bottom=expected[key]
                    assert abs(box[0]/k-left)<=.5/k
                    assert abs(box[1]/k-top)<=.5/k
                    assert abs((texture.height-box[3])/k-bottom)<=1/k
                    seam=np.asarray(texture)[round(72*k):round(76*k),texture.width//2,:3].mean(axis=1)
                    assert seam.max()-seam.min()>12, 'Missing pod seam relief'
        for key in ('mini','wide'):
            # Relief stays in the bottom white margin, changes with pose and
            # remains visible at preview resolution without changing the aperture.
            spec=FILMS[key];size=(864,round(864*86/spec['paper'][0]))
            _,_,rotation=book_geometry(800,.07,45,0,0)
            flat=np.asarray(paper_surface(spec,size))
            tilted=np.asarray(paper_surface(spec,size,rotation))
            assert np.max(np.abs(flat.astype(float)-tilted.astype(float)))>5
            result=render_instant(path,width=800,film=key,rotate_x=25,rotate_y=-20)
            alpha=np.asarray(result)[:,:,3]
            assert result.mode=='RGBA' and alpha[0,0]==0
            assert np.any((alpha>0)&(alpha<150))
        for crop in [None,{'x':0,'y':0,'w':2,'h':1},{'x':0,'y':0,'w':.5,'h':.2},{'x':float('nan'),'y':0,'w':1,'h':1}]:
            try:manual_crop(image,crop,1)
            except ValueError:pass
            else:raise AssertionError('Invalid crop accepted')
    print('PASS: film dimensions, calibrated image offsets, pose-aware pod seams, source crop, transparent shadows, invalid crop rejection')


if __name__=='__main__':main()
