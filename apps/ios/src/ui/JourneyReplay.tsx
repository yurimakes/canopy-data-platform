import {metersBetween} from '../journeyGeometry';
import {MODES} from '../types';
import type {ServerTrip} from '../tripApi';
import React,{useEffect,useState} from 'react';
import {Text,View} from 'react-native';
import {ActiveJourney} from './ActiveJourney';
import {Button,Note,S} from './theme';
import {localAction} from '../communityClient';
import type {GpsEvent} from '../types';
import type {PlannedRoute} from '../service';
export function JourneyReplay({trip,onClose}:{trip:ServerTrip;onClose():void}){
 const tripId=trip.trip_id;
 const [events,setEvents]=useState<GpsEvent[]>([]),[index,setIndex]=useState(1),[playing,setPlaying]=useState(true),[error,setError]=useState('');
 useEffect(()=>{let alive=true;void localAction('/gps/'+tripId).then(r=>{if(alive)setEvents(r.events);}).catch(e=>{if(alive)setError(String(e));});return()=>{alive=false;};},[tripId]);
 useEffect(()=>{if(!playing||!events.length)return;const timer=setInterval(()=>setIndex(i=>Math.min(events.length,i+1)),150);return()=>clearInterval(timer);},[playing,events.length]);
 const first=events[0],last=events.at(-1),current=events[Math.min(index-1,events.length-1)];
 const route:PlannedRoute|null=first&&last?{id:'replay',provider:'local-test',from:{latitude:first.lat,longitude:first.lon,name:'기록 출발지'},to:{latitude:last.lat,longitude:last.lon,name:'기록 도착지'},distance_m:0,minutes:0,fare:null,legs:[],searchedAt:first.event_time}:null;
 const seconds=first&&current?Math.max(0,Math.floor((Date.parse(current.event_time)-Date.parse(first.event_time))/1000)):0;
 const visible=events.slice(0,index);const distance=visible.reduce((sum,p,i)=>i?sum+metersBetween({latitude:visible[i-1].lat,longitude:visible[i-1].lon,name:''},{latitude:p.lat,longitude:p.lon,name:''}):0,0);
 const segment=trip.segments.find(s=>current&&Date.parse(s.start_time)<=Date.parse(current.event_time)&&Date.parse(s.end_time)>=Date.parse(current.event_time));
 const mode=MODES.find(m=>m.value===(segment?.confirmed_mode??segment?.mode))?.title??'구간 정보 없음';
 return <View style={{flex:1,padding:12,gap:8}}><Text style={S.heading}>저장한 GPS로 화면 재생</Text><Note>화면 검증용 재생 · 새 여정이나 보상은 생성하지 않습니다.</Note>{error?<Note error>{error}</Note>:<ActiveJourney replayDistance={distance} replayMode={mode+' · 저장 결과'} direction="outbound" p={{events:events.slice(0,index),active:true,route,duration:`${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`}}/>}<View style={S.row}><View style={{flex:1}}><Button title={playing?'일시정지':'계속 재생'} quiet onPress={()=>{if(index===events.length)setIndex(1);setPlaying(!playing);}}/></View><View style={{flex:1}}><Button title="결과로 돌아가기" onPress={onClose}/></View></View></View>;
}
