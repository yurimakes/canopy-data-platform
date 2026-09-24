import React,{useEffect,useId,useState} from 'react';
import {AccessibilityInfo,AppState,View} from 'react-native';
import Svg,{Defs,ClipPath,Path,Image,G,Ellipse,Circle,Line} from 'react-native-svg';
import {sheetParts,sheetPose,sheetTransform,type SheetOptions} from './sheetRig';
const source=require('../../assets/canopy-ui/sheet-rig/source.png');
export default function SheetMascot({pose,animated=true,...options}:{pose:string;animated?:boolean}&SheetOptions){
 const id=useId().replace(/[^a-zA-Z0-9]/g,''),[time,setTime]=useState(0);
 useEffect(()=>{let frame=0,last=0,elapsed=0,reduced=false;void AccessibilityInfo.isReduceMotionEnabled().then(v=>{reduced=v;});const listener=AccessibilityInfo.addEventListener('reduceMotionChanged',v=>{reduced=v;});const tick=(now:number)=>{if(animated&&!reduced&&AppState.currentState==='active'){if(last)elapsed+=Math.min((now-last)/1000,.07);setTime(elapsed);}last=now;frame=requestAnimationFrame(tick);};frame=requestAnimationFrame(tick);return()=>{cancelAnimationFrame(frame);listener.remove();};},[animated]);
 const frame=sheetPose(pose,time,options);
 return <View style={{flex:1}}><Svg width="100%" height="100%" viewBox="-150 -15 300 395">
  <Defs>{Object.entries(sheetParts).map(([key,p])=><ClipPath id={`${id}-${key}`} key={key}>{p.path.split(/(?=M)/).filter(Boolean).map((d,i)=><Path d={d} key={i}/>)}</ClipPath>)}</Defs>
  <Ellipse cx={0} cy={354} rx={62} ry={7} fill="#245e42" opacity={.10}/>
  {frame.cycle&&<G transform={options.direction==='left'?'scale(-1 1)':undefined} stroke="#316c50" strokeWidth={3} fill="none"><Circle cx={-64} cy={318} r={38}/><Circle cx={68} cy={318} r={38}/><Path d="M-64 318 L-32 257 L14 318 Z M-32 257 L48 257 L14 318 M48 257 L68 318 M48 257 L46 226 L63 226"/><Line x1={-43} y1={251} x2={-20} y2={251}/></G>}
  {frame.layers.map((layer,i)=><G key={i} transform={sheetTransform(layer)} opacity={layer.opacity}><G clipPath={`url(#${id}-${layer.part})`}><Image href={source} width={1536} height={1024}/></G></G>)}
  {frame.celebrate&&Array.from({length:14},(_,i)=>{const p=(time*.4+i/14)%1;return <Circle key={i} cx={Math.sin(i*12.5)*120*p} cy={210-220*p+130*p*p} r={2} fill={i%2?'#d9ad48':'#74b25b'} opacity={1-p}/>;})}
 </Svg></View>;
}
