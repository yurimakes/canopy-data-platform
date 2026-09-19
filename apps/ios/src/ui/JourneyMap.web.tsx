import {bearing} from '../journeyGeometry';
import React from 'react';
import {View,Text} from 'react-native';
import type {MapProps} from './JourneyMap';
import type {Place} from '../service';
import {C,S,Icon,Note} from './theme';

export default function JourneyMap({points,route,height=310,places=[],selectedPlace=0,onSelectPlace}:MapProps){
  const all=[...points,...places,...(route?[route.from,route.to]:[])];
  if(!all.length)return <View style={{height,backgroundColor:C.mint,justifyContent:'center',alignItems:'center',gap:16}}><Icon name="navigate-outline" size={40}/><Note>위치를 받으면 이동 궤적이 표시됩니다.</Note></View>;
  const xs=all.map(p=>p.longitude),ys=all.map(p=>p.latitude);
  const midX=(Math.min(...xs)+Math.max(...xs))/2,midY=(Math.min(...ys)+Math.max(...ys))/2;
  const cosine=Math.cos(midY*Math.PI/180),range=Math.max((Math.max(...xs)-Math.min(...xs))*cosine/480,(Math.max(...ys)-Math.min(...ys))/240,.00001);
  const xy=(p:Place)=>[300+(p.longitude-midX)*cosine/range,175-(p.latitude-midY)/range];
  const line=(ps:Place[])=>ps.map(p=>xy(p).join(',')).join(' ');
  const marker=(p:Place,label:string,color:string,key:string,click?:()=>void)=>{
    const [x,y]=xy(p);return <g key={key} role={click?'button':undefined} tabIndex={click?0:undefined} aria-label={p.name} onClick={click} onKeyDown={e=>{if(click&&(e.key==='Enter'||e.key===' ')){e.preventDefault();click();}}} style={{cursor:click?'pointer':'default'}}>
      <circle cx={x} cy={y} r={22} fill={color} opacity={.13}/><circle cx={x} cy={y} r={10} fill={color} stroke="white" strokeWidth={3}/>
      <text x={x} y={y-30} textAnchor="middle" fontSize={14} fontWeight={700} fill={C.deep}>{label}</text>
    </g>;
  };
  return <View style={{height,backgroundColor:'#edf5ef',overflow:'hidden'}}>
    <svg viewBox="0 0 600 350" width="100%" height="100%" aria-label="오프라인 위치와 GPS 궤적 미리보기">
      {Array.from({length:12},(_,i)=><line key={'x'+i} x1={i*60} y1={0} x2={i*60} y2={350} stroke="#dce9e0"/>)}
      {Array.from({length:7},(_,i)=><line key={'y'+i} x1={0} y1={i*60} x2={600} y2={i*60} stroke="#dce9e0"/>)}
      {route&&<polyline points={line([route.from,route.to])} fill="none" stroke="#799b92" strokeWidth={3} strokeDasharray="8 8"/>}
      {points.length>1&&<polyline points={line(points)} fill="none" stroke={C.green} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round"/>}
      {route&&marker(route.from,'출발',C.green,'from')}{route&&marker(route.to,'도착','#5072b4','to')}
      {points.length>0&&(()=>{const last=points[points.length-1],[x,y]=xy(last),angle=points.length>1?bearing(points[points.length-2],last):0;return <g transform={`translate(${x},${y})`}><circle r={25} fill="#10845422"/><circle r={17} fill="white"/><path d="M0 -12 L9 10 L0 6 L-9 10 Z" fill={C.green} transform={`rotate(${angle})`}/></g>;})()}
      {places.map((p,i)=>marker(p,places.length===1?p.name:`${i+1}`,i===selectedPlace?C.green:'#79918a','place'+i,()=>onSelectPlace?.(i)))}
    </svg>
    <View style={{position:'absolute',top:8,alignSelf:'center',borderRadius:14,paddingHorizontal:12,paddingVertical:5,backgroundColor:'#ffffffed'}}><Text style={[S.note,{fontSize:11}]}>오프라인 위치 미리보기 · 도로 지도 아님</Text></View>
  </View>;
}
