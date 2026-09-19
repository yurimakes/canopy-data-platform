import React,{useEffect,useRef,useState} from 'react';
import {AccessibilityInfo,AppState,Image,Platform,View} from 'react-native';
import type {MascotPose} from './CanopyMascot';
const atlases={start:require('../../assets/canopy-ui/mascot-wave-120.png'),walk:require('../../assets/canopy-ui/mascot-walk-120.png'),complete:require('../../assets/canopy-ui/mascot-celebrate-120.png')};
export default function MascotFrames({pose,animated,height}:{pose:MascotPose;animated:boolean;height:number}){
 const elapsed=useRef(0);
 const source=pose==='complete'?atlases.complete:pose==='run'||pose==='walk'?atlases.walk:atlases.start;
 const [width,setWidth]=useState(height),[frame,setFrame]=useState(0),[loaded,setLoaded]=useState(false),[reduce,setReduce]=useState(true),[active,setActive]=useState(AppState.currentState==='active');
 useEffect(()=>{let alive=true;void AccessibilityInfo.isReduceMotionEnabled().then(v=>{if(alive)setReduce(v);});const motion=AccessibilityInfo.addEventListener('reduceMotionChanged',setReduce);const app=AppState.addEventListener('change',s=>setActive(s==='active'));return()=>{alive=false;motion.remove();app.remove();};},[]);
 useEffect(()=>{setFrame(0);elapsed.current=0;setLoaded(false);},[source]);
 useEffect(()=>{if(!animated||reduce){setFrame(0);return;}if(!active||!loaded)return;
   let request=0,last:number|undefined,previous=-1;const duration=pose==='run'||pose==='walk'?2000:4000;
   function tick(now:number){if(Platform.OS==='web'&&document.hidden){last=undefined;request=requestAnimationFrame(tick);return;}if(last!==undefined)elapsed.current+=Math.min(now-last,100);last=now;const next=Math.floor((elapsed.current%duration)/duration*120);if(next!==previous){previous=next;setFrame(next);}request=requestAnimationFrame(tick);}
   request=requestAnimationFrame(tick);return()=>cancelAnimationFrame(request);
 },[pose,source,animated,reduce,active,loaded]);
 const size=Math.min(width,height);
 return <View onLayout={e=>setWidth(e.nativeEvent.layout.width)} style={{height,width:'100%',alignItems:'center',justifyContent:'center'}}><View style={{width:size,height:size,overflow:'hidden'}}><Image source={source} onLoad={()=>setLoaded(true)} resizeMode="stretch" fadeDuration={0} style={{position:'absolute',width:size*10,height:size*12,left:-(frame%10)*size,top:-Math.floor(frame/10)*size}}/></View></View>;
}
