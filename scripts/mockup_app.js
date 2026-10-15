const el=id=>document.getElementById(id);
const modes=['book','pillow','instant'];
let cover=null,mode='book',modeEpoch=0,previewUrl=null,revision=0,busy=false,pending=false,timer=null,uploading=false,exporting=false,crop=null,films={};
const controls=[['rotate_x','xv','°'],['rotate_y','yv','°'],['rotate_z','zv','°'],['thickness','tv',''],['gloss','gv',''],['wrinkles','wv','']];
const fields=['rotate_x','rotate_y','rotate_z','thickness','gloss','wrinkles','pillow_ratio','film','fit','width'];
function values(width){return {kind:mode,cover,crop,width,pillow_ratio:el('pillow_ratio').value,film:el('film').value,fit:el('fit').value,wrinkles:+el('wrinkles').value,thickness:+el('thickness').value,gloss:+el('gloss').value,rotate_x:+el('rotate_x').value,rotate_y:+el('rotate_y').value,rotate_z:+el('rotate_z').value}}
function labels(){for(const [id,out,suffix] of controls)el(out).value=el(id).value+suffix}
let lastFit='crop';
function schedule(){revision++;pending=true;if(!timer)timer=setTimeout(()=>{timer=null;preview()},65)}
for(const [id] of controls)el(id).oninput=()=>{labels();schedule()};
const initialRatio=el('ratio').textContent;
const defaults={cover:null,crop:null,filename:'当前：sample.png',ratio:initialRatio,rotate_x:0,rotate_y:0,rotate_z:0,thickness:.9,gloss:.35,wrinkles:1,pillow_ratio:'1:1',film:'polaroid',fit:'crop',width:2400};
const sessions={book:null,pillow:{...defaults},instant:{...defaults,rotate_z:-8}};
function targetAspect(){if(mode==='pillow'){const [w,h]=el('pillow_ratio').value.split(':').map(Number);return w/h}const spec=films[el('film').value];return spec.image[0]/spec.image[1]}
function formatInfo(){const spec=films[el('film').value];if(spec)el('film-dimensions').textContent=`宽 × 高：相纸 ${spec.paper.join(' × ')} mm；成像区 ${spec.image.join(' × ')} mm`;el('crop-info').textContent=crop&&el('fit').value==='manual'?'已应用手动裁切；切换比例后需重新选择。':'裁切比例自动锁定为当前画面比例。'}
function switchMode(next){
 if(next===mode||uploading)return;
 sessions[mode]={...values(+el('width').value),filename:el('filename').textContent,ratio:el('ratio').textContent};
 mode=next;modeEpoch++;const state=sessions[mode];cover=state.cover;crop=state.crop;
 for(const id of fields)el(id).value=state[id];lastFit=el('fit').value;labels();
 el('filename').textContent=state.filename;el('ratio').textContent=state.ratio;el('file').value='';
 for(const name of modes){el(name+'-options').hidden=name!==mode;el(name+'-tab').setAttribute('aria-pressed',String(name===mode))}
 el('fit-options').hidden=mode==='book';
 el('heading').textContent={book:'画册封面渲染',pillow:'单面定制抱枕',instant:'拍立得相纸渲染'}[mode];
 el('subtitle').textContent={book:'自定义封面 · 硬壳质感',pillow:'单图单面 · pillow_squ 底模',instant:'真实相纸比例 · 白边 · 柔影'}[mode];
 el('upload-label').textContent=mode==='book'?'替换封面图片':'替换定制图片';
 el('thickness-label').textContent=mode==='pillow'?'抱枕饱满度':'书本厚度';
 el('thickness').hidden=mode==='instant';el('thickness-label').parentElement.hidden=mode==='instant';
 el('gloss-label').textContent=mode==='pillow'?'布面光泽':'表面反光';
 el('image').style.visibility='hidden';formatInfo();schedule();
}
for(const name of modes)el(name+'-tab').onclick=()=>switchMode(name);
el('reset').onclick=()=>{const a=mode==='book'?[22,14,-13]:mode==='pillow'?[0,0,0]:[0,0,-8];['rotate_x','rotate_y','rotate_z'].forEach((id,i)=>el(id).value=a[i]);labels();schedule()};
function formatChanged(){crop=null;if(el('fit').value==='manual')el('fit').value='crop';lastFit=el('fit').value;formatInfo();schedule()}
el('pillow_ratio').onchange=formatChanged;el('film').onchange=formatChanged;
let fileVersion=0;
el('file').onchange=async()=>{
 const f=el('file').files[0];if(!f)return;const version=++fileVersion;uploading=true;revision++;el('save').disabled=true;for(const name of modes)el(name+'-tab').disabled=true;
 el('status').textContent='正在读取图片…';
 try{const r=await fetch('/cover',{method:'POST',body:f});if(!r.ok)throw Error(await r.text());const uploaded=await r.json();if(version!==fileVersion)return;
 cover=uploaded.token;crop=null;if(el('fit').value==='manual')el('fit').value='crop';lastFit=el('fit').value;el('filename').textContent=f.name;
 const gcd=(a,b)=>b?gcd(b,a%b):a,d=gcd(uploaded.width,uploaded.height);el('ratio').textContent=`${uploaded.width} × ${uploaded.height} 像素 · 画册 ${uploaded.width/d}:${uploaded.height/d}`;formatInfo();schedule();
 }catch(e){el('status').textContent='读取失败：'+e.message}finally{if(version===fileVersion){uploading=false;for(const name of modes)el(name+'-tab').disabled=false;el('save').disabled=exporting;if(pending)preview()}}
};
async function request(state){const r=await fetch('/render',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state)});if(!r.ok)throw Error(await r.text());return r.blob()}
async function preview(){if(busy||uploading||!pending)return;busy=true;pending=false;const current=revision,epoch=modeEpoch,state=values(800);el('status').textContent='正在更新预览…';try{
 const blob=await request(state);if(state.cover===cover&&state.kind===mode&&epoch===modeEpoch&&!uploading){const url=URL.createObjectURL(blob);if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=url;el('image').src=url;el('image').style.visibility='visible';el('status').textContent='实时预览已更新 · 可直接拖动画面或滑块'}
 }catch(e){if(current===revision)el('status').textContent='预览失败：'+e.message}finally{busy=false;if(pending)preview()}}
