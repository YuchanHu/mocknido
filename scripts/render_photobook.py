"""Photobook rendering with perspective, lighting and transparent shadows."""
from pathlib import Path
import argparse
import io
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageCms

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'sample.png'
OUTPUT = ROOT / 'deliverables' / '画册封面渲染_透明底.png'


def cover_dimensions(path):
    """Read the displayed dimensions, including camera EXIF orientation."""
    with Image.open(path) as image:
        w, h = image.size
        if image.getexif().get(274) in (5, 6, 7, 8):
            w, h = h, w
        return w, h


def read_cover(path):
    with Image.open(path) as src:
        src = ImageOps.exif_transpose(src)
        profile = src.info.get('icc_profile')
        if profile:
            try:
                return ImageCms.profileToProfile(src, ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                                                ImageCms.createProfile('sRGB'), outputMode='RGB')
            except (ValueError, OSError, ImportError):
                if b'sRGB' not in profile:
                    raise RuntimeError('此 Python 的 Pillow 缺少色彩管理模块；请使用 sRGB 封面，或安装完整 Pillow。')
        return src.convert('RGB')


def perspective(texture, corners, size):
    """Find inverse homography from output quadrilateral to texture pixels."""
    tw, th = texture.size
    matrix, rhs = [], []
    for (x, y), (u, v) in zip(corners, [(0, 0), (tw, 0), (tw, th), (0, th)]):
        matrix.extend([[x, y, 1, 0, 0, 0, -u*x, -u*y],
                       [0, 0, 0, x, y, 1, -v*x, -v*y]])
        rhs.extend([u, v])
    if abs(np.cross(np.asarray(corners[1])-corners[0], np.asarray(corners[3])-corners[0])) < .02:
        return Image.new('RGBA', size)
    coeff = np.linalg.solve(np.array(matrix), np.array(rhs))
    return texture.transform(size, Image.Transform.PERSPECTIVE, coeff,
                             Image.Resampling.BICUBIC)


@lru_cache(maxsize=4)
def preview_cover(path, modified):
    image = read_cover(path)
    image.thumbnail((1200, 1800), Image.Resampling.LANCZOS)
    return image


def book_geometry(width, thickness, rotate_x=22, rotate_y=14, rotate_z=-13, aspect=2/3):
    """Rotate a book matching the cover aspect, then project through a camera."""
    if not np.isfinite(aspect) or aspect <= 0:
        raise ValueError('封面宽高比必须为正数')
    angles = np.asarray([rotate_x, rotate_y, rotate_z], dtype=float)
    if not np.all(np.isfinite(angles)) or abs(rotate_x)>55 or abs(rotate_y)>55 or abs(rotate_z)>180:
        raise ValueError('X/Y 角度范围为 -55° 至 55°，Z 为 -180° 至 180°')
    x, y, z = np.radians(angles)
    cx, sx, cy, sy, cz, sz = np.cos(x), np.sin(x), np.cos(y), np.sin(y), np.cos(z), np.sin(z)
    rotation = np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]]) @ np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]]) @ np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
    # Normalize the longest side so wide covers stay safely in front of the camera.
    half_h = 1/max(1, aspect)
    half_w = aspect*half_h
    front = np.array([[-half_w,-half_h,0],[half_w,-half_h,0],
                      [half_w,half_h,0],[-half_w,half_h,0]])
    back = front + [0,0,-.085*thickness]
    vertices = np.concatenate([front,back]) @ rotation.T
    projected = vertices[:,:2] * (6/(6-vertices[:,2:3]))
    span = np.ptp(projected,axis=0)
    factor = min(445, 860/span[0], 970/span[1]) * width/1000
    center = (projected.min(axis=0)+projected.max(axis=0))/2
    screen = (projected-center)*factor + np.array([.5,.55])*width
    return screen[:4], screen[4:], rotation


