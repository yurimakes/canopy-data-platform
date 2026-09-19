import Text from './AppText';
import React, {useEffect,useRef,useState} from 'react';
import {Pressable,StyleSheet,TextInput,View} from 'react-native';
import {MODES,type TransportMode} from '../types';
import type {FeedbackInput,ServerTrip} from '../tripApi';
import {C,Icon,S,Stat,Note} from './theme';

const name=(mode:TransportMode)=>MODES.find(m=>m.value===mode)?.title??mode;
const distance=(meters:number)=>meters>=1000?`${(meters/1000).toFixed(2)} km`:`${Math.round(meters)} m`;
export function TripResult({trip,pending,onFeedback}:{trip:ServerTrip;pending?:FeedbackInput;
  onFeedback(input:FeedbackInput):Promise<void>}) {
  const [issue,setIssue]=useState(false),[text,setText]=useState(''),[saving,setSaving]=useState(false),[error,setError]=useState('');
  const sending=useRef(false);
  useEffect(()=>{setIssue(false);setText('');setError('');},[trip.trip_id]);
  const pendingKey=JSON.stringify(pending);
  useEffect(()=>{if(pending){setIssue(pending.has_issue);setText(pending.feedback_text??'');}},[pendingKey]);
  const answered=trip.feedback_status==='submitted'||trip.feedback_status==='no_issue';
  const locked=saving||!!pending;
  async function submit(has_issue:boolean) {
    if(sending.current)return;sending.current=true;setSaving(true);setError('');
    try {await onFeedback(pending??{has_issue,feedback_text:has_issue?text:null});}
    catch(e){setError(String(e));}finally{sending.current=false;setSaving(false);}
  }
  return <View style={s.root}>
    <View style={S.row}><Icon name="checkmark-circle" size={30}/><Text style={S.heading}>오늘의 여정이 쌓였어요</Text></View>
    <Note>{new Date(trip.started_at).toLocaleDateString('ko-KR')} / {new Date(trip.started_at).toLocaleTimeString('ko-KR')}{trip.ended_at?` ~ ${new Date(trip.ended_at).toLocaleTimeString('ko-KR')}`:''}</Note>
    {trip.is_mock && <Text style={s.note}>테스트용 예시입니다. 이동수단과 거리는 실제 GPS 분석 결과가 아닙니다.</Text>}
    {trip.confirmed_trip&&<View style={[S.row,{padding:18,borderRadius:18,backgroundColor:C.mint}]}><Stat label="총 이동거리" value={distance(trip.confirmed_trip.total_distance_m)}/><Stat label="탄소 배출량" value={`${trip.confirmed_trip.total_carbon_kg.toFixed(3)} kg`}/></View>}
    <Text style={S.heading}>나의 이동 타임라인</Text>
    {trip.segments.map((segment,index)=><View key={segment.segment_id} style={s.segment}>
      <View style={S.row}><Icon name={segment.mode==='walk'?'walk-outline':segment.mode==='bike'?'bicycle-outline':segment.mode==='car'?'car-outline':segment.mode==='bus'?'bus-outline':'train-outline'}/><Text style={s.title}>구간 {index+1}  {name(segment.confirmed_mode??segment.mode).replace('·',' / ')}</Text></View>
      <Text>{new Date(segment.start_time).toLocaleTimeString('ko-KR')} ~ {new Date(segment.end_time).toLocaleTimeString('ko-KR')} / {distance(segment.distance_m)}</Text>
      {segment.carbon_kg!=null && <Text>탄소 {segment.carbon_kg.toFixed(6)} kgCO2e</Text>}
    </View>)}
    {trip.confirmed_trip && <View style={s.segment}>
      <Text style={s.title}>이동수단별 거리</Text>
      {MODES.map(mode=>{const value=trip.confirmed_trip![`${mode.value}_distance_m`];
        return value>0?<Text key={mode.value}>{mode.title} {distance(value)}</Text>:null;})}
      <Text style={s.note}>탄소 배출량은 kgCO₂e 기준입니다. 이동 기준과 비교한 감축량은 별도 분석 결과로 제공됩니다.</Text>
    </View>}
    <View style={s.feedback}>
      <Text style={S.heading}>이동 결과는 어땠나요?</Text><Note>문제가 있었다면 알려주세요. 피드백은 검토에 전달되며 확정된 탄소량이나 토큰을 바로 변경하지 않습니다.</Note>
      {answered?<Text style={s.note}>{trip.has_issue?'피드백을 보냈습니다. 검토에 참고하겠습니다.':'문제없음으로 응답했습니다.'}</Text>:<>
        <View style={s.buttons}>
          <Pressable accessibilityRole="button" accessibilityState={{selected:issue,disabled:locked}} disabled={locked}
            onPress={()=>setIssue(true)} style={[s.button,issue&&s.selected,locked&&s.disabled]}><Text style={issue?s.white:s.text}>문제가 있었어요</Text></Pressable>
          <Pressable accessibilityRole="button" disabled={locked} onPress={()=>void submit(false)} style={[s.button,locked&&s.disabled]}><Text style={s.text}>문제없어요</Text></Pressable>
        </View>
        {issue && <>
          <Text style={s.note}>피드백 내용 (선택, 최대 500자)</Text>
          <TextInput accessibilityLabel="피드백 내용" multiline editable={!locked} maxLength={1000} value={text}
            onChangeText={value=>{if(Array.from(value).length<=500)setText(value);}} style={s.input}/>
          <Text style={s.note}>{Array.from(text).length}/500</Text>
          {!pending && <Pressable accessibilityRole="button" disabled={saving} onPress={()=>void submit(true)} style={[s.button,s.selected,saving&&s.disabled]}>
            <Text style={s.white}>{saving?'전송 중…':'피드백 보내기'}</Text></Pressable>}
        </>}
        {!!pending && <><Text style={s.note}>응답을 휴대폰에 보관했습니다. 연결이 복구되면 다시 전송합니다.</Text>
          <Pressable accessibilityRole="button" disabled={saving} onPress={()=>void submit(pending.has_issue)} style={s.button}><Text style={s.text}>다시 시도</Text></Pressable></>}
      </>}
      {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
    </View>
  </View>;
}
const s=StyleSheet.create({root:{gap:16},title:{fontSize:17,fontWeight:'600',color:'#174c39'},note:{color:'#66736e',lineHeight:20},
  segment:{gap:10,paddingVertical:12,borderBottomWidth:1,borderColor:'#d9e2dc'},feedback:{gap:10},buttons:{flexDirection:'row',flexWrap:'wrap',gap:8},
  input:{minHeight:80,borderWidth:1,borderColor:'#9eb7a8',borderRadius:10,padding:12,textAlignVertical:'top'},
  button:{minWidth:72,padding:14,borderWidth:1,borderColor:'#9eb7a8',borderRadius:10,alignItems:'center'},selected:{backgroundColor:'#087f5b'},
  text:{color:'#174c39',fontWeight:'600'},white:{color:'#fff',fontWeight:'600'},error:{color:'#ad2929'},disabled:{opacity:.5}});
