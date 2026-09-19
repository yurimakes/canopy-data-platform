import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,AppState,View,Text} from 'react-native';
import {GLView,type ExpoWebGLRenderingContext} from 'expo-gl';
import * as T from 'three';
import {mascotScene} from './mascotScene';
import type {MascotPose} from './CanopyMascot';
export default function ActorCanvas({pose,animated}:{pose:MascotPose;animated:boolean}){
 const [error,setError]=useState(false);
 const stop=useRef<()=>void>(()=>{}),reduced=useRef(false);
 useEffect(()=>{void AccessibilityInfo.isReduceMotionEnabled().then(v=>{reduced.current=v;});const sub=AccessibilityInfo.addEventListener('reduceMotionChanged',v=>{reduced.current=v;});return()=>{stop.current();sub.remove();};},[]);
 function create(gl:ExpoWebGLRenderingContext){
  try{
  stop.current();const width=gl.drawingBufferWidth,height=gl.drawingBufferHeight;
  const canvas={width,height,style:{},addEventListener(){},removeEventListener(){},getContext(){return gl;}};
  const renderer=new T.WebGLRenderer({canvas:canvas as unknown as HTMLCanvasElement,context:gl as unknown as WebGL2RenderingContext,alpha:true,antialias:true});renderer.setSize(width,height,false);
  renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;
  const actor=mascotScene(pose);actor.camera.aspect=width/height;actor.camera.updateProjectionMatrix();let frame=0,dead=false;const start=Date.now();
  function draw(){if(dead)return;if(AppState.currentState==='active'){actor.update(animated&&!reduced.current?(Date.now()-start)/1000:0);renderer.render(actor.scene,actor.camera);gl.endFrameEXP();}frame=requestAnimationFrame(draw);}draw();
  stop.current=()=>{dead=true;cancelAnimationFrame(frame);actor.dispose();renderer.dispose();};
  }catch{setError(true);}
 }
 if(error)return <View style={{flex:1,justifyContent:'center',alignItems:'center'}}><Text>3D 화면을 다시 열어주세요.</Text></View>;
 return <GLView key={`${pose}-${animated}`} style={{flex:1}} onContextCreate={create}/>;
}
