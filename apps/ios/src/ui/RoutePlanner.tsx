import React,{useState} from 'react';
import {Modal,Platform,Pressable,ScrollView,Text,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import Constants from 'expo-constants';
import {type Place,type Profile,type PlannedRoute,searchRoutes,routeApiUrl,km,validPlace} from '../service';
import {Button,Card,Field,Icon,Note,S,C} from './theme';
import JourneyMap from './JourneyMap';
export function PlacePicker({title,value,onPick}:{title:string;value:Place|null;onPick(p:Place):void}) {
  const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[results,setResults]=useState<Place[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function search(current=false){if(busy)return;setBusy(true);setError('');setResults([]);try {
    if(Platform.OS==='web')throw Error('장소 검색은 iPhone에서 사용할 수 있어요.');
    if(!(await Location.requestForegroundPermissionsAsync()).granted)throw Error('장소를 설정하려면 위치 접근을 허용해주세요.');
    if(current){const l=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.Balanced});setResults([{name:'현재 위치',...l.coords}]);}
    else{if(query.trim().length<2)throw Error('주소 또는 장소를 두 글자 이상 입력해주세요.');const list=await Location.geocodeAsync(query.trim());setResults(list.map(x=>({name:query.trim(),latitude:x.latitude,longitude:x.longitude})).filter(validPlace));if(!list.length)setError('검색 결과가 없습니다. 도로명 주소로 다시 검색해주세요.');}
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <><Pressable accessibilityRole="button" accessibilityLabel={`${title} 설정`} onPress={()=>{setOpen(true);setError('');}} style={[S.card,{padding:16,borderRadius:16}]}><View style={S.between}><View style={{flex:1,gap:5}}><Text style={S.note}>{title}</Text><Text style={S.label}>{value?.name??'장소를 설정해주세요'}</Text></View><Icon name="search-outline" size={19}/></View></Pressable>
    <Modal visible={open} animationType="slide" onRequestClose={()=>setOpen(false)}><SafeAreaView style={S.root}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={S.scroll}>
      <View style={S.between}><Text style={S.heading}>{title} 설정</Text><Button title="닫기" quiet onPress={()=>setOpen(false)}/></View>
      <Field label="주소 또는 장소" value={query} onChangeText={setQuery} placeholder="예: 서울특별시 중구 세종대로 110" returnKeyType="search" onSubmitEditing={()=>void search()}/>
      <Button title="장소 검색" busy={busy} onPress={()=>void search()}/><Button title="현재 위치 사용" quiet disabled={busy} onPress={()=>void search(true)}/>
      {!!error&&<Note error>{error}</Note>}
      {results.map((p,i)=><Card key={i}><Text style={S.heading}>{p.name}</Text><Note>{p.latitude.toFixed(5)}, {p.longitude.toFixed(5)}</Note><Button title="이 위치 선택" onPress={()=>{onPick(p);setOpen(false);}}/></Card>)}
    </ScrollView></SafeAreaView></Modal></>;
}
export function RoutePlanner({profile,onChoose,onFree}:{profile:Profile;onChoose(route:PlannedRoute):void;onFree():void}){
  const [from,setFrom]=useState<Place|null>(profile.home),[to,setTo]=useState<Place|null>(profile.work);
  const [routes,setRoutes]=useState<PlannedRoute[]|null>(null),[selected,setSelected]=useState<PlannedRoute|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  function change(which:'from'|'to',p:Place){if(busy)return;if(which==='from')setFrom(p);else setTo(p);setRoutes(null);setSelected(null);setError('');}
  async function search(){if(!from||!to||busy)return;setBusy(true);setError('');setSelected(null);setRoutes(null);try{
    const extra=Constants.expoConfig?.extra??{},url=routeApiUrl(extra);
    const token=extra.tripAccessToken,key=extra.tripFunctionKey||extra.gpsFunctionKey;
    const r=await searchRoutes(url,{...(token?{Authorization:'Bearer '+token}:{}),...(key?{'x-functions-key':key}:{})},from,to);setRoutes(r);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <><Text style={S.title}>어디로 떠나볼까요?</Text><Note>평소 출퇴근길도, 오늘의 다른 목적지도 자유롭게.</Note>
    <View pointerEvents={busy?"none":"auto"} style={{gap:10,opacity:busy?0.6:1}}><PlacePicker title="출발지" value={from} onPick={p=>change('from',p)}/><Button title="출발지와 도착지 바꾸기" quiet onPress={()=>{setFrom(to);setTo(from);setRoutes(null);setSelected(null);}}/><PlacePicker title="도착지" value={to} onPick={p=>change('to',p)}/></View>
    <Button title="대중교통 경로 찾기" busy={busy} disabled={!from||!to} onPress={()=>void search()}/>
    {!!error&&<Note error>{error}</Note>}
    {routes?.length===0&&<Card><Text style={S.heading}>찾은 경로가 없어요</Text><Note>출발지와 도착지를 변경하거나 경로 없이 기록해보세요.</Note></Card>}
    {routes?.map(r=><Pressable key={r.id} accessibilityRole="button" accessibilityState={{selected:selected?.id===r.id}} onPress={()=>setSelected(r)} style={[S.card,selected?.id===r.id&&{borderColor:C.green,borderWidth:2}]}>
      <View style={S.between}><Text style={S.heading}>{r.minutes}분</Text><Text style={S.pill}>{km(r.distance_m)}</Text></View><Text style={S.label}>{r.legs.map(l=>l.name).join(' → ')}</Text><Note>{r.fare==null?'요금 정보 없음':`${r.fare.toLocaleString()}원`} / TMAP 제공</Note></Pressable>)}
    {selected&&<><View style={{borderRadius:24,overflow:'hidden'}}><JourneyMap points={[]} route={selected}/></View>
      <Card><Text style={S.heading}>이렇게 이동해요</Text><Text style={S.label}>{selected.from.name}</Text>
        {selected.legs.map((leg,i)=><View key={i} style={[S.row,{alignItems:'flex-start'}]}>
          <View style={{padding:10,borderRadius:14,backgroundColor:C.mint}}><Icon name={leg.mode==='WALK'?'walk-outline':leg.mode==='BUS'?'bus-outline':'train-outline'}/></View>
          <View style={{flex:1,gap:5,paddingBottom:16,borderBottomWidth:1,borderColor:C.line}}><Text style={S.label}>{leg.name}</Text><Note>{leg.minutes}분 / {km(leg.distance_m)}</Note>{(leg.startName||leg.endName)&&<Note>{leg.startName??'출발'} → {leg.endName??'도착'}</Note>}</View>
        </View>)}<Text style={S.label}>{selected.to.name}</Text><Note>검색 시각 {new Date(selected.searchedAt).toLocaleTimeString('ko-KR')} / 교통 상황에 따라 실제 소요 시간이 달라질 수 있어요.</Note>
      </Card><Card><View style={S.row}><Icon name="leaf-outline"/><Text style={S.heading}>나의 이동 기준</Text></View><Note>Baseline 조회 기능을 연결하면 비교 기준을 보여드릴게요. 선택한 경로의 예상 거리와 실제 이동 결과는 다를 수 있어요.</Note></Card><Button title="이 경로로 여정 준비" onPress={()=>onChoose(selected)}/></>}
    <Button title="경로 없이 자유롭게 기록하기" quiet onPress={onFree}/><Note>경로 선택은 안내용입니다. 실제 이동은 GPS로 기록해요.</Note>
  </>;
}