def render(source, output=None, width=2400, thickness=0.9, gloss=0.85, fit='contain',
           rotate_x=22, rotate_y=14, rotate_z=-13, transparent=True):
    size = (int(width), round(width * 1.12))
    scale = width / 1000
    source_w, source_h = cover_dimensions(source)
    aspect = source_w/source_h
    q, base, rotation = book_geometry(width, thickness, rotate_x, rotate_y, rotate_z, aspect)
    # Shadows retain their own alpha; no white matte is baked into the export.
    canvas = Image.new('RGBA', size, (0, 0, 0, 0))

    def polygon(points, color):
        ImageDraw.Draw(canvas).polygon([tuple(p) for p in points], fill=color)

    # Area-light penumbra + narrower contact shadow, both anchored to the book.
    for shift, blur, alpha in [((10, 15), 13, 38), ((4, 7), 5, 49), ((1, 2), 1.5, 52)]:
        mask = Image.new('L', size)
        pts = base + np.array(shift) * scale
        ImageDraw.Draw(mask).polygon([tuple(p) for p in pts], fill=alpha)
        mask = mask.filter(ImageFilter.GaussianBlur(blur * scale))
        layer = Image.new('RGBA', size, (58, 53, 48, 0))
        layer.putalpha(mask)
        canvas = Image.alpha_composite(canvas, layer)

    image = (preview_cover(str(Path(source).resolve()), Path(source).stat().st_mtime_ns).copy()
             if width <= 800 else read_cover(source))
    texture_scale = width*1.02/max(source_w, source_h)
    texsize = (max(1, round(source_w*texture_scale)), max(1, round(source_h*texture_scale)))
    # The entire image maps to a cover of the same ratio. Legacy fit is ignored.
    image = image.resize(texsize, Image.Resampling.LANCZOS)

    # Deterministic material response in cover coordinates. Broad softbox reflection,
    # narrow spine roll, hinge groove and edge falloff. No painted content is added.
    w, h = texsize
    u = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    v = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    shade = 1 - .13*np.exp(-u/.018) - .065*np.exp(-((u-.032)/.008)**2)
    shade = shade - .04*u - .018*v
    # A broad reflected rectangular softbox, with Gaussian-softened boundaries.
    # It runs down the right side, leaving facial detail unobscured.
    softbox = Image.new('L', texsize)
    light_shift = (rotate_y-14)*.006 + (rotate_x-22)*.003
    ImageDraw.Draw(softbox).polygon([(int((x+light_shift)*w), int(y*h)) for x, y in
        [(.30, -.15), (.61, -.15), (1.20, .95), (.99, .95)]], fill=255)
    softbox = np.asarray(softbox.filter(ImageFilter.GaussianBlur(w*.022)), dtype=np.float32)/255
    highlight = np.clip((.12*np.exp(-((u-.016)/.009)**2)
                 + .39*softbox*(1-.48*v)
                 + .075*np.exp(-((u-.43-light_shift-.52*v)/.022)**2)) * gloss, 0, .8)
    arr = np.asarray(image, dtype=np.float32) / 255
    # Apply material lighting in linear light, then encode back into sRGB.
    linear = np.where(arr <= .04045, arr/12.92, ((arr+.055)/1.055)**2.4)
    linear = linear*shade[..., None]
    linear = linear*(1-highlight[..., None]) + highlight[..., None]
    srgb = np.where(linear <= .0031308, linear*12.92, 1.055*np.maximum(linear, 0)**(1/2.4)-.055)
    texture = Image.fromarray(np.uint8(np.clip(srgb*255, 0, 255))).convert('RGBA')
    # Blur only the rolled spine margin, never the full cover artwork.
    seam_mask = np.broadcast_to(np.uint8(255*np.exp(-(u/.012)**2)), (h, w)).copy()
    texture = Image.composite(texture.filter(ImageFilter.GaussianBlur(w*.003)), texture,
                              Image.fromarray(seam_mask))
    # Wrapped cover material: the actual left photo edge continues onto the spine.
    # Mirror its narrow margin so the inner spine edge meets the same cover pixels.
    strip = ImageOps.mirror(texture.crop((0, 0, min(w, max(8, round(w*.024))), h)))
    strip = strip.filter(ImageFilter.GaussianBlur(max(.5, w*.0012)))
    strip_arr = np.asarray(strip).copy()
    roll = np.linspace(.72, 1, strip.width, dtype=np.float32)[None, :, None]
    strip_arr[:, :, :3] = (strip_arr[:, :, :3]*roll).astype(np.uint8)
    strip = Image.fromarray(strip_arr)
    polygon(base, (126, 124, 128, 255))
    if (rotation @ [-1,0,0])[2] > 1e-6:
        canvas = Image.alpha_composite(canvas, perspective(strip, [base[0], q[0], q[3], base[3]], size))

    # Render only visible end faces, so top/right pages appear when the book turns.
    for a, b, normal, edge in [
        (3,2,[0,1,0],texture.crop((0,max(0,h-5),w,h))),
        (0,1,[0,-1,0],texture.crop((0,0,w,min(5,h)))),
        (1,2,[1,0,0],texture.crop((max(0,w-5),0,w,h)).transpose(Image.Transpose.ROTATE_90))]:
        if (rotation @ normal)[2] <= 1e-6:
            continue
        da, db = base[a]-q[a], base[b]-q[b]
        canvas = Image.alpha_composite(canvas, perspective(edge,
            [q[a]+da*.88,q[b]+db*.88,base[b],base[a]],size))
        length = np.linalg.norm(q[b]-q[a])
        axis = (q[b]-q[a])/length*min(3*scale, length*.1)
        left,right = q[a]+axis,q[b]-axis
        polygon([left+da*.16,right+db*.16,right+db*.87,left+da*.87],(221,218,208,255))
        draw = ImageDraw.Draw(canvas)
        for i,t in enumerate(np.linspace(.20,.83,max(5,round(thickness*15)))):
            color = (185,182,173,255) if i%3==0 else (240,237,227,255)
            draw.line([tuple(left+da*t),tuple(right+db*t)],fill=color,width=max(1,round(scale*.3)))
        draw.line([tuple(left+da*.17),tuple(right+db*.17)],fill=(111,108,104,255),width=max(1,round(scale*.7)))
        canvas = Image.alpha_composite(canvas,perspective(edge,[q[a],q[b],q[b]+db*.13,q[a]+da*.13],size))
    canvas = Image.alpha_composite(canvas, perspective(texture, q, size))
    edges = Image.new('RGBA', size)
    d = ImageDraw.Draw(edges)
    d.line([tuple(q[3]), tuple(q[0]), tuple(q[1])], fill=(255, 255, 249, 105), width=max(1, round(scale*.6)))
    d.line([tuple(q[1]), tuple(q[2]), tuple(q[3])], fill=(53, 51, 47, 55), width=max(1, round(scale*.45)))
    result = Image.alpha_composite(canvas, edges)
    if not transparent:
        result = Image.alpha_composite(Image.new('RGBA', size, (250,250,249,255)), result).convert('RGB')
    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        except ImportError:
            with Image.open(source) as original:
                profile = original.info.get('icc_profile')
        result.save(output, dpi=(300, 300), **({'icc_profile': profile} if profile else {}))
    return result


def gui():
    from photobook_ui import launch
    launch(render, DEFAULT)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cover', type=Path, default=DEFAULT)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--width', type=int, default=2400)
    parser.add_argument('--thickness', type=float, default=.9)
    parser.add_argument('--gloss', type=float, default=.85)
    parser.add_argument('--fit', choices=['contain', 'crop'], default='contain', help=argparse.SUPPRESS)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--rotate-x', type=float, default=22)
    parser.add_argument('--rotate-y', type=float, default=14)
    parser.add_argument('--rotate-z', type=float, default=-13)
    parser.add_argument('--opaque', action='store_true', help='Use a white background instead of transparent PNG')
    args = parser.parse_args()
    if args.gui:
        gui()
    else:
        if not 400 <= args.width <= 5000:
            parser.error('--width must be between 400 and 5000')
        render(args.cover, args.output, args.width, args.thickness, args.gloss, args.fit,
               args.rotate_x, args.rotate_y, args.rotate_z, transparent=not args.opaque)
        print(args.output)
