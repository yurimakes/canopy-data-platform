import React, {useEffect,useState} from 'react';
import {Pressable,StyleSheet,Text,View} from 'react-native';
import {MODES,type TransportMode} from '../types';
import type {Confirmation,ServerTrip} from '../tripApi';

const name=(mode:TransportMode)=>MODES.find(m=>m.value===mode)?.title??mode;
const distance=(meters:number)=>meters>=1000?`${(meters/1000).toFixed(2)} km`:`${Math.round(meters)} m`;
export function TripResult({trip,pending,onConfirm}:{trip:ServerTrip;pending?:Confirmation[];
  onConfirm(segments:Confirmation[]):Promise<void>}) {
  const [editing,setEditing]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const [modes,setModes]=useState<Record<string,TransportMode>>({});
  const pendingKey=JSON.stringify(pending);
  useEffect(()=>{
    setModes(Object.fromEntries((pending??trip.segments.map(s=>({segment_id:s.segment_id,confirmed_mode:s.confirmed_mode??s.mode})))
      .map(s=>[s.segment_id,s.confirmed_mode])));
    setEditing(false);setError('');
  },[trip.trip_id,trip.revision,pendingKey]);
  const locked=saving||!!pending;
  const confirmed=trip.confirmation_status==='confirmed';
  async function save() {
    if(saving)return;setSaving(true);setError('');
    try {
      await onConfirm(pending??trip.segments.map(s=>({segment_id:s.segment_id,confirmed_mode:modes[s.segment_id]??s.confirmed_mode??s.mode})));
      setEditing(false);
    }catch(e){setError(String(e));}finally{setSaving(false);}
  }
  return <View style={s.root}>
    <Text style={s.title}>{confirmed?'이동 완료':'이동 결과 확인'}</Text>
    {trip.is_mock && <Text style={s.note}>테스트용 예시입니다. 이동수단과 거리는 실제 GPS 분석 결과가 아닙니다.</Text>}
    {trip.segments.map((segment,index)=><View key={segment.segment_id} style={s.segment}>
      <Text style={s.title}>구간 {index+1}  {name(modes[segment.segment_id]??segment.confirmed_mode??segment.mode)}</Text>
      <Text>{new Date(segment.start_time).toLocaleTimeString('ko-KR')} ~ {new Date(segment.end_time).toLocaleTimeString('ko-KR')} / {distance(segment.distance_m)}</Text>
      {(editing||pending) && <View style={s.modes}>{MODES.map(m=><Pressable key={m.value} accessibilityRole="button"
        accessibilityState={{selected:modes[segment.segment_id]===m.value,disabled:locked}} disabled={locked}
        onPress={()=>setModes(values=>({...values,[segment.segment_id]:m.value}))}
        style={[s.button,modes[segment.segment_id]===m.value&&s.selected,locked&&s.disabled]}>
        <Text style={modes[segment.segment_id]===m.value?s.white:s.text}>{m.title}</Text>
      </Pressable>)}</View>}
      {confirmed && !editing && !locked && segment.carbon_kg!=null && <Text>탄소 {segment.carbon_kg.toFixed(6)} kgCO2e</Text>}
    </View>)}
    {trip.confirmed_trip && !editing && !locked && <View style={s.segment}>
      <Text style={s.title}>총 이동거리 {distance(trip.confirmed_trip.total_distance_m)}</Text>
      <Text>{trip.segments.map(s=>name(s.confirmed_mode??s.mode)).join(' → ')}</Text>
      {MODES.map(mode=>{
        const value=trip.confirmed_trip![`${mode.value}_distance_m`];
        return value>0?<Text key={mode.value}>{mode.title} {distance(value)}</Text>:null;
      })}
      <Text style={s.title}>탄소 배출량 {trip.confirmed_trip.total_carbon_kg.toFixed(6)} kgCO2e</Text>
      <Text style={s.note}>확인 완료 / 수정 {trip.revision??0}회</Text>
    </View>}
    {!!pending && <Text style={s.note}>확인 요청을 휴대폰에 보관했습니다. 연결이 복구되면 같은 요청으로 다시 전송합니다.</Text>}
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    {(!confirmed||editing||pending) && <Pressable accessibilityRole="button" disabled={saving} onPress={()=>void save()} style={[s.button,s.selected,saving&&s.disabled]}>
      <Text style={s.white}>{saving?'저장 중…':pending?'다시 시도':editing?'수정 내용 저장':'맞아요'}</Text>
    </Pressable>}
    {!editing && !pending && <Pressable accessibilityRole="button" disabled={saving} onPress={()=>{setEditing(true);setError('');}} style={s.button}><Text style={s.text}>수정하기</Text></Pressable>}
    {editing && !locked && <Pressable accessibilityRole="button" onPress={()=>{
      setModes(Object.fromEntries(trip.segments.map(s=>[s.segment_id,s.confirmed_mode??s.mode])));setEditing(false);setError('');
    }} style={s.button}><Text style={s.text}>취소</Text></Pressable>}
  </View>;
}
const s=StyleSheet.create({root:{gap:16},title:{fontSize:17,fontWeight:'600',color:'#174c39'},note:{color:'#66736e',lineHeight:20},
  segment:{gap:10,paddingVertical:12,borderBottomWidth:1,borderColor:'#d9e2dc'},modes:{flexDirection:'row',flexWrap:'wrap',gap:8},
  button:{padding:14,borderWidth:1,borderColor:'#9eb7a8',borderRadius:10,alignItems:'center'},selected:{backgroundColor:'#087f5b'},
  text:{color:'#174c39',fontWeight:'600'},white:{color:'#fff',fontWeight:'600'},error:{color:'#ad2929'},disabled:{opacity:.5}});
