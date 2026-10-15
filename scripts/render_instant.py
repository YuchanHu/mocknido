"""Instant film mockups, with published outside and image-area dimensions in mm."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps,ImageDraw,ImageFilter
from render_photobook import read_cover,preview_cover,book_geometry,perspective,DEFAULT,ROOT
from image_crop import manual_crop

# Width, height, image width, image height. Polaroid uses its support page's
# precise dimensions, not the rounded 79 x 79 mm often quoted by retailers.
FILMS={
 'polaroid':{'name':'宝丽来 600 / i-Type','paper':[88.47,107.52],'image':[76.801,78.94],'image_origin':[5.8345,5.8345]},
 # Origins and pod seam are approximate visual measurements from Fujifilm's
 # front-view samples, not manufacturer-specified manufacturing tolerances:
 # https://instax.jp/common/images/products/img_product_fi_top_mini.png
 # https://instax.jp/common/images/products/img_product_fi_top_wide.png
 'mini':{'name':'富士 instax mini','paper':[54,86],'image':[46,62],'image_origin':[4,7],'pod_seam_y':74},
 'wide':{'name':'富士 instax WIDE','paper':[108,86],'image':[99,62],'image_origin':[4.5,8],'pod_seam_y':74},
}


def paper_surface(spec,size,rotation=None):
    """Emboss the pod seam in paper coordinates; normals follow the film pose."""
    base=np.array([247,246,242],dtype=np.float32)
    if 'pod_seam_y' not in spec:return Image.new('RGB',size,tuple(base.astype(int)))
    tw,th=size;pw,ph=spec['paper'];k=tw/pw
    x=np.arange(tw,dtype=np.float32)[None,:]/k
    y=np.arange(th,dtype=np.float32)[:,None]/k
    # Pressed channel with feathered ends and a very slight reservoir shoulder.
    fade=np.clip(np.minimum(x-1.2,pw-1.2-x)/1.2,0,1)
    fade=fade*fade*(3-2*fade)
    center=spec['pod_seam_y']+.10*(2*x/pw-1)**4
    distance=y-center
    groove=np.exp(-.5*(distance/.17)**2)
    height=(-.045*groove+.045*np.exp(-.5*((distance-4.7)/3.1)**2))*fade
    dy,dx=np.gradient(height,1/k)
    light=np.array([-.4,-.75,1.2]);light/=np.linalg.norm(light)
    if rotation is not None:light=rotation.T@light
    diffuse=(-dx*light[0]-dy*light[1]+light[2])/np.sqrt(1+dx*dx+dy*dy)
    shade=1+.65*(diffuse-light[2])-.025*groove*fade
    # Low contrast pressed-paper grain; all spatial frequencies use millimetres.
    grain=.32*np.sin(x*32+y*19)+.22*np.sin(x*13-y*27)
    pixels=np.clip(base[None,None,:]*shade[:,:,None]+grain[:,:,None],0,255)
    return Image.fromarray(pixels.astype(np.uint8))


def film_texture(source,film,width,fit='crop',crop=None,gloss=.35,rotation=None):
    spec=FILMS[film];pw,ph=spec['paper'];iw,ih=spec['image']
    tw=round(width*.92);k=tw/pw;th=round(ph*k)
    texture=paper_surface(spec,(tw,th),rotation)
    left,top=spec['image_origin']
    box=tuple(round(n*k) for n in (left,top,left+iw,top+ih))
    target=(box[2]-box[0],box[3]-box[1])
    path=Path(source)
    image=preview_cover(str(path.resolve()),path.stat().st_mtime_ns).copy() if width<=800 and fit!='manual' else read_cover(path)
    if fit=='manual':image=manual_crop(image,crop,iw/ih).resize(target,Image.Resampling.LANCZOS)
    elif fit=='contain':image=ImageOps.pad(image,target,Image.Resampling.LANCZOS,color=(242,240,235))
    elif fit=='crop':image=ImageOps.fit(image,target,Image.Resampling.LANCZOS)
    else:raise ValueError('图片适配模式无效')
    arr=np.asarray(image,dtype=np.float32)
    u=np.linspace(0,1,target[0])[None,:];v=np.linspace(0,1,target[1])[:,None]
    reflection=np.clip(gloss,0,1.5)*.08*np.exp(-((u-.25-.5*v)/.12)**2)
    arr=arr*(1-reflection[:,:,None])+255*reflection[:,:,None]
    texture.paste(Image.fromarray(np.uint8(np.clip(arr,0,255))),box[:2])
    draw=ImageDraw.Draw(texture)
    draw.rectangle((box[0]-1,box[1]-1,box[2],box[3]),outline=(202,202,197),width=1)
    return texture,spec,box


def render_instant(source,output=None,width=2400,film='polaroid',fit='crop',crop=None,
                   gloss=.35,rotate_x=0,rotate_y=0,rotate_z=-8,transparent=True):
    if film not in FILMS:raise ValueError('相纸型号无效')
    spec=FILMS[film];pw,ph=spec['paper'];size=(width,round(width*1.12));s=width/1000
    q,base,rotation=book_geometry(width,.07,rotate_x,rotate_y,rotate_z,pw/ph)
    texture,spec,box=film_texture(source,film,width,fit,crop,gloss,rotation)
    canvas=Image.new('RGBA',size)
    mask=Image.new('L',texture.size)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,texture.width-1,texture.height-1),radius=max(1,texture.width*.008),fill=255)
    texture=texture.convert('RGBA');texture.putalpha(mask)
    front=perspective(texture,q,size)
    for offset,blur,alpha in [((5,8),9,.16),((2,3),2.5,.22)]:
        shadow=Image.new('L',size);shadow.paste(front.getchannel('A'),(round(offset[0]*s),round(offset[1]*s)))
        shadow=shadow.filter(ImageFilter.GaussianBlur(blur*s)).point(lambda p:p*alpha)
        layer=Image.new('RGBA',size,(40,36,32,0));layer.putalpha(shadow);canvas=Image.alpha_composite(canvas,layer)
    edge=Image.new('RGBA',texture.size,(197,195,189,255));edge.putalpha(mask)
    canvas=Image.alpha_composite(canvas,perspective(edge,base,size))
    result=Image.alpha_composite(canvas,front)
    if not transparent:result=Image.alpha_composite(Image.new('RGBA',size,(250,250,249,255)),result).convert('RGB')
    if output:result.save(output,dpi=(300,300))
    return result


if __name__=='__main__':
    for film in FILMS:
        options={}
        if film=='wide':
            source=read_cover(DEFAULT);iw,ih=FILMS[film]['image']
            h=(source.width/source.height)/(iw/ih)
            options={'fit':'manual','crop':{'x':0,'y':min(.12,1-h),'w':1,'h':h}}
        render_instant(DEFAULT,ROOT/'deliverables'/f'拍立得_{film}_透明底.png',film=film,**options)
