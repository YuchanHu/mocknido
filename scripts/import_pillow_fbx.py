"""Read the supplied binary FBX mesh without requiring a DCC installation."""
from pathlib import Path
import struct
import zlib
import numpy as np
from functools import lru_cache


def read_fbx(path):
    data=Path(path).read_bytes()
    if not data.startswith(b'Kaydara FBX Binary'):raise ValueError('Expected binary FBX')
    version=struct.unpack_from('<I',data,23)[0]
    wide=version>=7500
    header='<QQQB' if wide else '<IIIB'
    hs=struct.calcsize(header)
    def node(pos):
        end,count,_,length=struct.unpack_from(header,data,pos)
        if not end:return None,pos+hs
        pos+=hs;name=data[pos:pos+length].decode();pos+=length;props=[]
        for _ in range(count):
            kind=chr(data[pos]);pos+=1
            if kind in 'YCI LFD'.replace(' ',''):
                fmt={'Y':'h','C':'?','I':'i','L':'q','F':'f','D':'d'}[kind]
                value=struct.unpack_from('<'+fmt,data,pos)[0];pos+=struct.calcsize(fmt)
            elif kind in 'fdlibc':
                size,encoding,packed=struct.unpack_from('<III',data,pos);pos+=12
                raw=data[pos:pos+packed];pos+=packed
                if encoding:raw=zlib.decompress(raw)
                dtype={'f':'<f4','d':'<f8','l':'<i8','i':'<i4','b':'u1','c':'u1'}[kind]
                value=np.frombuffer(raw,dtype=dtype,count=size).copy()
            elif kind in 'SR':
                size=struct.unpack_from('<I',data,pos)[0];pos+=4
                value=data[pos:pos+size];pos+=size
                if kind=='S':value=value.decode('utf-8',errors='replace')
            else:raise ValueError('Unsupported FBX property '+kind)
            props.append(value)
        children=[]
        while pos<end:
            child,pos=node(pos)
            if child is None:break
            children.append(child)
        return {'name':name,'props':props,'children':children},end
    roots=[];pos=27
    while True:
        item,pos=node(pos)
        if item is None:break
        roots.append(item)
    return roots


def child(node,name):
    return next(c for c in node['children'] if c['name']==name)


@lru_cache(maxsize=2)
def load_square(path, modified):
    roots=read_fbx(path)
    objects=next(n for n in roots if n['name']=='Objects')
    geometry=child(objects,'Geometry');model=child(objects,'Model')
    properties={p['props'][0]:p['props'][4:] for p in child(model,'Properties70')['children']}
    scale=np.asarray(properties['Lcl Scaling'],dtype=float)
    vertices=child(geometry,'Vertices')['props'][0].reshape(-1,3)*scale
    # The supplied object lies flat in FBX space. Its broad local XY plane is
    # displayed upright: X right, -Y down, local Z towards the viewer.
    center=(vertices.max(0)+vertices.min(0))/2
    half_height=np.ptp(vertices[:,1])/2
    vertices=(vertices-center)/half_height
    vertices[:,1]*=-1
    indices=child(geometry,'PolygonVertexIndex')['props'][0]
    ends=np.flatnonzero(indices<0)
    if not np.all(np.diff(np.r_[-1,ends])==4):raise ValueError('Expected the supplied quad pillow mesh')
    vertex_ids=np.where(indices<0,-indices-1,indices).reshape(-1,4)
    normals=child(child(geometry,'LayerElementNormal'),'Normals')['props'][0].reshape(-1,3)/scale
    normals[:,1]*=-1;normals/=np.maximum(1e-12,np.linalg.norm(normals,axis=1,keepdims=True))
    layer=child(geometry,'LayerElementUV')
    original_uv=child(layer,'UV')['props'][0].reshape(-1,2)[child(layer,'UVIndex')['props'][0]]
    # Small-scale smoothing provides a detail-strength control around the original
    # sculpt, rather than adding unrelated procedural folds.
    from scipy.sparse import coo_matrix
    edges=np.concatenate([vertex_ids[:,[0,1]],vertex_ids[:,[1,2]],vertex_ids[:,[2,3]],vertex_ids[:,[3,0]]])
    edges=np.concatenate([edges,edges[:,::-1]])
    adjacency=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(vertices),len(vertices))).tocsr()
    sums=np.asarray(adjacency.sum(axis=1)).ravel()
    smooth=vertices.copy()
    for _ in range(32):smooth=.3*smooth+.7*(adjacency@smooth)/sums[:,None]
    expanded=vertices[vertex_ids.ravel()]
    uv=(expanded[:,:2]-vertices[:,:2].min(0))/np.ptp(vertices[:,:2],axis=0)
    quads=np.arange(len(indices),dtype=np.int32).reshape(-1,4)
    faces=np.concatenate([quads[:,[0,1,2]],quads[:,[0,2,3]]])
    front=np.mean(expanded[faces,2],axis=1)>=0
    return vertices,smooth,vertex_ids,faces,normals,uv,front,original_uv


def square_render_mesh(aspect=1,fullness=.9,wrinkles=1):
    path=Path(__file__).resolve().parents[1]/'pillow_obj'/'pillow_squ.fbx'
    vertices,smooth,ids,faces,normals,uv,front,_=load_square(str(path),path.stat().st_mtime_ns)
    shape=smooth+(vertices-smooth)*wrinkles
    transform=np.array([aspect,1,fullness/.9])
    if abs(wrinkles-1)<1e-8:
        n=normals/transform
    else:
        triangles=ids.ravel()[faces]
        tri=shape[triangles]
        face_normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        # Canonical Y reflection reverses triangle winding.
        accum=np.zeros_like(shape)
        for k in range(3):np.add.at(accum,triangles[:,k],-face_normals)
        n=accum[ids.ravel()]/transform
    n=n/np.maximum(1e-12,np.linalg.norm(n,axis=1,keepdims=True))
    return np.ascontiguousarray(shape[ids.ravel()]*transform),n,uv,faces,front


if __name__=='__main__':
    roots=read_fbx(Path(__file__).resolve().parents[1]/'pillow_obj/pillow_squ.fbx')
    def show(nodes,depth=0):
        for item in nodes:
            props=[f'array {p.shape} range {p.min():.4g}..{p.max():.4g}' if isinstance(p,np.ndarray) else repr(p)[:160] for p in item['props']]
            print(' '*depth+item['name']+' '+str(props))
            show(item['children'],depth+1)
    show([n for n in roots if n['name'] in ('Objects','Connections','GlobalSettings')])
