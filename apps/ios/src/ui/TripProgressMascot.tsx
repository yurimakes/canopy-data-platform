import React,{useEffect,useState} from 'react';
import {AppState,Image} from 'react-native';
import {useReducedMotion} from './DesignPrimitives';

export function TripProgressMascot({active}:{active:boolean}){
 const reduced=useReducedMotion(),[foreground,setForeground]=useState(AppState.currentState==='active');
 useEffect(()=>{const sub=AppState.addEventListener('change',s=>setForeground(s==='active'));return()=>sub.remove();},[]);
 const animate=active&&foreground&&!reduced;
 return <Image key={animate?'walking':'still'} source={animate?require('../../assets/mascot/trip-walk.gif'):require('../../assets/mascot/trip-walk-still.png')} resizeMode="contain" style={{width:58,height:58}} accessibilityLabel={active?'여정 진행 중 캐노피':'출발을 기다리는 캐노피'}/>;
}
