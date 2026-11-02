"""User-initiated browser camera, with a capture-input fallback for LAN HTTP."""
import re
from starlette.responses import HTMLResponse,Response


async def cameraPage(request):
    ticket=request.path_params['ticket']
    from photo_upload import photoUploadExists
    if not re.fullmatch('[A-Za-z0-9_-]{32,64}',ticket) or not photoUploadExists(ticket):return Response(status_code=404)
    html='''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Снимок цвета</title><style>body{font:18px system-ui;max-width:600px;margin:24px auto;padding:16px}button,input{font:inherit;margin:12px 0;padding:12px;max-width:100%}video{width:100%;max-height:400px}#status{white-space:pre-wrap}</style>
<h1>Снимок цвета</h1><p>Снимите объект при ровном освещении. Фото попадёт только в открытое приложение.</p>
<button id="start">Включить камеру</button><video id="video" autoplay playsinline hidden></video><button id="capture" hidden>Сделать снимок</button>
<p>Если камера недоступна в браузере, выберите снимок:</p><input id="file" type="file" accept="image/jpeg,image/png,image/webp" capture="environment">
<p id="status">После загрузки вернитесь в приложение и нажмите «Использовать снимок браузера».</p><canvas id="canvas" hidden></canvas>
<script>
const status=document.querySelector('#status'),video=document.querySelector('#video'),canvas=document.querySelector('#canvas');let stream;
function stop(){if(stream)stream.getTracks().forEach(t=>t.stop());}
async function upload(image,width,height){
 const scale=Math.min(1,1600/width,1600/height);canvas.width=Math.round(width*scale);canvas.height=Math.round(height*scale);
 canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
 const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.92));
 if(!blob||blob.size>5*1024*1024)throw Error('Снимок слишком большой');
 const response=await fetch('/photo-uploads/TICKET',{method:'PUT',body:blob});
 if(!response.ok)throw Error('Загрузка не удалась. Вернитесь в приложение и начните заново.');
 stop();status.textContent='Снимок загружен. Вернитесь в приложение и нажмите «Использовать снимок браузера».';
}
document.querySelector('#start').onclick=async()=>{try{stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'},audio:false});video.srcObject=stream;video.hidden=false;document.querySelector('#capture').hidden=false;}catch(e){status.textContent='Камера недоступна или разрешение не выдано. На HTTP в домашней сети используйте выбор снимка ниже.';}};
document.querySelector('#capture').onclick=async()=>{try{await upload(video,video.videoWidth,video.videoHeight);}catch(e){status.textContent=e.message;}};
document.querySelector('#file').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>10*1024*1024)throw Error('Фото больше 10 МБ');const image=await createImageBitmap(file);try{await upload(image,image.width,image.height);}finally{image.close();}}catch(e){status.textContent=e.message;}};
window.addEventListener('pagehide',stop);
</script></html>'''.replace('TICKET',ticket)
    return HTMLResponse(html,headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'"})