el('preview').onclick=schedule;
el('save').onclick=async()=>{if(uploading||exporting)return;exporting=true;el('save').disabled=true;const state=values(+el('width').value);el('save').textContent='正在导出…';try{const url=URL.createObjectURL(await request(state));const a=document.createElement('a');a.href=url;a.download={book:'画册',pillow:'抱枕',instant:'拍立得_'+state.film}[state.kind]+'_透明底.png';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);el('status').textContent='已导出点击时的图片与参数'}catch(e){el('status').textContent='导出失败：'+e.message}finally{exporting=false;el('save').disabled=uploading;el('save').textContent='导出透明 PNG（含阴影）'}};
const surface=el('image');let drag=null;
function updateAngles(x,y,z){const wrap=n=>((n+180)%360+360)%360-180;for(const [id,v] of [['rotate_x',Math.max(-55,Math.min(55,x))],['rotate_y',Math.max(-55,Math.min(55,y))],['rotate_z',wrap(z)]])el(id).value=Math.round(v);labels();schedule()}
surface.addEventListener('pointerdown',e=>{if(e.button!==0||drag)return;e.preventDefault();const size=surface.getBoundingClientRect();drag={id:e.pointerId,startX:e.clientX,startY:e.clientY,x:+el('rotate_x').value,y:+el('rotate_y').value,z:+el('rotate_z').value,roll:e.shiftKey,sensitivity:150/Math.max(250,Math.min(size.width,size.height))};surface.setPointerCapture(e.pointerId);surface.classList.add('dragging')});
surface.addEventListener('pointermove',e=>{if(!drag||drag.id!==e.pointerId)return;e.preventDefault();const dx=(e.clientX-drag.startX)*drag.sensitivity,dy=(e.clientY-drag.startY)*drag.sensitivity;if(drag.roll)updateAngles(drag.x,drag.y,drag.z+dx);else updateAngles(drag.x-dy,drag.y+dx,drag.z)});
function endDrag(e){if(!drag||drag.id!==e.pointerId)return;drag=null;surface.classList.remove('dragging');if(surface.hasPointerCapture(e.pointerId))surface.releasePointerCapture(e.pointerId)}
for(const name of ['pointerup','pointercancel','lostpointercapture'])surface.addEventListener(name,endDrag);
surface.addEventListener('dragstart',e=>e.preventDefault());

