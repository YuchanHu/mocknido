"""Browser-based local UI; binds only to loopback, no external requests."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64
import io
import json
import tempfile
import webbrowser
import uuid
from math import gcd
from urllib.parse import urlparse,parse_qs


def launch(render, default):
    from render_photobook import cover_dimensions
    default_w, default_h = cover_dimensions(default)
    divisor = gcd(default_w, default_h)
    default_size = f'{default_w} × {default_h} 像素 · 画册 {default_w//divisor}:{default_h//divisor}'
    page = Path(__file__).with_suffix('.html').read_text(encoding='utf-8').replace('__DEFAULT_SIZE__',default_size).encode('utf-8')
    uploads = tempfile.TemporaryDirectory(prefix='photobook_session_')
    sources = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            route=urlparse(self.path)
            if route.path=='/app.js':
                self.send_response(200);self.send_header('Content-Type','text/javascript; charset=utf-8');self.end_headers()
                self.wfile.write(Path(__file__).with_name('mockup_app.js').read_bytes());return
            if route.path=='/films':
                from render_instant import FILMS
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps(FILMS,ensure_ascii=False).encode());return
            if route.path=='/source':
                from render_photobook import read_cover
                try:
                    token=parse_qs(route.query).get('cover',[''])[0]
                    image=read_cover(sources[token] if token else default)
                    w,h=image.size;image.thumbnail((1600,1600))
                    buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=94)
                    self.send_response(200);self.send_header('Content-Type','image/jpeg')
                    self.send_header('X-Image-Width',str(w));self.send_header('X-Image-Height',str(h));self.end_headers()
                    self.wfile.write(buffer.getvalue())
                except Exception as exc:self.send_error(400,str(exc))
                return
            if self.path != '/':
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self):
            # Reject cross-site requests; the UI is intended for this local origin only.
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + self.headers.get('Host', ''):
                self.send_error(403)
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length < 100_000_000:
                    raise ValueError('图片过大（上限约 70 MB）')
                if self.path == '/cover':
                    token = uuid.uuid4().hex
                    path = Path(uploads.name) / token
                    path.write_bytes(self.rfile.read(length))
                    from PIL import Image
                    with Image.open(path) as check:
                        check.verify()
                    sources[token] = path
                    cover_w, cover_h = cover_dimensions(path)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'token':token,'width':cover_w,'height':cover_h}).encode())
                    return
                if self.path != '/render':
                    self.send_error(404)
                    return
                data = json.loads(self.rfile.read(length))
                width = int(data.get('width', 800))
                if width not in (800, 1600, 2400, 3600):
                    raise ValueError('不支持的导出尺寸')
                with tempfile.TemporaryDirectory(prefix='photobook_') as tmp:
                    source = sources[data['cover']] if data.get('cover') else default
                    if data.get('image'):
                        source = Path(tmp) / 'cover'
                        source.write_bytes(base64.b64decode(data['image'].split(',', 1)[1], validate=True))
                    kind = data.get('kind','book')
                    common = dict(width=width, gloss=max(0,min(1.5,float(data['gloss']))),
                                  rotate_x=float(data.get('rotate_x',22)),
                                  rotate_y=float(data.get('rotate_y',14)),
                                  rotate_z=float(data.get('rotate_z',-13)), transparent=True)
                    if kind == 'pillow':
                        from render_pillow import render_pillow
                        result = render_pillow(source, **common,
                                               ratio=data.get('pillow_ratio','1:1'),
                                               fullness=float(data['thickness']),
                                               wrinkles=float(data.get('wrinkles',1)),
                                               fit=data.get('fit','crop'),crop=data.get('crop'))
                    elif kind == 'instant':
                        from render_instant import render_instant
                        result=render_instant(source,**common,film=data.get('film','polaroid'),
                                              fit=data.get('fit','crop'),crop=data.get('crop'))
                    elif kind == 'book':
                        result = render(source, **common, thickness=max(.2,min(2,float(data['thickness']))))
                    else:
                        raise ValueError('不支持的功能菜单')
                    output = io.BytesIO()
                    preview = width == 800
                    result.save(output, format='PNG', compress_level=1 if preview else 6,
                                dpi=(300,300))
                self.send_response(200)
                self.send_header('Content-Type', 'image/png')
                self.end_headers()
                self.wfile.write(output.getvalue())
            except Exception as exc:
                self.send_response(400)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(str(exc).encode('utf-8'))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    url = f'http://127.0.0.1:{server.server_port}'
    print('Photobook renderer: ' + url, flush=True)
    print('Keep this window open. Press Ctrl+C to stop.', flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        uploads.cleanup()
