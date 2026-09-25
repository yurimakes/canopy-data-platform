import {getStorage} from '../backgroundLocationTask';
import {exportTrip} from '../exporter';
import {files} from '../files';
import {IllustratedIcon} from './IllustratedIcon';
import React,{useState} from 'react';
import {Pressable,View} from 'react-native';
import type {Summary} from '../types';
import Text from './AppText';
import {Button,Card,C,Icon,Note,S} from './theme';
import {Eyebrow,Segmented} from './DesignPrimitives';
export function JourneyHistory({trips,developer,busy,onOpen,onStart}:{trips:Summary[];developer:boolean;busy:boolean;onOpen(id:string):void;onStart():void}){
 const [filter,setFilter]=useState('all'),[exporting,setExporting]=useState<string|null>(null),[error,setError]=useState('');
 async function share(id:string){setExporting(id);setError('');try{await exportTrip(await getStorage(),files,id,'gps',new Date().toISOString());}catch(e){setError(String(e));}finally{setExporting(null);}}
 const rows=trips.filter(t=>filter==='all'||(t.collection_mode??'developer')===filter).slice().sort((a,b)=>Date.parse(b.started_at)-Date.parse(a.started_at));
 return <><Eyebrow>YOUR GREEN FOOTPRINT</Eyebrow><Text style={S.title}>나의 이동이{'\n'}만든 이야기.</Text><Note>차곡차곡 쌓인 초록 발걸음을 돌아보세요.</Note>
 {!!error&&<Note error>{error}</Note>}
 {developer&&<Segmented items={[{id:'all',label:'전체'},{id:'user',label:'사용자'},{id:'developer',label:'개발자'}]} value={filter} onChange={setFilter}/>}
 {!rows.length&&<Card><IllustratedIcon name="walk" size={65}/><Text style={S.heading}>첫 발걸음을 기다려요</Text><Note>여정을 마치면 여기에 기록돼요.</Note><Button title="첫 여정 시작하기" onPress={onStart}/></Card>}
 {rows.map((trip,i)=>{const date=new Date(trip.started_at),day=date.toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'short'}),previous=i?new Date(rows[i-1].started_at).toDateString():'';return <View key={trip.trip_id} style={{gap:12}}>{date.toDateString()!==previous&&<Text style={[S.label,{marginTop:8}]}>{day}</Text>}<Pressable accessibilityRole="button" disabled={busy} onPress={()=>onOpen(trip.trip_id)} style={[S.row,{padding:20,borderRadius:22,backgroundColor:C.white,borderWidth:1,borderColor:C.line}]}><View style={{backgroundColor:C.mint,padding:12,borderRadius:16}}><IllustratedIcon name="walk" size={42}/></View><View style={{flex:1,gap:6}}><Text style={S.label}>{date.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})}의 발걸음</Text><Text style={S.note}>{trip.status==='recording'?'이동 중':trip.status==='interrupted'?'기록 중단':'기록 완료'}</Text></View><Icon name="chevron-forward" size={18}/></Pressable>{trip.status!=='recording'&&trip.gps_count>0&&<Button title="GPS 기록 내보내기" quiet disabled={busy||!!exporting} onPress={()=>void share(trip.trip_id)}/>}</View>;})}</>;
}
