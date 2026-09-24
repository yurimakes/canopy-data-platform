import Text from './AppText';
import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,View} from 'react-native';
import * as T from 'three';
import {mascotScene} from './mascotScene';
import type {MascotPose} from './CanopyMascot';
export default function ActorCanvas({pose,animated}:{pose:MascotPose;animated:boolean}){
 const canvas=useRef<HTMLCanvasElement>(null),[error,setError]=useState(false);
 useEffect(()=>{if(!canvas.current)return;let renderer:T.WebGLRenderer;
  try{renderer=new T.WebGLRenderer({canvas:canvas.current,alpha:true,antialias:true,powerPreference:'low-power'});}catch{setError(true);return;}
  renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;
  const actor=mascotScene(pose);let frame=0,disposed=false,reduced=false,elapsed=0,last:number|undefined,renderedAt=0;
  void AccessibilityInfo.isReduceMotionEnabled().then(v=>{reduced=v;});const sub=AccessibilityInfo.addEventListener('reduceMotionChanged',v=>{reduced=v;});
  const resize=new ResizeObserver(()=>{const el=canvas.current;if(!el)return;const {width,height}=el.getBoundingClientRect();renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.setSize(width,height,false);actor.camera.aspect=width/Math.max(height,1);actor.camera.updateProjectionMatrix();});resize.observe(canvas.current);
  function draw(now:number){if(disposed)return;if(!document.hidden&&now-renderedAt>=33){renderedAt=now;if(last!==undefined&&animated&&!reduced)elapsed+=Math.min((now-last)/1000,.1);actor.update(animated&&!reduced?elapsed:0);renderer.render(actor.scene,actor.camera);last=now;}else if(document.hidden){last=undefined;}frame=requestAnimationFrame(draw);}frame=requestAnimationFrame(draw);
  return()=>{disposed=true;cancelAnimationFrame(frame);resize.disconnect();sub.remove();actor.dispose();renderer.dispose();};
 },[pose,animated]);
 return error?<View style={{flex:1,justifyContent:'center',alignItems:'center'}}><Text>3D 표시를 지원하는 브라우저에서 확인해주세요.</Text></View>:<canvas ref={canvas} style={{width:'100%',height:'100%',display:'block'}} aria-hidden="true"/>;
}
