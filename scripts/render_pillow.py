"""Textured cushion rendering with cloth shading and transparent shadows."""
from pathlib import Path
import argparse
import math
import numpy as np
from numba import njit
from PIL import Image, ImageOps, ImageFilter
from render_photobook import DEFAULT, ROOT, read_cover, preview_cover, book_geometry

RATIOS = {'1:1': 1., '2:3': 2/3, '1:2': .5}


def pillow_mesh(aspect, fullness, wrinkles, resolution=193):
    # Boundary landmarks traced from the supplied upright cushion reference.
    # A Coons patch preserves its hanging top, pinched waist and grounded hem.
    from scipy.interpolate import PchipInterpolator
    axis=np.sin(np.linspace(-np.pi/2,np.pi/2,resolution))
    u,v=np.meshgrid(axis,axis)
    t=(axis+1)/2
    def curve(knots,points):
        return PchipInterpolator(knots,np.asarray(points),axis=0)(t)
    top=curve([0,.12,.25,.34,.39,.44,.5,.57,.64,.76,.88,1],
              [[-.94,-.98],[-.73,-.91],[-.49,-.83],[-.30,-.80],[-.20,-.81],[-.11,-.78],
               [0,-.80],[.13,-.79],[.26,-.82],[.49,-.87],[.72,-.94],[.94,-1.]])
    bottom=curve([0,.035,.15,.4,.65,.87,.97,1],
                 [[-1.,.98],[-.96,1.],[-.73,1.005],[-.23,1.],[.30,1.003],[.74,1.],[.96,.995],[1.,.98]])
    left=curve([0,.12,.32,.50,.62,.68,.76,.84,.91,.97,1],
               [[-.94,-.98],[-.90,-.73],[-.85,-.34],[-.81,.04],[-.80,.28],[-.85,.39],
                [-.86,.56],[-.90,.70],[-.94,.84],[-1.01,.94],[-1.,.98]])
    right=curve([0,.13,.32,.50,.60,.65,.71,.77,.83,.89,.94,.98,1],
                [[.94,-1.],[.90,-.73],[.84,-.34],[.80,.02],[.80,.22],[.77,.33],
                 [.82,.46],[.80,.58],[.86,.69],[.85,.81],[.92,.89],[1.015,.96],[1.,.98]])
    U=(u+1)/2;V=(v+1)/2
    corners=(1-U)[...,None]*(1-V)[...,None]*top[0]+U[...,None]*(1-V)[...,None]*top[-1]+(1-U)[...,None]*V[...,None]*bottom[0]+U[...,None]*V[...,None]*bottom[-1]
    xy=(1-V)[...,None]*top[None,:,:]+V[...,None]*bottom[None,:,:]+(1-U)[...,None]*left[:,None,:]+U[...,None]*right[:,None,:]-corners
    x=xy[:,:,0]*aspect;y=xy[:,:,1]
    envelope=np.maximum(0,(1-u*u)*(1-v*v))
    depth=(.27+.14*fullness)*min(1,aspect/.75)
    dome=depth*np.maximum(0,1-u*u)**.48*np.maximum(0,1-v*v)**.39*(1+.10*v)
    # Folds follow the reference's gathered lower corners rather than evenly
    # spaced radial streaks. Curved troughs are accompanied by broad cloth rolls.
    folds=np.zeros_like(u)
    fold_specs=[
      (-1,.30,-.36,.36,.041,.032),
      (-1,.69,-.23,.43,.047,.038),(-1,.87,-.17,.48,.033,.031),
      (1,.31,.40,.32,.041,.031),(1,.47,-.24,.40,.036,.033),
      (1,.64,-.28,.48,.044,.043),(1,.81,-.22,.52,.037,.036),
      (1,.92,-.12,.44,.025,.024)]
    for side,anchor,slope,length,spread,amplitude in fold_specs:
        d=1-side*u
        path=anchor+slope*d+.16*d*d
        distance=(v-path)/(spread*(1+.8*d))
        taper=(1-np.exp(-d/.045))*np.exp(-(d/length)**2)*(1-np.clip(d/.72,0,1)**2)**2
        trough=-np.exp(-.5*distance*distance)
        roll=.58*np.exp(-.5*((distance+1.8)/1.45)**2)
        folds+=amplitude*1.25*taper*(trough+roll)
    # A pair of broad asymmetric slack depressions connects the gathers to the body.
    folds-=.012*np.exp(-((u+.69)/.20)**2-((v-.25)/.22)**2)
    folds-=.014*np.exp(-((u-.62)/.23)**2-((v-.56)/.23)**2)
    folds+=.005*np.sin(5*u+2*v)*envelope
    z=np.maximum(0,dome+wrinkles*folds*envelope**.10)
    # The seam stays closed; both skins meet the same traced perimeter.
    front=np.stack([x,y,z],axis=-1)
    back=np.stack([x,y,-dome*.70],axis=-1)
    uv=np.stack([U,V],axis=-1)
    faces=[]
    for j in range(resolution-1):
        for i in range(resolution-1):
            a=j*resolution+i
            faces.extend([(a,a+1,a+resolution),(a+1,a+resolution+1,a+resolution)])
    return front,back,uv,np.asarray(faces,dtype=np.int32)


