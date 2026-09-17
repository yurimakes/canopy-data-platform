import {CanopyMascot} from './CanopyMascot';
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
export function RoutePlanner({profile,direction='outbound',onChoose,onFree}:{profile:Profile;direction?:'outbound'|'return';onChoose(route:PlannedRoute):void;onFree():void}){
  const [from,setFrom]=useState<Place|null>(direction==='outbound'?profile.home:profile.work),[to,setTo]=useState<Place|null>(direction==='outbound'?profile.work:profile.home);
  const [routes,setRoutes]=useState<PlannedRoute[]|null>(null),[selected,setSelected]=useState<PlannedRoute|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  function change(which:'from'|'to',p:Place){if(busy)return;if(which==='from')setFrom(p);else setTo(p);setRoutes(null);setSelected(null);setError('');}
  async function search(){if(!from||!to||busy)return;setBusy(true);setError('');setSelected(null);setRoutes(null);try{
    const extra=Constants.expoConfig?.extra??{},url=routeApiUrl(extra);
    const token=extra.tripAccessToken,key=extra.tripFunctionKey||extra.gpsFunctionKey;
    const r=await searchRoutes(url,{...(token?{Authorization:'Bearer '+token}:{}),...(key?{'x-functions-key':key}:{})},from,to);setRoutes(r);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <>
    <Text style={S.note}>저장한 경로</Text>
    <View pointerEvents={busy?"none":"auto"} style={{gap:8,opacity:busy?.6:1}}>
      <PlacePicker title="출발지" value={from} onPick={p=>change('from',p)}/>
      <View style={{alignItems:'center',marginVertical:-8,zIndex:1}}><Pressable accessibilityRole="button" accessibilityLabel="출발지와 도착지 바꾸기" onPress={()=>{setFrom(to);setTo(from);setRoutes(null);setSelected(null);}} style={{backgroundColor:C.white,borderRadius:24,padding:10,borderWidth:1,borderColor:C.line}}><Icon name="swap-vertical" size={18}/></Pressable></View>
      <PlacePicker title="도착지" value={to} onPick={p=>change('to',p)}/>
    </View>
    <Button title="경로 찾기" busy={busy} disabled={!from||!to} onPress={()=>void search()}/>
    {busy&&<View style={{alignItems:'center',paddingVertical:18,gap:12}}><CanopyMascot pose="start" height={170}/><Text style={S.heading}>지금 경로를 분석하고 있어요</Text><Note>조금만 기다려주세요!</Note></View>}
    {!!error&&<Card><CanopyMascot height={140}/><Text style={[S.heading,{textAlign:'center'}]}>경로를 불러오지 못했어요</Text><Note error>{error}</Note><Button title="다시 시도하기" onPress={()=>void search()}/></Card>}
    {routes?.length===0&&<Card><CanopyMascot height={160}/><Text style={S.heading}>경로를 찾을 수 없어요</Text><Note>출발지와 도착지를 변경하거나 경로 없이 기록해보세요.</Note></Card>}
    {!!routes?.length&&<Text style={S.note}>추천 경로 - 지금 출발</Text>}
    {routes?.map(r=><Pressable key={r.id} accessibilityRole="button" accessibilityLabel={`${r.minutes}분 경로 상세보기`} onPress={()=>setSelected(r)} style={[S.card,{gap:12,boxShadow:'0 4px 16px #174c3909'}]}>
      <Text style={[S.metric,{fontSize:26,color:C.ink}]}>{r.minutes}분</Text>
      <Note>{km(r.distance_m)} / {r.fare==null?'요금 정보 없음':`${r.fare.toLocaleString()}원`}</Note>
      <RouteStrip route={r}/><View style={S.between}><Text numberOfLines={1} style={[S.note,{flex:1}]}>{r.legs.filter(l=>l.mode!=='WALK').map(l=>l.name).join(' / ')||'도보'}</Text><Text style={S.pill}>경로 상세보기</Text></View>
    </Pressable>)}
    <Button title="경로 없이 자유롭게 기록하기" quiet onPress={onFree}/>
    <Modal visible={!!selected} animationType="slide" onRequestClose={()=>setSelected(null)}><SafeAreaView style={S.root}>
      <View style={[S.row,{padding:16}]}><Pressable accessibilityRole="button" accessibilityLabel="경로 목록으로" onPress={()=>setSelected(null)} style={{padding:8}}><Icon name="arrow-back"/></Pressable><Text style={S.heading}>경로 상세보기</Text></View>
      {selected&&<ScrollView contentContainerStyle={S.scroll}><Card><Text style={[S.metric,{fontSize:28}]}>{selected.minutes}분</Text><Note>{km(selected.distance_m)} / {selected.fare==null?'요금 정보 없음':`${selected.fare.toLocaleString()}원`}</Note><RouteStrip route={selected}/></Card>
        <View style={{borderRadius:16,overflow:'hidden'}}><JourneyMap points={[]} route={selected}/></View>
        <Text style={S.label}>상세 이동 경로</Text><Card>
          <View style={S.row}><Icon name="location-outline"/><Text style={S.label}>{selected.from.name} 출발</Text></View>
          {selected.legs.map((leg,i)=><View key={i} style={[S.row,{alignItems:'flex-start'}]}><View style={{alignItems:'center',width:28,gap:5}}><Icon color={leg.mode==='WALK'?C.muted:'#318cef'} name={leg.mode==='WALK'?'walk-outline':leg.mode==='BUS'?'bus-outline':'train-outline'}/><View style={{width:1,backgroundColor:C.line,minHeight:32}}/></View><View style={{flex:1,gap:4,paddingBottom:14}}><Text style={S.label}>{leg.name}</Text><Note>{leg.minutes}분 / {km(leg.distance_m)}</Note>{(leg.startName||leg.endName)&&<Note>{leg.startName??'출발'} → {leg.endName??'도착'}</Note>}</View></View>)}
          <View style={S.row}><Icon name="flag-outline"/><Text style={S.label}>{selected.to.name} 도착</Text></View>
        </Card><Card><Text style={S.label}>나의 이동 기준</Text><Note>이동 기록을 바탕으로 한 Baseline 연결 후 비교 결과가 표시됩니다.</Note></Card>
        <Button title="이 경로로 안내 시작" onPress={()=>{const chosen=selected;setSelected(null);onChoose(chosen);}}/>
        <Note>TMAP 검색 결과입니다. 실제 이동 시간과 거리는 GPS 기록 후 확정됩니다.</Note>
      </ScrollView>}
    </SafeAreaView></Modal>
  </>;
}

export function RouteStrip({route}:{route:PlannedRoute}){return <View style={{flexDirection:'row',gap:3,minHeight:24}}>{route.legs.map((leg,i)=><View key={i} style={{flex:Math.max(leg.minutes,5),backgroundColor:leg.mode==='WALK'?'#80958b':leg.mode==='BUS'?'#80c83f':'#318cef',borderRadius:16,justifyContent:'center',alignItems:'center',paddingHorizontal:3,paddingVertical:6}}><Text numberOfLines={1} style={{fontSize:10,color:C.white}}>{leg.mode==='WALK'?'도보':leg.mode==='BUS'?'버스':'지하철'} {leg.minutes}분</Text></View>)}</View>;}
