"""Offline smoke test using the bundled interpreter."""
from pathlib import Path
import json
import queue
import sys
import threading
import urllib.request
import numpy as np
from PIL import Image
from render_photobook import ROOT, DEFAULT, render
from render_pillow import render_pillow
from render_instant import render_instant
import photobook_ui as ui

assert Path(sys.executable).resolve().is_relative_to(ROOT / "runtime")
assert all(str(ROOT) in path for path in sys.path if path)
for name, image in [("book", render(DEFAULT, width=400)),
                    ("pillow", render_pillow(DEFAULT, width=400)),
                    ("instant", render_instant(DEFAULT, width=400))]:
    assert image.mode == "RGBA" and image.width == 400
    alpha = np.asarray(image)[:, :, 3]
    assert alpha.min() == 0 and alpha.max() > 0
    print("PASS render:", name, flush=True)
urls = queue.Queue()
ui.webbrowser.open = urls.put
threading.Thread(target=ui.launch, args=(render, DEFAULT), daemon=True).start()
url = urls.get(timeout=15)
for endpoint in ("/", "/app.js", "/films", "/source"):
    with urllib.request.urlopen(url + endpoint, timeout=30) as response:
        assert response.status == 200 and response.read()
body = json.dumps(dict(width=800, gloss=.5, thickness=.9, kind="book")).encode()
request = urllib.request.Request(url + "/render", data=body, headers={"Content-Type":"application/json"})
with urllib.request.urlopen(request, timeout=60) as response:
    assert response.status == 200
    assert response.read(8) == b"\x89PNG\r\n\x1a\n"
print("PASS portable isolation, default assets, HTTP UI and PNG export", flush=True)
