import {currentOrigin} from '../currentOrigin';
import Text from './AppText';
import type {BaselineView,RemotePanel} from './CommunityPanels';
import {attachRouteQuote} from '../routeQuote';
import {PopulationPreview} from './PopulationPreview';
import {localAction} from '../communityClient';
import React,{useEffect,useRef,useState} from 'react';
import {Modal,Platform,Pressable,ScrollView,View} from 'react-native';
import {SafeAreaView,SafeAreaProvider} from 'react-native-safe-area-context';
import * as Location from 'expo-location';
import Constants from 'expo-constants';
import {session} from '../accountSession';
import {type Place,type Profile,type PlannedRoute,searchRoutes,searchPlaces,routeApiUrl,km,validPlace} from '../service';
import {Disclosure,Eyebrow} from './DesignPrimitives';
import {Button,Card,Field,Icon,Note,S,C} from './theme';
import JourneyMap from './JourneyMap';
function searchConfig(){const extra=Constants.expoConfig?.extra??{},saved=session();const token=saved?.api_url===extra.tripApiUrl?.replace(/\/+$/,'')?saved?.access_token:undefined,key=extra.tripFunctionKey||extra.gpsFunctionKey;return {url:routeApiUrl(extra),headers:{...(token?{Authorization:'Bearer '+token}:{}),...(key?{'x-functions-key':key}:{})} as Record<string,string>};}
export function PlacePicker({title,value,onPick}:{title:string;value:Place|null;onPick(p:Place):void}) {
  const [open,setOpen]=useState(false),[query,setQuery]=useState(''),[results,setResults]=useState<Place[]>([]),[selected,setSelected]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(''),[searched,setSearched]=useState(false);
  const requestId=useRef(0);
  const [latitude,setLatitude]=useState(''),[longitude,setLongitude]=useState('');
  function close(){requestId.current++;setOpen(false);setBusy(false);}
  async function search(current=false){if(busy)return;const id=++requestId.current;setBusy(true);setError('');setResults([]);setSearched(false);try {
    let places:Place[];
    if(current){
      if(Platform.OS==='web')throw Error('현재 위치는 iPhone에서 사용할 수 있어요.');
      if(!(await Location.requestForegroundPermissionsAsync()).granted)throw Error('현재 위치를 사용하려면 위치 접근을 허용해주세요. 장소 이름 검색은 권한 없이 가능합니다.');
      const l=await Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High});
      if(l.coords.accuracy==null||l.coords.accuracy>100)throw Error('현재 위치의 오차가 커요. 실외에서 다시 시도하거나 정확한 좌표를 입력해주세요.');
      let address='지도에서 위치를 확인해주세요';
      try{const [a]=await Location.reverseGeocodeAsync(l.coords);if(a)address=[a.region,a.city,a.district,a.street,a.streetNumber].filter(Boolean).join(' ');}catch{}
      places=[{name:'현재 위치',address,latitude:l.coords.latitude,longitude:l.coords.longitude}];
    }else if(Constants.expoConfig?.extra?.localOnly){places=(await localAction('/journey/places',{query})).places;}else{const config=searchConfig();places=await searchPlaces(config.url,config.headers,query);}
    if(id!==requestId.current)return;setResults(places.filter(validPlace));setSelected(0);setSearched(true);
  }catch(e){if(id===requestId.current)setError(e instanceof Error?e.message:String(e));}finally{if(id===requestId.current)setBusy(false);}}
  return <><Pressable accessibilityRole="button" accessibilityLabel={`${title} 설정`} onPress={()=>{setOpen(true);setError('');}} style={[S.card,{padding:16,borderRadius:16}]}><View style={S.between}><View style={{flex:1,gap:5}}><Text style={S.note}>{title}</Text><Text style={S.label}>{value?.name??'장소를 설정해주세요'}</Text>{!!value?.address&&<Text style={S.note}>{value.address}</Text>}</View><Icon name="search-outline" size={19}/></View></Pressable>
    <Modal visible={open} animationType="slide" onRequestClose={close}><SafeAreaProvider><SafeAreaView style={S.root}>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={S.scroll}>
        <View style={S.between}><Text style={S.heading}>{title} 검색</Text><Button title="닫기" quiet onPress={close}/></View>
        <Field label="장소 이름 또는 주소" value={query} onChangeText={text=>{requestId.current++;setBusy(false);setQuery(text);setResults([]);setError('');setSearched(false);}} placeholder={Constants.expoConfig?.extra?.localOnly?'예: 천안 신방동, 서울 역삼동':'예: 천안역, 일봉로 71'} returnKeyType="search" onSubmitEditing={()=>void search()}/>
        {Constants.expoConfig?.extra?.localOnly&&<Note>오프라인에서는 행정동 이름으로 검색합니다. 결과는 실제 건물 위치가 아닌 행정동 중심점입니다.</Note>}<Button title="검색" busy={busy} onPress={()=>void search()}/><Button title="현재 위치 사용" quiet disabled={busy} onPress={()=>void search(true)}/>
        {(title==='집'||title==='직장')&&<Disclosure title="좌표로 직접 지정"><Note>주소 검색 또는 현재 위치로 등록하세요.</Note>
          <Field label="위도" value={latitude} onChangeText={setLatitude} placeholder="예: 37.501"/><Field label="경도" value={longitude} onChangeText={setLongitude} placeholder="예: 127.039"/>
          <Button title="입력한 좌표 사용" quiet onPress={()=>{const p={name:query.trim()||title,latitude:Number(latitude),longitude:Number(longitude),address:'직접 지정한 위치'};if(!latitude.trim()||!longitude.trim()||!validPlace(p)){setError('유효한 위도와 경도를 입력해주세요.');return;}onPick(p);close();}}/></Disclosure>}
        {!!error&&<Note error>{error}</Note>}
        {!!results.length&&<><Text style={S.note}>검색 결과 {results.length}곳 — 목록이나 지도 핀을 선택해주세요</Text><View style={{borderRadius:20,overflow:'hidden'}}><JourneyMap points={[]} places={results} selectedPlace={selected} onSelectPlace={setSelected} height={230}/></View></>}
        {searched&&!results.length&&<Card><Icon name="search-outline"/><Text style={S.label}>검색 결과가 없어요</Text><Note>지역명과 장소 이름을 함께 입력해보세요.</Note></Card>}
        {results.map((p,i)=><Pressable key={`${p.id??p.name}-${i}`} accessibilityRole="button" accessibilityState={{selected:selected===i}} accessibilityLabel={`${p.name}, ${p.address||'주소 정보 없음'}`} onPress={()=>setSelected(i)} style={[S.card,{gap:8,borderColor:selected===i?C.green:C.line,borderWidth:selected===i?2:1}]}><View style={S.row}><Icon name={selected===i?'location':'location-outline'}/><Text style={[S.label,{flex:1}]}>{p.name}</Text>{selected===i&&<Icon name="checkmark-circle"/>}</View><Text style={S.note}>{p.address||'주소 정보 없음 — 지도에서 위치를 확인해주세요'}</Text></Pressable>)}
      </ScrollView>
      {!!results[selected]&&<View style={{padding:20,borderTopWidth:1,borderTopColor:C.line,backgroundColor:C.white,gap:8}}><Text numberOfLines={1} style={S.label}>{results[selected].name}</Text><Button title={`${title}로 선택`} onPress={()=>{if((title==='집'||title==='직장')&&results[selected].address?.includes('행정동 중심점')){setError('행정동 중심점은 출퇴근 위치로 사용할 수 없어요. 현재 위치 또는 정확한 좌표를 선택해주세요.');return;}onPick(results[selected]);close();}}/></View>}
    </SafeAreaView></SafeAreaProvider></Modal></>;
}
export function RoutePlanner({profile,direction='outbound',onChoose,onFree,baseline}:{baseline?:RemotePanel<BaselineView>;profile:Profile;direction?:'outbound'|'return';onChoose(route:PlannedRoute):void;onFree():void}){
  const [from,setFrom]=useState<Place|null>(null),[to,setTo]=useState<Place|null>(null);
  const [routes,setRoutes]=useState<PlannedRoute[]|null>(null),[selected,setSelected]=useState<PlannedRoute|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const [locating,setLocating]=useState(false),[originError,setOriginError]=useState('');
  const originGeneration=useRef(0),originAt=useRef(0);
  async function locate(){const generation=++originGeneration.current;setLocating(true);setOriginError('');setFrom(null);setRoutes(null);setSelected(null);try{
    const place=await currentOrigin({permission:async()=>(await Location.requestForegroundPermissionsAsync()).granted,position:()=>Location.getCurrentPositionAsync({accuracy:Location.Accuracy.High})});
    if(generation!==originGeneration.current)return null;setFrom(place);originAt.current=Date.now();return place;
  }catch(e){if(generation===originGeneration.current)setOriginError(e instanceof Error?e.message:String(e));return null;}finally{if(generation===originGeneration.current)setLocating(false);}}
  useEffect(()=>{void locate();return()=>{originGeneration.current++;};},[]);
  function change(p:Place){if(busy)return;setTo(p);setRoutes(null);setSelected(null);setError('');}
  async function search(){if(!to||busy||locating)return;setBusy(true);setError('');setSelected(null);setRoutes(null);try{
    const origin=from&&Date.now()-originAt.current<30000?from:await locate();if(!origin)return;

    const extra=Constants.expoConfig?.extra??{},url=routeApiUrl(extra);
    if(extra.localOnly){const r=await localAction('/journey/quote',{from:origin,to,direction});setRoutes([r]);setSelected(r);return;}
    const [routing,reference]=await Promise.allSettled([searchRoutes(url,searchConfig().headers,origin,to),localAction('/journey/quote',{from:origin,to,direction})]);
    if(reference.status==='rejected')throw reference.reason;
    const quote=reference.value as PlannedRoute;
    if(routing.status==='fulfilled'&&routing.value.length){setRoutes(routing.value.map(route=>attachRouteQuote(route,quote)));}
    else{setRoutes([attachRouteQuote(quote,quote)]);setError(routing.status==='rejected'?'길 안내를 불러오지 못했어요. 보상 기준은 확인할 수 있어요.':'가까운 거리예요. 아래 보상 기준을 확인하고 출발하세요.');}
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  return <>
    <Text style={[S.title,{fontSize:27}]}>어디로 갈까요?</Text>
    <View style={{backgroundColor:'#E5F1EA',borderRadius:22,padding:17,gap:8}}><View style={S.between}><View style={S.row}><Icon name="locate-outline"/><Text style={S.label}>{locating?'현재 위치 확인 중':from?'현재 위치에서 출발':'위치를 확인해주세요'}</Text></View><Pressable accessibilityRole="button" accessibilityLabel="현재 위치 다시 확인" disabled={locating||busy} onPress={()=>void locate()} style={{padding:10}}><Icon name="refresh" size={19}/></Pressable></View>{!!originError&&<Note error>{originError}</Note>}</View>
    <View pointerEvents={busy?"none":"auto"} style={{gap:8,opacity:busy?.6:1}}><PlacePicker title="목적지" value={to} onPick={change}/></View>
    <Button title={Constants.expoConfig?.extra?.localOnly?"보상 기준 확인":"경로 찾기"} busy={busy} disabled={!from||!to||locating} onPress={()=>void search()}/>
    {busy&&<View style={{alignItems:'center',paddingVertical:18,gap:12}}><Icon name="navigate-circle-outline" size={56}/><Text style={S.heading}>가는 길을 찾고 있어요</Text><Note>조금만 기다려주세요!</Note></View>}
    {!!error&&<Card><Icon name="cloud-offline-outline" size={48}/><Text style={[S.heading,{textAlign:'center'}]}>경로 검색 안내</Text><Note error>{error}</Note><Button title="다시 시도하기" onPress={()=>void search()}/></Card>}
    {routes?.length===0&&<Card><Icon name="search-outline" size={48}/><Text style={S.heading}>경로를 찾을 수 없어요</Text><Note>목적지를 변경하거나 경로 없이 기록해보세요.</Note></Card>}
    {!!routes?.length&&<Text style={S.note}>{Constants.expoConfig?.extra?.localOnly?'선택한 출발·도착지의 비교 기준':'추천 경로 - 지금 출발'}</Text>}
    {routes?.map(r=><Pressable key={r.id} accessibilityRole="button" accessibilityLabel={`${r.minutes}분 경로 상세보기`} onPress={()=>setSelected(r)} style={[S.card,{gap:12,boxShadow:'0 4px 16px #174c3909'}]}>
      <Text style={[S.metric,{fontSize:26,color:C.ink}]}>{r.minutes}분</Text>
      <Note>{km(r.distance_m)} / {r.fare==null?'요금 정보 없음':`${r.fare.toLocaleString()}원`}</Note>
      {r.expectedKg!==undefined&&<PopulationPreview route={r} baseline={baseline}/>}
      {r.provider==='local-test'&&<Note>직선거리 비교 기준 · 길 안내 경로가 아닙니다. 시간은 도보 참고값입니다.</Note>}
      <RouteStrip route={r}/><View style={S.between}><Text numberOfLines={1} style={[S.note,{flex:1}]}>{r.legs.filter(l=>l.mode!=='WALK').map(l=>l.name).join(' / ')||'도보'}</Text><Text style={S.pill}>경로 상세보기</Text></View>
    </Pressable>)}
    <Button title="목적지 없이 출발" quiet onPress={onFree}/>
    <Modal visible={!!selected} animationType="slide" onRequestClose={()=>setSelected(null)}><SafeAreaProvider><SafeAreaView style={S.root}>
      <View style={[S.row,{padding:16}]}><Pressable accessibilityRole="button" accessibilityLabel="경로 목록으로" onPress={()=>setSelected(null)} style={{padding:8}}><Icon name="arrow-back"/></Pressable><Text style={S.heading}>경로 상세보기</Text></View>
      {selected&&<ScrollView contentContainerStyle={S.scroll}>{selected.expectedKg!==undefined&&<PopulationPreview route={selected} baseline={baseline}/>}<Card><Text style={[S.metric,{fontSize:28}]}>{selected.minutes}분</Text><Note>{km(selected.distance_m)} / {selected.fare==null?'요금 정보 없음':`${selected.fare.toLocaleString()}원`}</Note><RouteStrip route={selected}/></Card>
        <View style={{borderRadius:16,overflow:'hidden'}}><JourneyMap points={[]} route={selected}/></View>
        <Text style={S.label}>상세 이동 경로</Text><Card>
          <View style={S.row}><Icon name="location-outline"/><Text style={[S.label,{flex:1}]}>{selected.from.name} 출발</Text></View>
          {selected.legs.map((leg,i)=><View key={i} style={[S.row,{alignItems:'flex-start'}]}><View style={{alignItems:'center',width:28,gap:5}}><Icon color={leg.mode==='WALK'?C.muted:'#318cef'} name={leg.mode==='WALK'?'walk-outline':leg.mode==='BUS'?'bus-outline':'train-outline'}/><View style={{width:1,backgroundColor:C.line,minHeight:32}}/></View><View style={{flex:1,gap:4,paddingBottom:14}}><Text style={S.label}>{leg.name}</Text><Note>{leg.minutes}분 / {km(leg.distance_m)}</Note>{(leg.startName||leg.endName)&&<Note>{leg.startName??'출발'} → {leg.endName??'도착'}</Note>}</View></View>)}
          <View style={S.row}><Icon name="flag-outline"/><Text style={[S.label,{flex:1}]}>{selected.to.name} 도착</Text></View>
        </Card>
        <Button title={selected.provider==='local-test'?"이 경로 선택":"이 경로 선택"} onPress={()=>{const chosen=selected;setSelected(null);onChoose(chosen);}}/>
        <Note>{selected.provider==='local-test'?'선택한 출발·도착지의 직선거리 비교 기준입니다. 실제 이동 시간과 거리는 GPS 기록으로 확정됩니다.':'TMAP 검색 결과입니다. 실제 이동 시간과 거리는 GPS 기록 후 확정됩니다.'}</Note>
      </ScrollView>}
    </SafeAreaView></SafeAreaProvider></Modal>
  </>;
}

export function RouteStrip({route}:{route:PlannedRoute}){return <View style={{flexDirection:'row',gap:3,minHeight:24}}>{route.legs.map((leg,i)=><View key={i} style={{flex:Math.max(leg.minutes,5),backgroundColor:leg.mode==='WALK'?'#80958b':leg.mode==='BUS'?'#80c83f':'#318cef',borderRadius:16,justifyContent:'center',alignItems:'center',paddingHorizontal:3,paddingVertical:6}}><Text numberOfLines={1} style={{fontSize:10,color:C.white}}>{leg.mode==='WALK'?'도보':leg.mode==='BUS'?'버스':'지하철'} {leg.minutes}분</Text></View>)}</View>;}