// Crop selection is normalized to the oriented original image, never the mockup.
const dialog=el('crop-dialog'),canvas=el('crop-canvas'),ctx=canvas.getContext('2d');
let editor=null,cropDrag=null,priorFit='crop',cropRequest=0;
function cropSize(zoom){const sourceAspect=editor.iw/editor.ih;const mw=Math.min(1,editor.aspect/sourceAspect),mh=Math.min(1,sourceAspect/editor.aspect);return {w:mw/zoom,h:mh/zoom}}
function cropClamp(){const r=editor.rect;r.x=Math.max(0,Math.min(1-r.w,r.x));r.y=Math.max(0,Math.min(1-r.h,r.y))}
function drawCrop(){if(!editor)return;const {img,iw,ih,rect:r}=editor;const scale=Math.min(860/iw,560/ih);const w=iw*scale,h=ih*scale,x=(900-w)/2,y=(600-h)/2;editor.display={x,y,w,h};ctx.clearRect(0,0,900,600);ctx.drawImage(img,x,y,w,h);ctx.fillStyle='#0009';ctx.beginPath();ctx.rect(x,y,w,h);ctx.rect(x+r.x*w,y+r.y*h,r.w*w,r.h*h);ctx.fill('evenodd');ctx.strokeStyle='white';ctx.lineWidth=2;ctx.strokeRect(x+r.x*w,y+r.y*h,r.w*w,r.h*h);ctx.strokeStyle='#ffffff88';ctx.lineWidth=1;for(const t of [1/3,2/3]){ctx.beginPath();ctx.moveTo(x+(r.x+r.w*t)*w,y+r.y*h);ctx.lineTo(x+(r.x+r.w*t)*w,y+(r.y+r.h)*h);ctx.moveTo(x+r.x*w,y+(r.y+r.h*t)*h);ctx.lineTo(x+(r.x+r.w)*w,y+(r.y+r.h*t)*h);ctx.stroke()}}
async function openCrop(previous){if(mode==='book'||uploading||dialog.open)return;const requestId=++cropRequest;priorFit=previous||el('fit').value;el('crop-error').textContent='正在加载原图…';el('crop-apply').disabled=true;editor=null;cropDrag=null;ctx.clearRect(0,0,900,600);dialog.showModal();try{
 const response=await fetch('/source?cover='+encodeURIComponent(cover||''));if(!response.ok)throw Error(await response.text());const iw=+response.headers.get('X-Image-Width'),ih=+response.headers.get('X-Image-Height');const url=URL.createObjectURL(await response.blob());const img=new Image();img.src=url;try{await img.decode()}finally{URL.revokeObjectURL(url)}if(!dialog.open||requestId!==cropRequest)return;
 editor={img,iw,ih,aspect:targetAspect(),rect:null};const full=cropSize(1);editor.rect=crop?{...crop}:{x:(1-full.w)/2,y:(1-full.h)/2,...full};el('crop-zoom').value=full.w/editor.rect.w;el('crop-zoom-value').value=(+el('crop-zoom').value).toFixed(2)+'×';el('crop-hint').textContent=`固定画面比例 ${editor.aspect.toFixed(4)}:1；拖动白框选位置，缩放选择范围。`;el('crop-error').textContent='';el('crop-apply').disabled=false;drawCrop();
 }catch(e){if(requestId===cropRequest)el('crop-error').textContent='加载失败：'+e.message}}
el('fit').onchange=()=>{if(el('fit').value==='manual'){el('fit').value=lastFit;openCrop(lastFit)}else{lastFit=el('fit').value;formatInfo();schedule()}};
el('edit-crop').onclick=()=>openCrop();
function cancelCrop(){el('fit').value=priorFit;lastFit=priorFit;cropRequest++;dialog.close();editor=null;cropDrag=null;formatInfo()}
el('crop-cancel').onclick=cancelCrop;dialog.addEventListener('cancel',e=>{e.preventDefault();cancelCrop()});
el('crop-apply').onclick=()=>{if(!editor)return;crop={...editor.rect};el('fit').value='manual';lastFit='manual';dialog.close();editor=null;cropDrag=null;formatInfo();schedule()};
el('crop-zoom').oninput=()=>{if(!editor)return;const old=editor.rect,center={x:old.x+old.w/2,y:old.y+old.h/2},size=cropSize(+el('crop-zoom').value);editor.rect={x:center.x-size.w/2,y:center.y-size.h/2,...size};cropClamp();el('crop-zoom-value').value=(+el('crop-zoom').value).toFixed(2)+'×';drawCrop()};
el('crop-center').onclick=()=>{if(!editor)return;el('crop-zoom').value=1;el('crop-zoom').oninput();const r=editor.rect;r.x=(1-r.w)/2;r.y=(1-r.h)/2;drawCrop()};
function cropPoint(e){const r=canvas.getBoundingClientRect();return {x:(e.clientX-r.left)*900/r.width,y:(e.clientY-r.top)*600/r.height}}
canvas.addEventListener('pointerdown',e=>{if(!editor||e.button!==0)return;const p=cropPoint(e),d=editor.display,r=editor.rect;if(p.x<d.x+r.x*d.w||p.x>d.x+(r.x+r.w)*d.w||p.y<d.y+r.y*d.h||p.y>d.y+(r.y+r.h)*d.h)return;e.preventDefault();cropDrag={id:e.pointerId,p,rect:{...r}};canvas.setPointerCapture(e.pointerId)});
canvas.addEventListener('pointermove',e=>{if(!cropDrag||!editor||cropDrag.id!==e.pointerId)return;const p=cropPoint(e),d=editor.display;editor.rect={...cropDrag.rect,x:cropDrag.rect.x+(p.x-cropDrag.p.x)/d.w,y:cropDrag.rect.y+(p.y-cropDrag.p.y)/d.h};cropClamp();drawCrop()});
for(const name of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(name,e=>{if(cropDrag?.id===e.pointerId){cropDrag=null;if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId)}});
canvas.addEventListener('wheel',e=>{if(!editor)return;e.preventDefault();el('crop-zoom').value=Math.max(1,Math.min(6,+el('crop-zoom').value*(e.deltaY>0?1.06:1/1.06)));el('crop-zoom').oninput()},{passive:false});
fetch('/films').then(r=>r.json()).then(data=>{films=data;formatInfo();schedule()}).catch(e=>el('status').textContent='规格加载失败：'+e.message);
