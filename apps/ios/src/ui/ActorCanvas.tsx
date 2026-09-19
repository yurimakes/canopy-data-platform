import Text from './AppText';
import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,AppState,View,Pressable} from 'react-native';
import {GLView,type ExpoWebGLRenderingContext} from 'expo-gl';
import * as T from 'three';
import {mascotScene} from './mascotScene';
import {createNativeRenderer} from './nativeGLRenderer';
import type {MascotPose} from './CanopyMascot';
export default function ActorCanvas({pose,animated}:{pose:MascotPose;animated:boolean}){
 const [error,setError]=useState(''),[attempt,setAttempt]=useState(0);
 const stop=useRef<()=>void>(()=>{}),reduced=useRef(false);
 useEffect(()=>{void AccessibilityInfo.isReduceMotionEnabled().then(v=>{reduced.current=v;});const sub=AccessibilityInfo.addEventListener('reduceMotionChanged',v=>{reduced.current=v;});return()=>{stop.current();sub.remove();};},[]);
 function create(gl:ExpoWebGLRenderingContext){
  try{
  stop.current();const width=gl.drawingBufferWidth,height=gl.drawingBufferHeight;
  const renderer=createNativeRenderer(gl as unknown as WebGL2RenderingContext);renderer.setSize(width,height,false);
  renderer.outputColorSpace=T.SRGBColorSpace;renderer.toneMapping=T.ACESFilmicToneMapping;renderer.toneMappingExposure=1.05;
  const actor=mascotScene(pose);actor.camera.aspect=width/height;actor.camera.updateProjectionMatrix();let frame=0,dead=false,elapsed=0,last:number|undefined;
  function draw(){if(dead)return;try{const now=Date.now();if(AppState.currentState==='active'){if(last!==undefined&&animated&&!reduced.current)elapsed+=Math.min((now-last)/1000,.1);actor.update(animated&&!reduced.current?elapsed:0);renderer.render(actor.scene,actor.camera);gl.endFrameEXP();last=now;}else{last=undefined;}frame=requestAnimationFrame(draw);}catch(e){fail(e);}}
  stop.current=()=>{dead=true;cancelAnimationFrame(frame);actor.dispose();renderer.dispose();};
  draw();
  }catch(e){fail(e);}
 }
 function fail(e:unknown){const message=e instanceof Error?e.message:String(e);console.warn('[Canopy 3D]',message);try{stop.current();}catch{}stop.current=()=>{};setError(message);}
 if(error)return <View style={{flex:1,justifyContent:'center',alignItems:'center',gap:8,padding:8}}><Text style={{fontSize:12,textAlign:'center'}}>3D 표시 오류: {error}</Text><Pressable accessibilityRole="button" onPress={()=>{setError('');setAttempt(v=>v+1);}}><Text style={{color:'#108454',fontWeight:'700'}}>다시 불러오기</Text></Pressable></View>;
 return <GLView key={`${pose}-${animated}-${attempt}`} style={{flex:1}} onContextCreate={create}/>;
}
