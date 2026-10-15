"""Local Edge smoke check for mode isolation, uploads, dragging and RGBA export."""
import base64
import json
import queue
import subprocess
import tempfile
import os
import shutil
import threading
import time
import urllib.request
from pathlib import Path
import websocket
from PIL import Image
import numpy as np
import photobook_ui as ui
from render_photobook import render, DEFAULT, ROOT


def find_browser():
    configured = os.environ.get('MOCKNIDO_BROWSER')
    if configured and Path(configured).is_file():
        return configured
    for name in ('msedge', 'msedge.exe', 'google-chrome', 'chromium'):
        found = shutil.which(name)
        if found:
            return found
    for variable in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
        base = os.environ.get(variable)
        if base:
            for relative in ('Microsoft/Edge/Application/msedge.exe', 'Google/Chrome/Application/chrome.exe'):
                candidate = Path(base) / relative
                if candidate.is_file():
                    return str(candidate)
    raise RuntimeError('Set MOCKNIDO_BROWSER to an Edge or Chrome executable.')


def main(extra_checks=None):
    urls=queue.Queue();ui.webbrowser.open=urls.put
    threading.Thread(target=ui.launch,args=(render,DEFAULT),daemon=True).start()
    url=urls.get(timeout=10)
    with tempfile.TemporaryDirectory(prefix='pillow_browser_') as tmp:
        profile=Path(tmp)/'profile';downloads=Path(tmp)/'downloads';downloads.mkdir()
        process=subprocess.Popen([
            find_browser(),
            '--headless','--disable-gpu','--no-sandbox','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check',
            '--remote-debugging-port=0','--remote-allow-origins=*',
            '--user-data-dir='+str(profile),'--window-size=1440,1100',url],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        ws=None
        try:
            for _ in range(100):
                if (profile/'DevToolsActivePort').exists():break
                time.sleep(.1)
            port=(profile/'DevToolsActivePort').read_text().splitlines()[0]
            for _ in range(100):
                pages=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json'))
                pages=[p for p in pages if p.get('type')=='page' and p.get('url','').startswith(url)]
                if pages:break
                time.sleep(.1)
            ws=websocket.create_connection(pages[0]['webSocketDebuggerUrl'],timeout=30)
            serial=0
            def call(method,params=None):
                nonlocal serial
                serial+=1;ws.send(json.dumps({'id':serial,'method':method,'params':params or {}}))
                while True:
                    msg=json.loads(ws.recv())
                    if msg.get('id')==serial:
                        if 'error' in msg:raise RuntimeError(msg['error'])
                        return msg.get('result',{})
            def evaluate(expression):
                answer=call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
                if 'exceptionDetails' in answer:raise RuntimeError(answer['exceptionDetails'])
                return answer.get('result',{}).get('value')
            def wait(expression):
                for _ in range(200):
                    if evaluate(expression):return
                    time.sleep(.1)
                raise AssertionError('Timed out: '+expression)
            ready="!busy&&!pending&&!uploading&&el('image').naturalWidth>0"
            wait("typeof busy !== 'undefined' && "+ready)
            if extra_checks:
                extra_checks(evaluate,wait,call,ready,Path(tmp),downloads)
            evaluate("el('rotate_x').value=31;el('rotate_x').oninput();el('pillow-tab').click()")
            wait(ready)
            assert evaluate("mode==='pillow'&&!el('pillow-options').hidden&&el('book-options').hidden")
            assert evaluate("Number(el('rotate_x').value)===0")
            for ratio in ['2:3','1:2','1:1']:
                evaluate("el('pillow_ratio').value="+json.dumps(ratio)+";el('pillow_ratio').onchange()")
                wait(ready)
                assert evaluate("el('status').textContent.includes('已更新')")
            evaluate("el('pillow_ratio').value='2:3';el('pillow_ratio').onchange()")
            wait(ready)
            box=evaluate("(()=>{const r=el('image').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
            call('Input.dispatchMouseEvent',{'type':'mousePressed',**box,'button':'left','clickCount':1})
            call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':box['x']+70,'y':box['y']-35,'button':'left','buttons':1})
            call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':box['x']+70,'y':box['y']-35,'button':'left','clickCount':1})
            wait(ready)
            assert evaluate("Number(el('rotate_y').value)!==0")
            # Each menu retains its own image and controls.
            custom=Path(tmp)/'replacement.png';Image.new('RGB',(400,600),'#6688aa').save(custom)
            doc=call('DOM.getDocument')['root']['nodeId']
            node=call('DOM.querySelector',{'nodeId':doc,'selector':'#file'})['nodeId']
            call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(custom)]})
            wait("!uploading&&cover!==null&&"+ready)
            token=evaluate('cover')
            evaluate("el('book-tab').click()")
            wait(ready)
            assert evaluate("cover===null&&Number(el('rotate_x').value)===31")
            evaluate("el('pillow-tab').click()")
            wait(ready)
            assert evaluate('cover')==token
            assert evaluate("el('pillow_ratio').value")=='2:3'
            # Restore the bundled sample for the export check.
            call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(DEFAULT)]})
            wait("!uploading&&el('filename').textContent==='sample.png'&&"+ready)
            evaluate("el('reset').click()")
            wait(ready)
            screenshot=call('Page.captureScreenshot',{'format':'png'})['data']
            (ROOT/'deliverables'/'抱枕操作界面.png').write_bytes(base64.b64decode(screenshot))
            call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(downloads)})
            evaluate("el('width').value='1600';el('save').click()")
            wait('!exporting')
            for _ in range(100):
                files=list(downloads.glob('*.png'))
                if files:break
                time.sleep(.1)
            im=Image.open(files[0]);a=np.asarray(im)
            assert im.mode=='RGBA' and im.size==(1600,1792)
            assert a[0,0,3]==0 and np.any((a[:,:,3]>0)&(a[:,:,3]<150))
            assert np.count_nonzero(a[:,:,3]==255)>100000
            print('PASS: browser menus, 3 presets, pointer drag, replacement image, per-menu state, transparent PNG download')
        finally:
            if ws:
                try:call('Browser.close')
                except Exception:pass
                ws.close()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=10)


if __name__=='__main__':main()
