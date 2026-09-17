import React,{useEffect,useState} from 'react';
import {AccessibilityInfo,AppState,Image,View} from 'react-native';

const walk=[require('../../assets/canopy-ui/landing-mascot-walk-1.png'),require('../../assets/canopy-ui/landing-mascot-walk-2.png'),require('../../assets/canopy-ui/landing-mascot-point.png')];
const start=[require('../../assets/canopy-ui/journey-start-frame-1.png'),require('../../assets/canopy-ui/journey-start-frame-2.png'),require('../../assets/canopy-ui/journey-start-frame-3.png'),require('../../assets/canopy-ui/journey-start-frame-4.png'),require('../../assets/canopy-ui/journey-start-frame-5.png'),require('../../assets/canopy-ui/journey-start-frame-6.png'),require('../../assets/canopy-ui/journey-start-frame-7.png'),require('../../assets/canopy-ui/journey-start-frame-8.png')];
const complete=[require('../../assets/canopy-ui/journey-complete-frame-1.png'),require('../../assets/canopy-ui/journey-complete-frame-2.png'),require('../../assets/canopy-ui/journey-complete-frame-3.png'),require('../../assets/canopy-ui/journey-complete-frame-4.png'),require('../../assets/canopy-ui/journey-complete-frame-5.png'),require('../../assets/canopy-ui/journey-complete-frame-6.png'),require('../../assets/canopy-ui/journey-complete-frame-7.png'),require('../../assets/canopy-ui/journey-complete-frame-8.png')];

// 기존 PoC의 걷기, 출발, 도착 프레임 재사용. 화면 비활성화와 동작 줄이기 설정 시 정지
export function CanopyMascot({pose='walk',height=200}:{pose?:'walk'|'start'|'complete';height?:number}){
  const [frame,setFrame]=useState(0),[reduced,setReduced]=useState(true),[active,setActive]=useState(AppState.currentState==='active');
  const frames=pose==='walk'?walk:pose==='start'?start:complete;
  useEffect(()=>{let alive=true;void AccessibilityInfo.isReduceMotionEnabled().then(v=>{if(alive)setReduced(v);});
    const motion=AccessibilityInfo.addEventListener('reduceMotionChanged',setReduced),state=AppState.addEventListener('change',v=>setActive(v==='active'));
    return()=>{alive=false;motion.remove();state.remove();};},[]);
  useEffect(()=>{setFrame(0);if(reduced||!active)return;
    const durations=pose==='walk'?[1218,1050,1932]:pose==='complete'?[200,200,200,200,200,200,200,200]:[576,576,624,768,720,576,480,480];let timer:ReturnType<typeof setTimeout>;let index=0;
    function advance(){timer=setTimeout(()=>{index=(index+1)%frames.length;setFrame(index);advance();},durations[index]);}advance();return()=>clearTimeout(timer);
  },[pose,reduced,active]);
  return <View pointerEvents="none" accessibilityLabel="캐노피 캐릭터" accessible style={{height,width:'100%',overflow:'hidden'}}>{frames.map((source,i)=><Image key={i} source={source} resizeMode="contain" style={{position:'absolute',width:'100%',height:'100%',opacity:i===frame?1:0,transform:[{scale:pose==='walk'?1:1.65}]}}/>)}</View>;
}
