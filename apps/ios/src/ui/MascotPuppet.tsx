import React, {useEffect, useRef, useState} from 'react';
import {AccessibilityInfo, AppState, Image, Platform, View} from 'react-native';
import type {MascotPose} from './CanopyMascot';
import {characterMotion, gardenMotion} from './mascotMotion';
import atlas from '../../assets/canopy-ui/mascot-puppet-parts.json';
import {jointEnd, spriteFrame} from './puppetGeometry';

const source=require('../../assets/canopy-ui/mascot-puppet-parts.png');
const deg=(r:number)=>`${r*180/Math.PI}deg` as `${number}deg`;
type Point=[number,number];
const joints:Record<number,[Point,Point]>={
  4:[[232,466],[156,679]],5:[[505,459],[577,620]],
  6:[[937,466],[862,679]],7:[[1220,459],[1294,620]],
  8:[[210,755],[247,1003]],9:[[514,760],[563,969]],
  10:[[915,756],[951,1004]],11:[[1225,761],[1273,970]],
};
function Sprite({index,scale,anchor,pivot,rotation=0}:{index:number;scale:number;anchor:Point;pivot:Point;rotation?:number}){
 const rect=atlas.rects[index];
 const frame=spriteFrame(rect,anchor,scale,pivot,rotation);
 return <View collapsable={false} style={{position:'absolute',...frame,overflow:'hidden',transform:[{rotate:deg(rotation)}]}}><Image source={source} fadeDuration={0} resizeMode="stretch" style={{position:'absolute',width:atlas.width*scale,height:atlas.height*scale,left:-rect[0]*scale,top:-rect[1]*scale}}/></View>;
}
function Art({index,height,x,y,angle=0}:{index:number;height:number;x:number;y:number;angle?:number}){
 const rect=atlas.rects[index],scale=height/rect[3];
 return <Sprite index={index} scale={scale} anchor={[rect[0]+rect[2]/2,rect[1]]} pivot={[x,y]} rotation={angle}/>;
}
function Bone({index,length,angle,x,y}:{index:number;length:number;angle:number;x:number;y:number}){
 const [a,b]=joints[index],dx=b[0]-a[0],dy=b[1]-a[1],scale=length/Math.hypot(dx,dy),base=Math.atan2(-dx,dy);
 return <Sprite index={index} scale={scale} anchor={a} pivot={[x,y]} rotation={angle-base}/>;
}
function Chain({x,y,upper,lower,a,b,l1,l2}:{x:number;y:number;upper:number;lower:number;a:number;b:number;l1:number;l2:number}){
 const [ex,ey]=jointEnd(x,y,a,l1);
 return <><Bone index={upper} length={l1} angle={a} x={x} y={y}/><Bone index={lower} length={l2} angle={a+b} x={ex} y={ey}/></>;
}
export function solvePuppetLimb(dx:number,dy:number,l1:number,l2:number):[number,number]{
 const d=Math.min(l1+l2-.01,Math.max(Math.abs(l1-l2)+.01,Math.hypot(dx,dy)));
 const b=Math.acos(Math.max(-1,Math.min(1,(d*d-l1*l1-l2*l2)/(2*l1*l2))));
 return [Math.atan2(dy,dx)-Math.PI/2-Math.atan2(l2*Math.sin(b),l1+l2*Math.cos(b)),b];
}
function Stroke({a,b,color='#59836b',width=3}:{a:Point;b:Point;color?:string;width?:number}){
 const dx=b[0]-a[0],dy=b[1]-a[1],length=Math.hypot(dx,dy);
 return <View style={{position:'absolute',left:(a[0]+b[0]-length)/2,top:(a[1]+b[1]-width)/2,width:length,height:width,backgroundColor:color,borderRadius:width,transform:[{rotate:deg(Math.atan2(dy,dx))}]}}/>;
}
function Bike({t}:{t:number}){
 return <>{[100,221].map(x=><View key={x} style={{position:'absolute',left:x-31,top:255,width:62,height:62,borderWidth:3,borderRadius:31,borderColor:'#345448',transform:[{rotate:deg(t*4.2)}]}}>{[0,45,90,135].map(a=><View key={a} style={{position:'absolute',left:0,top:27,width:56,height:1,backgroundColor:'#94aa9b',transform:[{rotate:`${a}deg`}]}}/>)}</View>)}
 {([[100,286,134,235],[134,235,166,272],[166,272,100,286],[134,235,204,238],[204,238,166,272],[204,238,221,286],[204,238,209,211],[192,210,220,210],[134,235,134,228]]).map((p,i)=><Stroke key={i} a={[p[0],p[1]]} b={[p[2],p[3]]}/>)}
 <View style={{position:'absolute',left:121,top:225,width:26,height:6,borderRadius:4,backgroundColor:'#365943'}}/>
 {[0,1].map(i=>{const a=t*Math.PI*2/1.5+i*Math.PI,x=166+Math.cos(a)*16,y=272+Math.sin(a)*16;return <React.Fragment key={i}><Stroke a={[166,272]} b={[x,y]} color="#365943" width={2}/><Stroke a={[x-6,y]} b={[x+6,y]} color="#365943" width={3}/></React.Fragment>;})}
 </>;
}
export default function MascotPuppet({pose,height,animated}:{pose:MascotPose;height:number;animated:boolean}){
 const [width,setWidth]=useState(height),[time,setTime]=useState(0),[reduce,setReduce]=useState(true);
 const elapsed=useRef(0);
 useEffect(()=>{let alive=true;void AccessibilityInfo.isReduceMotionEnabled().then(v=>{if(alive)setReduce(v);});const sub=AccessibilityInfo.addEventListener('reduceMotionChanged',setReduce);return()=>{alive=false;sub.remove();};},[]);
 useEffect(()=>{elapsed.current=0;setTime(0);},[pose]);
 useEffect(()=>{if(!animated||reduce){setTime(0);return;}let frame=0,last:number|undefined,paint=0;function tick(now:number){const active=AppState.currentState==='active'&&!(Platform.OS==='web'&&document.hidden);if(active){if(last!==undefined)elapsed.current+=Math.max(0,Math.min((now-last)/1000,.08));last=now;if(now-paint>=1000/30){setTime(elapsed.current);paint=now;}}else last=undefined;frame=requestAnimationFrame(tick);}frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame);},[animated,reduce,pose]);
 return <View onLayout={e=>setWidth(e.nativeEvent.layout.width)} style={{height,width:'100%',alignItems:'center',justifyContent:'center',overflow:'hidden'}}><PuppetFrame pose={pose} time={time} width={width} height={height}/></View>;
}
export function PuppetFrame({pose,time,width,height}:{pose:MascotPose;time:number;width:number;height:number}){
 const action=pose==='cycle'||pose==='garden'||pose==='walk'||pose==='run'||pose==='complete'?pose:'start';
 const m=characterMotion(action,time),g=gardenMotion(time),cycling=action==='cycle',garden=action==='garden';
 const stageWidth=cycling?260:290,scale=Math.min(width/stageWidth,height/330);
 const sway=m.walking?Math.sin(time*6.5)*2:Math.sin(time*1.5)*1.5;
 const hipY=garden?222:230,hipX=cycling?145:146;
 const leg=(side:number):[number,number]=>{
  if(cycling){const a=time*Math.PI*2/1.5+side*Math.PI;return solvePuppetLimb(166+Math.cos(a)*16-(hipX+side*22),262+Math.sin(a)*16-hipY,29,35);}
  if(garden)return [-1.1+side*.15,1.55];
  if(m.walking){const phase=time*6.5+side*Math.PI;return [Math.sin(phase)*.55,Math.max(0,-Math.sin(phase))*.7];}
  return [side===0?.08:-.08,.03];
 };
 const arm=(side:number):[number,number]=>{
  if(cycling)return solvePuppetLimb((side?211:194)-(side?185:131),211-178,27,34);
  if(garden)return side?[-.85,.18]:[.22+g.hello*1.95,.15+g.wave*.33];
  if(m.walking)return [Math.sin(time*6.5+side*Math.PI)*.38,.16];
  return side?[-m.armRaise,-m.elbow-m.wrist]:[.23,.12];
 };
 const la=leg(0),lb=leg(1),aa=arm(0),ab=arm(1);
 const expression=garden&&g.smile>.7?1:m.wink>.7?2:m.blink>.7?1:0;
 const endpoint=(x:number,y:number,a:number,b:number):Point=>[x-Math.sin(a)*27-Math.sin(a+b)*34,y+Math.cos(a)*27+Math.cos(a+b)*34];
 const hand=endpoint(185,178,ab[0],ab[1]);
 return <View style={{width:stageWidth,height:330,flexShrink:0,transform:[{scale}]}}>
  {cycling&&<Bike t={time}/>}
  <View style={{position:'absolute',left:0,top:cycling?0:sway,width:stageWidth,height:330}}>
   <Chain x={hipX} y={hipY} upper={8} lower={9} a={la[0]} b={la[1]} l1={29} l2={35}/>
   <Chain x={131} y={178} upper={4} lower={5} a={aa[0]} b={aa[1]} l1={27} l2={34}/>
   <Art index={3} height={88} x={158} y={149}/>
   <Chain x={hipX+22} y={hipY} upper={10} lower={11} a={lb[0]} b={lb[1]} l1={29} l2={35}/>
   <Chain x={185} y={178} upper={6} lower={7} a={ab[0]} b={ab[1]} l1={27} l2={34}/>
   <Art index={expression} height={163} x={153} y={8} angle={garden?-.04*g.hello:.022*Math.sin(time*1.4)}/>
   {garden&&<View style={{position:'absolute',left:hand[0]-3,top:hand[1]-5,width:26,height:21,transform:[{rotate:deg(g.pour*.35)}]}}><View style={{width:21,height:19,borderRadius:4,backgroundColor:'#d6b968'}}/><View style={{position:'absolute',left:-6,top:0,width:11,height:13,borderWidth:2,borderColor:'#b2944e',borderRadius:7}}/><Stroke a={[18,6]} b={[37,-3]} color="#b2944e" width={3}/></View>}
   {garden&&g.pour>.7&&Array.from({length:7},(_,i)=>{const u=(time*1.6+i/7)%1;return <View key={i} style={{position:'absolute',left:hand[0]+33+u*7,top:hand[1]+u*u*47,width:2,height:4,borderRadius:2,backgroundColor:'#8dc6c8',opacity:1-u}}/>;})}
   {action==='complete'&&<View style={{position:'absolute',left:hand[0]-4,top:hand[1]-11,width:12,height:25,borderRadius:3,backgroundColor:'#e2bb62',transform:[{rotate:'-25deg'}]}}/>}
  </View>
  {action==='complete'&&m.burstAge>=0&&m.burstAge<2.8&&Array.from({length:22},(_,i)=>{const a=m.burstAge,theta=i*2.4;return <View key={i} style={{position:'absolute',left:224+Math.cos(theta)*a*33,top:140-a*90+a*a*47,width:4,height:7,backgroundColor:['#87ad68','#e8bb66','#8bc7c1'][i%3],opacity:Math.min(1,(2.8-a)*2),transform:[{rotate:deg(theta+a*3)}]}}/>;})}
 </View>;
}
