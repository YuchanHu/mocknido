"""Real browser checks for film formats, locked crops, state and RGBA download."""
import base64
import json
import time
from PIL import Image
import numpy as np
from check_pillow_ui import main
from render_photobook import ROOT


def check(evaluate,wait,call,ready,tmp,downloads):
    evaluate("el('instant-tab').click()")
    wait(ready)
    assert evaluate("mode==='instant'&&!el('instant-options').hidden&&el('thickness').hidden")
    for mode,field,presets in [('instant','film',['polaroid','mini','wide']),('pillow','pillow_ratio',['1:1','2:3','1:2'])]:
        evaluate(f"el('{mode}-tab').click()")
        wait(ready)
        for preset in presets:
            evaluate(f"el('{field}').value={json.dumps(preset)};el('{field}').onchange()")
            wait(ready)
            assert evaluate("crop===null&&el('fit').value==='crop'")
            evaluate("el('fit').value='manual';el('fit').onchange()")
            wait("editor!==null&&!el('crop-apply').disabled")
            assert evaluate("Math.abs(editor.rect.w*editor.iw/(editor.rect.h*editor.ih)-targetAspect())<1e-9")
            evaluate("el('crop-zoom').value=2;el('crop-zoom').oninput()")
            if mode=='instant' and preset=='wide':
                evaluate("editor.rect.y=.16;cropClamp();drawCrop()")
            before=evaluate('editor.rect.x')
            box=evaluate("(()=>{const b=canvas.getBoundingClientRect(),d=editor.display,r=editor.rect;return {x:b.x+(d.x+(r.x+r.w/2)*d.w)*b.width/900,y:b.y+(d.y+(r.y+r.h/2)*d.h)*b.height/600}})()")
            call('Input.dispatchMouseEvent',{'type':'mousePressed',**box,'button':'left','clickCount':1})
            call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':box['x']+20,'y':box['y']-10,'button':'left','buttons':1})
            call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':box['x']+20,'y':box['y']-10,'button':'left','clickCount':1})
            assert evaluate('editor.rect.x')>before
            assert evaluate("Math.abs(editor.rect.w*editor.iw/(editor.rect.h*editor.ih)-targetAspect())<1e-9")
            if mode=='instant' and preset=='wide':
                screenshot=call('Page.captureScreenshot',{'format':'png'})['data']
                (ROOT/'deliverables'/'手动裁切操作界面.png').write_bytes(base64.b64decode(screenshot))
            expected=evaluate('JSON.stringify(editor.rect)')
            evaluate("el('crop-apply').click()")
            wait(ready)
            assert evaluate("el('status').textContent.includes('已更新')&&el('fit').value==='manual'")
            assert evaluate('JSON.stringify(crop)')==expected
            # Cancel retains the previous crop and fit, even after editing zoom.
            evaluate("el('edit-crop').click()")
            wait('editor!==null')
            evaluate("el('crop-zoom').value=3;el('crop-zoom').oninput();el('crop-cancel').click()")
            assert evaluate('JSON.stringify(crop)')==expected
        saved=evaluate('JSON.stringify(crop)')
        evaluate("el('book-tab').click()")
        wait(ready)
        evaluate(f"el('{mode}-tab').click()")
        wait(ready)
        assert evaluate('JSON.stringify(crop)')==saved
    # Cancel a newly selected manual mode restores contain.
    evaluate("el('fit').value='contain';el('fit').onchange()")
    wait(ready)
    evaluate("el('fit').value='manual';el('fit').onchange()")
    wait('editor!==null')
    evaluate("el('crop-cancel').click()")
    assert evaluate("el('fit').value==='contain'")
    # Upload clears a crop made against the previous image and uses oriented dimensions.
    custom=tmp/'crop_source.jpg'
    im=Image.new('RGB',(600,400),'#7b9caa');exif=im.getexif();exif[274]=6;im.save(custom,exif=exif)
    doc=call('DOM.getDocument')['root']['nodeId']
    node=call('DOM.querySelector',{'nodeId':doc,'selector':'#file'})['nodeId']
    call('DOM.setFileInputFiles',{'nodeId':node,'files':[str(custom)]})
    wait("!uploading&&el('filename').textContent==='crop_source.jpg'&&"+ready)
    assert evaluate('crop===null')
    evaluate("el('edit-crop').click()")
    wait('editor!==null')
    assert evaluate('editor.iw===400&&editor.ih===600')
    evaluate("el('crop-cancel').click();el('instant-tab').click()")
    wait(ready)
    assert evaluate("el('film').value==='wide'&&el('fit').value==='manual'&&crop!==null")
    # Instant mode shares the 3D pointer controls.
    box=evaluate("(()=>{const r=el('image').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()")
    call('Input.dispatchMouseEvent',{'type':'mousePressed',**box,'button':'left','clickCount':1})
    call('Input.dispatchMouseEvent',{'type':'mouseMoved','x':box['x']+35,'y':box['y']-15,'button':'left','buttons':1})
    call('Input.dispatchMouseEvent',{'type':'mouseReleased','x':box['x']+35,'y':box['y']-15,'button':'left','clickCount':1})
    wait(ready)
    assert evaluate("Number(el('rotate_y').value)!==0")
    screenshot=call('Page.captureScreenshot',{'format':'png'})['data']
    (ROOT/'deliverables'/'拍立得操作界面.png').write_bytes(base64.b64decode(screenshot))
    call('Browser.setDownloadBehavior',{'behavior':'allow','downloadPath':str(downloads)})
    evaluate("el('width').value='1600';el('save').click()")
    wait('!exporting')
    path=downloads/'拍立得_wide_透明底.png'
    for _ in range(100):
        if path.exists():break
        time.sleep(.1)
    image=Image.open(path);a=np.asarray(image)
    assert image.mode=='RGBA' and image.size==(1600,1792)
    assert a[0,0,3]==0 and np.any((a[:,:,3]>0)&(a[:,:,3]<150))
    image.close();path.unlink()
    # Restore clean defaults for the existing book/pillow regression suite.
    evaluate("sessions.pillow={...defaults};el('book-tab').click()")
    wait(ready)
    print('PASS: 3 film formats, 6 locked crop ratios, real pointer selection, zoom, cancellation, EXIF upload, independent state, instant rotation and RGBA download')


if __name__=='__main__':main(check)
