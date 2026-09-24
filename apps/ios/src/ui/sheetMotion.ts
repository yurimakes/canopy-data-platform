import {sheetParts,sheetExpressions,type SheetLayer,type SheetExpression} from './sheetRig';
type P=[number,number];
export const sheetMotions=[
 {id:'idle',label:'기본 · 숨쉬기'},{id:'wave',label:'안녕 · 손 인사'},
 {id:'walk',label:'오른쪽 걷기'},{id:'run',label:'총총 달리기'},
 {id:'jump',label:'기뻐서 점프'},{id:'cheer',label:'주먹 응원'},
 {id:'think',label:'고개 갸웃 · 생각'},{id:'surprise',label:'깜짝 놀라기'},
 {id:'sit',label:'앉아서 쉬기'},{id:'point',label:'가리키기'},
 {id:'thumbsup',label:'엄지 척'},{id:'okay',label:'OK 손짓'},
 {id:'cycle',label:'자전거 페달'},{id:'complete',label:'완료 · 축하'},
] as const;
export const sheetHands=[{id:'auto',label:'동작에 맞게'},{id:'palm',label:'손 펴기'},{id:'fist',label:'주먹'},{id:'pointHand',label:'가리키기'},{id:'thumbHand',label:'엄지 척'},{id:'okayHand',label:'OK'}] as const;
export type SheetOptions={expression?:SheetExpression|'auto';hand?:typeof sheetHands[number]['id'];direction?:'left'|'right'};
const rad=(d:number)=>d*Math.PI/180,deg=(r:number)=>r*180/Math.PI;
const length=(a:P,b:P)=>Math.hypot(b[0]-a[0],b[1]-a[1]);
function turn(p:P,pivot:P,angle:number):P{const a=rad(angle),x=p[0]-pivot[0],y=p[1]-pivot[1];return [pivot[0]+x*Math.cos(a)-y*Math.sin(a),pivot[1]+x*Math.sin(a)+y*Math.cos(a)];}
function ik(from:P,to:P,l1:number,l2:number,bend=1):P{
 const dx=to[0]-from[0],dy=to[1]-from[1],d=Math.max(Math.abs(l1-l2)+.01,Math.min(l1+l2-.01,Math.hypot(dx,dy)));
 const a=Math.atan2(dy,dx)-bend*Math.acos(Math.max(-1,Math.min(1,(l1*l1+d*d-l2*l2)/(2*l1*d))));
 return [from[0]+Math.cos(a)*l1,from[1]+Math.sin(a)*l1];
}
export function sheetPose(input:string,time:number,options:SheetOptions={}){
 const pose=input==='start'?'wave':input==='garden'?'idle':input;
 const walk=pose==='walk',run=pose==='run',cycle=pose==='cycle',side=walk||run||cycle,sit=pose==='sit',celebrate=pose==='complete';
 const jump=pose==='jump'||celebrate,period=run?.76:walk?1.18:cycle?1.5:4.8,p=time/period*Math.PI*2;
 const jumpWave=Math.max(0,Math.sin(time*Math.PI*2/2.4)),lift=jump?-24*jumpWave:run?-4*Math.abs(Math.sin(p)):0;
 const base=(cycle?-10:sit?38:0)+lift+(side?0:Math.sin(time*1.3)*.65),hipY=272+base;
 const lean=run?9:pose==='think'?-5:pose==='cheer'?-3:Math.sin(time*1.3)*.65;
 const layers:SheetLayer[]=[],joints:P[]=[],bones:{name:string;from:P;to:P}[]=[];
 const put=(part:string,at:P,angle=0,scale=1,flip=false,opacity=1)=>{layers.push({part,x:at[0],y:at[1],angle,scale,flip,opacity});};
 const segment=(part:string,sourceEnd:P,from:P,to:P,flip=false,opacity=1)=>{
   const widthScale=(side||sit)&&(part==='thighL'||part==='legShaft')?.65:1;
   const sourceStart=sheetParts[part].pivot,dx=(sourceEnd[0]-sourceStart[0])*(flip?-1:1)*widthScale,dy=sourceEnd[1]-sourceStart[1];
   put(part,from,deg(Math.atan2(to[1]-from[1],to[0]-from[0])-Math.atan2(dy,dx)),length(from,to)/Math.hypot(dx,dy),flip,opacity);
   layers[layers.length-1].widthScale=widthScale;
 };
 const leg=(i:number)=>{
   const s=i?1:-1,hip:P=[side?(i?3:-3):s*23,hipY];let ankle:P,footAngle=0;
   if(cycle){const t=p+i*Math.PI;ankle=[10+12*Math.cos(t),315+12*Math.sin(t)];footAngle=4*Math.sin(t);}
   else if(side){
     const phase=p+i*Math.PI,stride=run?36:24,swing=Math.max(0,-Math.sin(phase));
     // Facing right: grounded foot travels front-to-back; only the back-to-front return lifts.
     ankle=[stride*Math.cos(phase),334-(run?26:14)*swing*swing+lift];
     footAngle=-9*swing*swing;
   }else if(sit){ankle=[s*43,338];footAngle=s*8;}
   else{ankle=[s*(jump?29+7*jumpWave:26),334+lift];footAngle=jump?s*8*jumpWave:0;}
   const l1=cycle?35:sit?32:run?37:34,l2=cycle?35:sit?29:run?36:33;
   const knee=ik(hip,ankle,l1,l2,side?1:i?1:-1),alpha=side&&i===0?.86:1;
   if(!side&&!sit){
     // Preserve the continuous original silhouette for straight frontal legs.
     segment('legL',[54,670],hip,ankle,i===1);
   }else{
     segment('thighL',[61,638],hip,knee,i===1,alpha);
     segment('legShaft',[54,670],knee,ankle,i===1,alpha);
     put(side?'footSide':'footFront',ankle,footAngle,side?.41:.40,side,alpha);
   }
   joints.push(hip,knee,ankle);bones.push({name:`leg${i}-upper`,from:hip,to:knee},{name:`leg${i}-lower`,from:knee,to:ankle});
 };
 leg(0);leg(1);
 const body=(at:P)=>turn([at[0],at[1]+base],[0,hipY],lean);
 const bodyPart=(part:string,at:P,angle=0,scale=1,flip=false)=>put(part,body(at),angle+lean,scale,flip);
 const arm=(i:number)=>{
   const s=i?1:-1,shoulder=body([side?(i?13:-9):s*42,214]);let hand='hand',a=i?-15:15,target:P|undefined;
   if(walk||run)a=Math.sin(p+i*Math.PI)*(run?43:25);
   if(pose==='wave'&&i===0){a=126+Math.sin(time*5)*11;hand='palm';}
   if(jump){a=s*(-122-9*jumpWave);hand='palm';}
   if(pose==='cheer'&&i===1){a=-116-Math.sin(time*5)*7;hand='fist';}
   if(pose==='surprise'){a=s*-49*(.7+.3*Math.sin(time*3));hand='palm';}
   if(pose==='think'&&i===1){target=body([8,202]);hand='pointHand';}
   if(pose==='point'&&i===1){target=body([101,219]);hand='pointHand';}
   if(pose==='thumbsup'&&i===1){target=body([73,207]);hand='thumbHand';}
   if(pose==='okay'&&i===1){target=body([71,205]);hand='okayHand';}
   if(cycle){target=[i?53:43,226];}
   if(sit){target=body([s*46,254]);hand='hand';}
   if(options.hand&&options.hand!=='auto'&&i===1)hand=options.hand;
   let wrist:P,handAngle:number;
   if(target){
     const elbow=ik(shoulder,target,29,31,i===1?-1:1);
     segment('upperArm',[402,480],shoulder,elbow);
     segment('foreArm',[416,509],elbow,target);
     wrist=target;handAngle=deg(Math.atan2(target[1]-elbow[1],target[0]-elbow[0]))-90;
     joints.push(elbow);bones.push({name:`arm${i}-upper`,from:shoulder,to:elbow},{name:`arm${i}-lower`,from:elbow,to:wrist});
   }else{
     const aa=rad(a+lean);wrist=[shoulder[0]-Math.sin(aa)*49.8,shoulder[1]+Math.cos(aa)*49.8];
     segment('arm',[416,509],shoulder,wrist);handAngle=a+lean;
     bones.push({name:`arm${i}`,from:shoulder,to:wrist});
   }
   if(hand==='hand')put(hand,wrist,handAngle+26,.85);
   else put(hand,wrist,hand==='pointHand'&&pose==='point'?72:handAngle+180+(pose==='wave'?Math.sin(time*5)*6:0),hand==='palm'?.33:.40);
   joints.push(shoulder,wrist);
 };
 if(side)arm(0);
 bodyPart(side?'sideTorso':'frontBody',[0,201],0,side?1.05:1.02,side);
 if(!side)arm(0);arm(1);
 let expression:SheetExpression='neutral';
 if(jump||sit)expression='happy';else if(pose==='cheer')expression='joy';else if(pose==='surprise')expression='surprised';else if(pose==='think')expression='thinking';
 else if(pose==='wave'&&time%4.8>2.8&&time%4.8<3.3)expression='joy';
 if(options.expression&&options.expression!=='auto')expression=options.expression;
 const part=sheetExpressions.find(e=>e.id===expression)!.part;
 // The sheet supplies a single profile expression. Never attach a frontal face to a profile body.
 const profile=side;
 bodyPart(profile?'sideHead':part,[profile?4:0,204],Math.sin(time*1.3)*(pose==='think'?4:1),profile?.98:1.22,profile);
 joints.push(body([0,201]));
 if(jump)for(const s of [-1,1])put('sparkle',[s*(83+10*jumpWave),170-25*jumpWave],s*12,.37);
 if(expression==='love')put('heartFx',[93,153+Math.sin(time*2)*5],-12,.38);
 if(pose==='think')put('speech',[100,162],0,.38);
 if(options.direction==='left'){
   layers.forEach(l=>{l.x=-l.x;l.angle=-l.angle;l.flip=!l.flip;});
   bones.forEach(b=>{b.from=[-b.from[0],b.from[1]];b.to=[-b.to[0],b.to[1]];});
   joints.forEach(p=>p[0]=-p[0]);
 }
 return {layers,joints,bones,cycle,celebrate,expression};
}
