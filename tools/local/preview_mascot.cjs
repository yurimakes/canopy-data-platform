const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const ts = require(path.join(root, 'apps/ios/node_modules/typescript'));
const out = path.join(root, '.local-data/rig-preview');
fs.mkdirSync(out, { recursive: true });
for (const file of ['mascotMotion', 'canopyTextureData', 'canopyModel', 'robotRig']) {
  const source = fs.readFileSync(path.join(root, 'apps/ios/src/ui', file + '.ts'), 'utf8');
  const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
  fs.writeFileSync(path.join(out, file + '.js'), js.replace(/'\.\/(mascotMotion|canopyModel|canopyTextureData)'/g, "'./$1.js'"));
}
fs.copyFileSync(path.join(root,'apps/ios/node_modules/fflate/esm/browser.js'),path.join(out,'fflate.js'));
for (const file of ['three.module.js', 'three.core.js']) fs.copyFileSync(path.join(root, 'apps/ios/node_modules/three/build', file), path.join(out, file));
fs.writeFileSync(path.join(out, 'index.html'), `<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Canopy · 모션 확인</title>
<style>body{margin:0;background:#eef5ef;color:#173d30;font-family:system-ui}header{padding:24px 32px}h1{margin:0 0 8px;font-size:24px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;padding:0 24px}.card{background:#fff;border-radius:24px;overflow:hidden;text-align:center}canvas{display:block;width:100%;height:440px}.card p{color:#688074;font-size:14px}footer{padding:24px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}button{padding:12px 18px;border:0;border-radius:12px;background:#174c37;color:white;cursor:pointer}output{font-variant-numeric:tabular-nums}input{width:260px}@media(max-width:650px){main{grid-template-columns:1fr}canvas{height:340px}}</style>
<script type="importmap">{"imports":{"three":"./three.module.js","fflate":"./fflate.js"}}</script>
<header><h1>Canopy · 관절 애니메이션</h1><div>서서 인사 · 오른쪽 걷기 · 자전거 · 폭죽 1회 후 대기</div></header><main>
<section class="card"><h2>서서 인사</h2><canvas id="start"></canvas><p>손 흔들기 · 눈웃음</p></section><section class="card"><h2>오른쪽 걷기</h2><canvas id="run"></canvas><p>발 교대 · 팔과 몸 회전</p></section>
<section class="card"><h2>자전거</h2><canvas id="cycle"></canvas><p>페달과 양발 연결 · 바퀴 회전</p></section>
<section class="card"><h2>폭죽과 축하</h2><canvas id="complete"></canvas><p>준비 → 발사와 반동 → 편안한 대기</p></section></main>
<footer><button id="play">일시정지</button><button id="restart">처음부터 재생</button><label>시간 <input aria-label="재생 시간" id="time" type="range" min="0" max="12" step=".01"></label><output id="clock"></output>
${[0,1.2,2.4,4.8,6,8,10,12].map(t => '<button class="seek" data-time="' + t + '">' + t + '초</button>').join('')}</footer>
<script type="module">import * as T from 'three';import {robotRig} from './robotRig.js';
const actors=['start','run','cycle','complete'].map(action=>{const canvas=document.getElementById(action);const renderer=new T.WebGLRenderer({canvas,antialias:true,alpha:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;const rig=robotRig(action);const resize=()=>{renderer.setSize(canvas.clientWidth,canvas.clientHeight,false);rig.camera.aspect=canvas.clientWidth/canvas.clientHeight;rig.camera.updateProjectionMatrix()};new ResizeObserver(resize).observe(canvas);resize();return {renderer,rig};});
let t=0,last=performance.now(),playing=true;const play=document.getElementById('play'),slider=document.getElementById('time');function label(){play.textContent=playing?'일시정지':'재생'}play.onclick=()=>{playing=!playing;label()};document.getElementById('restart').onclick=()=>{t=0;playing=true;label()};slider.oninput=()=>{t=Number(slider.value);playing=false;label()};document.querySelectorAll('.seek').forEach(b=>b.onclick=()=>{t=Number(b.dataset.time);playing=false;label()});function draw(now){if(playing&&!document.hidden)t+=Math.min((now-last)/1000,.1);last=now;actors.forEach(({renderer,rig})=>{rig.update(t);renderer.render(rig.scene,rig.camera)});slider.value=String(t%12);document.getElementById('clock').value=t.toFixed(2)+' s';requestAnimationFrame(draw)}requestAnimationFrame(draw);
</script></html>`);
console.log(out);