@njit(cache=True)
def raster(screen, attributes, faces, texture, pixels, zbuffer):
    """Perspective-correct, depth-tested triangles with bilinear texture sampling."""
    height,width,_=pixels.shape
    th,tw,_=texture.shape
    for face in faces:
        a,b,c=face
        x0,y0=screen[a,0],screen[a,1];x1,y1=screen[b,0],screen[b,1];x2,y2=screen[c,0],screen[c,1]
        denom=(y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
        if abs(denom)<1e-8: continue
        left=max(0,int(math.floor(min(x0,x1,x2))));right=min(width-1,int(math.ceil(max(x0,x1,x2))))
        top=max(0,int(math.floor(min(y0,y1,y2))));bottom=min(height-1,int(math.ceil(max(y0,y1,y2))))
        for y in range(top,bottom+1):
            for x in range(left,right+1):
                w0=((y1-y2)*(x+.5-x2)+(x2-x1)*(y+.5-y2))/denom
                w1=((y2-y0)*(x+.5-x2)+(x0-x2)*(y+.5-y2))/denom
                w2=1-w0-w1
                if min(w0,w1,w2)<-1e-7: continue
                inv=w0*screen[a,2]+w1*screen[b,2]+w2*screen[c,2]
                if inv<=zbuffer[y,x]:continue
                zbuffer[y,x]=inv
                wa=w0*screen[a,2]/inv;wb=w1*screen[b,2]/inv;wc=w2*screen[c,2]/inv
                u=min(1.,max(0.,wa*attributes[a,0]+wb*attributes[b,0]+wc*attributes[c,0]))*(tw-1)
                v=min(1.,max(0.,wa*attributes[a,1]+wb*attributes[b,1]+wc*attributes[c,1]))*(th-1)
                tx=int(u);ty=int(v);fx=u-tx;fy=v-ty;tx1=min(tx+1,tw-1);ty1=min(ty+1,th-1)
                shade=wa*attributes[a,2]+wb*attributes[b,2]+wc*attributes[c,2]
                spec=wa*attributes[a,3]+wb*attributes[b,3]+wc*attributes[c,3]
                for k in range(3):
                    color=(texture[ty,tx,k]*(1-fx)+texture[ty,tx1,k]*fx)*(1-fy)+(texture[ty1,tx,k]*(1-fx)+texture[ty1,tx1,k]*fx)*fy
                    value=max(0.,min(1.,color*shade+spec))
                    encoded=value*12.92 if value<=.0031308 else 1.055*value**(1/2.4)-.055
                    pixels[y,x,k]=int(min(255.,max(0.,encoded*255+.5)))
                pixels[y,x,3]=255


def render_pillow(source, output=None, width=2400, ratio='1:1', fullness=.9, wrinkles=1.,
                  gloss=.35, fit='crop', rotate_x=0, rotate_y=0, rotate_z=0, transparent=True, crop=None):
    if ratio not in RATIOS: raise ValueError('抱枕比例仅支持 1:1、2:3、1:2')
    if fit not in ('crop','contain','manual'): raise ValueError('图片适配模式无效')
    if not 400<=width<=5000: raise ValueError('输出宽度范围为 400–5000')
    params=np.array([fullness,wrinkles,gloss],float)
    if not np.all(np.isfinite(params)):raise ValueError('参数必须是有限数值')
    fullness=float(np.clip(fullness,.2,2));wrinkles=float(np.clip(wrinkles,0,2));gloss=float(np.clip(gloss,0,1.5))
    aspect=RATIOS[ratio]
    # Use the same rotation conventions and limits as the book controls.
    _,_,rotation=book_geometry(width,.9,rotate_x,rotate_y,rotate_z)
    from import_pillow_fbx import square_render_mesh
    mesh,normals_base,uv,faces,front_faces=square_render_mesh(aspect,fullness,wrinkles)
    points=mesh@rotation.T
    all_points=points
    projection=all_points[:,:2]*6/(6-all_points[:,2:3])
    span=np.ptp(projection,axis=0)
    factor=min(420,850/span[0],930/span[1])*width/1000
    center=(projection.max(axis=0)+projection.min(axis=0))/2
    # Supersample previews and normal exports to soften the alpha edge without a white matte.
    ss=2 if width<=2400 else 1
    size=(width*ss,round(width*1.12)*ss)
    pixels=np.zeros((size[1],size[0],4),np.uint8)
    zbuffer=np.zeros(size[::-1],np.float32)
    path=Path(source)
    image=preview_cover(str(path.resolve()),path.stat().st_mtime_ns).copy() if width<=800 and fit!='manual' else read_cover(path)
    texture_size=(max(16,round(width*aspect)),width)
    if fit=='manual':
        from image_crop import manual_crop
        image=manual_crop(image,crop,aspect).resize(texture_size,Image.Resampling.LANCZOS)
    elif fit=='crop':image=ImageOps.fit(image,texture_size,Image.Resampling.LANCZOS)
    else:image=ImageOps.pad(image,texture_size,Image.Resampling.LANCZOS,color=(242,240,235))
    texture=np.asarray(image,dtype=np.float32)/255
    texture=np.where(texture<=.04045,texture/12.92,((texture+.055)/1.055)**2.4)
    # Subtle deterministic weave. It modulates print as well as unprinted cloth.
    tx=np.arange(texture_size[0])[None,:];ty=np.arange(texture_size[1])[:,None]
    grain=np.random.default_rng(421).normal(0,.008,(texture_size[1],texture_size[0]))
    weave=1-.008*(1+np.sin(tx*2.1)*np.sin(ty*2.35))+grain
    texture=np.ascontiguousarray(texture*weave[:,:,None],dtype=np.float32)
    light=np.array([-.55,-.75,1.15]);light/=np.linalg.norm(light)
    half_vector=light+np.array([0,0,1]);half_vector/=np.linalg.norm(half_vector)
    normals=normals_base@rotation.T
    diffuse=np.maximum(0,normals@light)
    fill_light=np.array([.55,.10,.82]);fill_light/=np.linalg.norm(fill_light)
    lighting=.36+.56*diffuse+.15*np.maximum(0,normals@fill_light)
    shine=gloss*.035*np.maximum(0,normals@half_vector)**10
    attrs=np.column_stack([uv,lighting,shine]).astype(np.float32)
    projected=points[:,:2]*6/(6-points[:,2:3])
    screen=np.column_stack([((projected-center)*factor+np.array([.5,.54])*width)*ss,1/(6-points[:,2])]).astype(np.float32)
    # Both original skins share the depth buffer; only the front receives print.
    raster(screen,attrs,faces[front_faces],texture,pixels,zbuffer)
    raster(screen,attrs,faces[~front_faces],np.full((2,2,3),.84,np.float32),pixels,zbuffer)
    body=Image.fromarray(pixels,'RGBA')
    if ss>1:body=body.resize((width,round(width*1.12)),Image.Resampling.LANCZOS)
    # The complete cloth silhouette casts a shadow; alpha remains unflattened.
    canvas=Image.new('RGBA',body.size)
    for offset,blur,opacity in [((11,17),17,.17),((5,8),6,.19),((2,3),2,.13)]:
        shadow=Image.new('L',body.size)
        shadow.paste(body.getchannel('A'),(round(offset[0]*width/1000),round(offset[1]*width/1000)))
        shadow=shadow.filter(ImageFilter.GaussianBlur(blur*width/1000)).point(lambda a:a*opacity)
        layer=Image.new('RGBA',body.size,(34,30,26,0));layer.putalpha(shadow)
        canvas=Image.alpha_composite(canvas,layer)
    result=Image.alpha_composite(canvas,body)
    if not transparent:result=Image.alpha_composite(Image.new('RGBA',result.size,(250,250,249,255)),result).convert('RGB')
    if output:
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
        result.save(output,dpi=(300,300))
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cover',type=Path,default=DEFAULT)
    parser.add_argument('--output',type=Path,default=ROOT/'deliverables'/'抱枕渲染_透明底.png')
    parser.add_argument('--width',type=int,default=2400)
    parser.add_argument('--ratio',choices=RATIOS,default='1:1')
    parser.add_argument('--fullness',type=float,default=.9)
    parser.add_argument('--wrinkles',type=float,default=1.)
    parser.add_argument('--gloss',type=float,default=.35)
    parser.add_argument('--fit',choices=['crop','contain'],default='crop')
    parser.add_argument('--rotate-x',type=float,default=0)
    parser.add_argument('--rotate-y',type=float,default=0)
    parser.add_argument('--rotate-z',type=float,default=0)
    args=parser.parse_args()
    render_pillow(args.cover,args.output,args.width,args.ratio,args.fullness,args.wrinkles,args.gloss,args.fit,
                  args.rotate_x,args.rotate_y,args.rotate_z)
    print(args.output)
