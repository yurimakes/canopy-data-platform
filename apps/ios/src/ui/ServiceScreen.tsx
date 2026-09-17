import React,{useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Image,Modal,Pressable,ScrollView,Text,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import type {MeasurementProps} from './MeasurementScreen';
import {MeasurementScreen} from './MeasurementScreen';
import {TripResult} from './TripResult';
import {Button,Card,C,Fade,Field,Icon,Note,S,Stat} from './theme';
import {PlacePicker,RoutePlanner} from './RoutePlanner';
import JourneyMap from './JourneyMap';
import {gpsDistance,km,type PlannedRoute,type Profile} from '../service';
import type {GpsEvent,Summary} from '../types';
export type ServiceProps=MeasurementProps&{profile:Profile;trips:Summary[];events:GpsEvent[];route:PlannedRoute|null;
  onCollectionMode(mode:'user'|'developer'):void;onProfile(p:Profile):Promise<void>;onRoute(p:PlannedRoute|null):void;onSelect(id:string):void;preview?:boolean};
type Tab='home'|'route'|'journey'|'history'|'profile'|'missions'|'ranking'|'result';
export function ServiceScreen(p:ServiceProps){
  const [tab,setTab]=useState<Tab>(p.active?'journey':'home'),[tools,setTools]=useState(p.collectionMode==='developer'&&!!p.active),[stopOpen,setStopOpen]=useState(false),[edit,setEdit]=useState(false),[logout,setLogout]=useState(false);
  const [draft,setDraft]=useState(p.profile),[saveError,setSaveError]=useState(''),[saving,setSaving]=useState(false);
  const wasActive=useRef(!!p.active);
  const busy=!!p.active||['starting','recording','stopping'].includes(p.phase);
  useEffect(()=>{if(p.active)setTab('journey');if(wasActive.current&&!p.active&&p.phase!=='starting')setTab('result');wasActive.current=!!p.active;},[p.active,p.phase]);
  const points=p.events.map(e=>({latitude:e.lat,longitude:e.lon,name:'GPS'}));
  const measured=gpsDistance(p.events);
  const title:Record<Tab,string>={home:'CANOPY',route:'여정 계획',journey:'나의 여정',history:'지난 여정',profile:'마이페이지',missions:'이번 주 미션',ranking:'캠페인 랭킹',result:'여정 결과'};
  function choose(route:PlannedRoute|null){p.onRoute(route);setTab('journey');}
  async function save(){if(saving)return;setSaving(true);setSaveError('');try{if(!draft.nickname.trim())throw Error('닉네임을 입력해주세요.');await p.onProfile(draft);setEdit(false);}catch(e){setSaveError(String(e));}finally{setSaving(false);}}
  if(tools&&p.profile.role==='developer')return <MeasurementScreen {...p} onBack={()=>{p.onCollectionMode('user');setTools(false);}}/>;
  return <SafeAreaView style={S.root} edges={['top','bottom']}>
    <View style={[S.between,{paddingHorizontal:24,minHeight:64,backgroundColor:C.white}]}>
      <View style={S.row}><Icon name={tab==='home'?'leaf':'leaf-outline'} size={25}/><Text style={[S.heading,tab==='home'&&{letterSpacing:2}]}>{title[tab]}</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel="마이페이지" onPress={()=>setTab('profile')} style={{padding:12,backgroundColor:C.mint,borderRadius:30}}><Icon name="person-outline" size={20}/></Pressable>
    </View>
    <ScrollView key={tab} keyboardShouldPersistTaps="handled" contentContainerStyle={S.scroll} showsVerticalScrollIndicator={false}>
      <Fade key={tab}>
      <View style={S.between}><Text style={S.pill}>TEST 캠페인</Text><Text style={S.note}>{p.preview?'브라우저 화면 미리보기':'기기 내 테스트 프로필'}</Text></View>
      {tab==='home'&&<>
        <View><Note>{p.profile.nickname}님, 반가워요</Note><Text style={[S.title,{marginTop:8}]}>오늘의 이동을{ '\n'}초록빛 변화로.</Text></View>
        <Image source={require('../../assets/canopy-ui/home-landscape.png')} style={{height:165,width:'100%',borderRadius:24}} resizeMode="cover"/>
        <Card><View style={S.between}><Text style={S.heading}>오늘은 어디로 가시나요?</Text><Icon name="navigate-outline"/></View>
          <Text style={S.label}>{p.profile.home?.name??'집을 설정해주세요'} → {p.profile.work?.name??'직장을 설정해주세요'}</Text>
          <Button title={busy?'진행 중인 여정 보기':'나의 경로 찾기'} onPress={()=>setTab(busy?'journey':'route')}/>
          {(!p.profile.home||!p.profile.work)&&<Button title="집과 직장 설정" quiet onPress={()=>{setDraft(p.profile);setEdit(true);}}/>}
        </Card>
        <Card><View style={S.row}><Icon name="analytics-outline"/><Text style={S.heading}>나의 이동 기준</Text></View><Text style={S.metric}>함께 알아가는 중</Text><Note>이동 기록이 쌓이면 나에게 맞는 Baseline을 보여드릴게요. 현재는 조회 기능 연결을 준비하고 있어요.</Note></Card>
        <View style={S.row}><Pressable accessibilityRole="button" onPress={()=>setTab('missions')} style={[S.card,{flex:1,padding:18}]}><Icon name="flag-outline"/><Text style={S.label}>주간 미션</Text><Note>작은 실천의 시작</Note></Pressable><Pressable accessibilityRole="button" onPress={()=>setTab('ranking')} style={[S.card,{flex:1,padding:18}]}><Icon name="podium-outline"/><Text style={S.label}>캠페인 랭킹</Text><Note>함께 만드는 변화</Note></Pressable></View>
        <Note>실제 측정은 기존 테스트 사용자 인증으로 전송됩니다. 이 프로필은 아직 서버 회원 계정이 아닙니다.</Note>
      </>}
      {tab==='route'&&(busy?<Card><Text style={S.heading}>이미 여정을 기록 중이에요</Text><Button title="진행 중인 여정" onPress={()=>setTab('journey')}/></Card>:<RoutePlanner profile={p.profile} onChoose={choose} onFree={()=>choose(null)}/>)}
      {tab==='journey'&&<>
        <View style={S.between}><Text style={S.title}>{busy?'여정이 이어지고 있어요':'출발할 준비 됐나요?'}</Text>{busy&&<Text style={S.pill}>기록 중</Text>}</View>
        <View style={{borderRadius:24,overflow:'hidden'}}><JourneyMap points={busy?points:[]} route={p.route}/></View>
        <Card><Text style={S.heading}>{p.route?`${p.route.from.name} → ${p.route.to.name}`:'자유로운 여정'}</Text>
          {p.route&&<Note>{p.route.legs.map(l=>l.name).join(' → ')} / 예상 {p.route.minutes}분</Note>}
          <View style={S.row}><Stat label="기록 시간" value={busy?p.duration:'00:00'}/><Stat label="GPS 추정 거리" value={busy?km(measured):'0.00 km'}/></View>
          <View style={S.divider}/><View style={S.row}><Stat label="저장된 위치" value={`${busy?p.count:0}개`}/><Stat label="전송 대기" value={`${p.pending??0}개`}/></View>
          <Note>실시간 거리는 GPS로 추정한 값입니다. 최종 거리는 서버 처리 후 확정됩니다.</Note>
          {p.foregroundOnly&&<Note>Expo Go에서는 화면을 켜둔 상태로 측정해주세요.</Note>}
        </Card>
        {!!p.error&&<Card><Note error>{p.error}</Note><Button title="위치 설정 열기" quiet onPress={()=>p.onSettings?.()}/></Card>}
        {!!p.uploadError&&<Card><Text style={S.label}>기록은 휴대폰에 보관 중이에요</Text><Note>연결이 복구되면 자동 전송합니다.</Note><Button title="전송 다시 시도" quiet onPress={()=>p.onRetry?.()}/></Card>}
        {p.active&&!p.foregroundOnly&&!p.backgroundRunning&&<Button title="위치 기록 재개" quiet onPress={()=>p.onResume?.()}/>}
        <Button title={p.phase==='starting'?'위치를 준비하고 있어요':p.phase==='stopping'?'기록을 마무리하고 있어요':busy?'여정 종료':'여정 시작'} busy={p.phase==='starting'||p.phase==='stopping'} disabled={!p.ready||!!p.preview} danger={busy} onPress={()=>{if(busy)setStopOpen(true);else p.onStart();}}/>
        {!busy&&<Button title="경로 다시 선택" quiet onPress={()=>setTab('route')}/>}
      </>}
      {tab==='result'&&<>
        {p.serverTrip?.status==='ready'?<>
          <Image source={require('../../assets/canopy-ui/journey-complete-frame-4.png')} style={{width:'100%',height:150}} resizeMode="contain"/>
          <Card><TripResult trip={p.serverTrip} pending={p.feedbackPending} onFeedback={p.onFeedback}/></Card>
          <Card><View style={S.row}><Icon name="gift-outline"/><Text style={S.heading}>캐노피 토큰</Text></View><Note>보상 기능 연결 후 실제 지급 내역이 표시됩니다. 현재는 토큰이 지급되지 않습니다.</Note></Card>
        </>:p.resultTrip?<Card><Icon name={p.serverTrip?.status==='failed'?'alert-circle-outline':'hourglass-outline'} size={38}/><Text style={S.heading}>{p.serverTrip?.status==='failed'?'처리를 마치지 못했어요':(p.pending??0)>0?'이동 기록을 전송 중이에요':'서버에서 여정을 분석 중이에요'}</Text>
          {p.serverTrip?.status!=='failed'&&<ActivityIndicator color={C.green}/>}<Note>{p.serverTrip?.status==='failed'?p.serverTrip.error_message:'완료되면 이 화면에 결과와 피드백이 표시됩니다. 다른 화면을 보셔도 기록은 남아 있어요.'}</Note>
          {!!p.tripError&&<Note error>{p.tripError}</Note>}{p.serverTrip?.status==='failed'&&<Button title="처리 다시 시도" onPress={()=>p.onRetryTrip?.()}/>}
          {!!p.pending&&<Button title="전송 재시도" quiet onPress={()=>p.onRetry?.()}/>}
        </Card>:<Card><Text style={S.heading}>먼저 여정을 선택해주세요</Text><Button title="지난 여정 보기" onPress={()=>setTab('history')}/></Card>}
        <Button title="홈으로 돌아가기" quiet onPress={()=>setTab('home')}/>
      </>}
      {tab==='history'&&<><Text style={S.title}>내가 남긴 발자취</Text><Note>이 기기의 현재 프로필로 기록한 여정입니다.</Note>
        {!p.trips.length&&<Card><Icon name="footsteps-outline" size={36}/><Text style={S.heading}>첫 여정을 기다리고 있어요</Text><Button title="여정 준비하기" onPress={()=>setTab('route')}/></Card>}
        {p.trips.map(t=><Pressable key={t.trip_id} accessibilityRole="button" disabled={busy} onPress={()=>{p.onSelect(t.trip_id);setTab('result');}} style={S.card}><View style={S.between}><Text style={S.heading}>{new Date(t.started_at).toLocaleDateString('ko-KR')}</Text><Icon name="chevron-forward" size={18}/></View><Note>{new Date(t.started_at).toLocaleTimeString('ko-KR')} / GPS {t.gps_count}개</Note><Text style={S.pill}>{t.status==='recording'?'기록 중':t.status==='interrupted'?'기록 중단':'기록 종료'}</Text></Pressable>)}
      </>}
      {(tab==='missions'||tab==='ranking')&&<>
        <Text style={S.title}>{tab==='missions'?'작은 도전,\n일상 속 큰 변화.':'함께라서\n더 멀리 갈 수 있어요.'}</Text>
        <View style={S.row}><Text style={S.pill}>TEST 캠페인</Text><Text style={S.note}>서비스 준비 중</Text></View>
        <Card><Icon name={tab==='missions'?'flag-outline':'podium-outline'} size={48}/><Text style={S.heading}>{tab==='missions'?'나에게 맞는 미션을 준비하고 있어요':'우리의 변화를 모으고 있어요'}</Text><Note>{tab==='missions'?'미션 기능이 연결되면 미션 선택, 진행률과 보상을 이곳에서 확인할 수 있어요.':'랭킹 기능이 연결되면 캠페인 내 사용자와 부서 순위를 확인할 수 있어요.'}</Note><Button title="여정 기록하러 가기" onPress={()=>setTab(busy?'journey':'route')}/></Card>
      </>}
      {tab==='profile'&&<>
        <View style={[S.row,{paddingVertical:16}]}><View style={{padding:22,borderRadius:50,backgroundColor:C.mint}}><Icon name="person" size={30}/></View><View style={{flex:1,gap:6}}><Text style={S.heading}>{p.profile.nickname}</Text><Note>{p.profile.email}</Note><Text style={S.pill}>테스트 캠페인 소속</Text></View></View>
        <Card><Text style={S.heading}>나의 출퇴근 장소</Text><Note>집: {p.profile.home?.name??'아직 설정하지 않았어요'}</Note><Note>직장: {p.profile.work?.name??'아직 설정하지 않았어요'}</Note><Button title="프로필과 장소 수정" quiet disabled={busy} onPress={()=>{setDraft(p.profile);setSaveError('');setEdit(true);}}/></Card>
        <Card><View style={S.row}><Icon name="wallet-outline"/><Text style={S.heading}>캐노피 토큰</Text></View><Note>보상 서비스 연결 준비 중</Note></Card>
        {([['지난 여정','history','time-outline'],['나의 미션','missions','flag-outline'],['캠페인 랭킹','ranking','podium-outline']] as const).map(([label,target,icon])=><Pressable key={target} accessibilityRole="button" onPress={()=>setTab(target)} style={[S.card,S.between,{padding:18}]}><View style={S.row}><Icon name={icon}/><Text style={S.label}>{label}</Text></View><Icon name="chevron-forward" size={18}/></Pressable>)}
        {p.profile.role==='developer'&&<Button title="개발자 GPS 수집 도구" quiet onPress={()=>{p.onCollectionMode('developer');setTools(true);}}/>}
        <Button title="로그아웃" quiet disabled={busy} onPress={()=>setLogout(true)}/><Note>프로필은 이 기기에만 저장됩니다. 측정 중에는 로그아웃할 수 없어요.</Note>
      </>}
      </Fade>
    </ScrollView>
    {busy&&tab!=='journey'&&<Pressable accessibilityRole="button" onPress={()=>setTab('journey')} style={{padding:14,backgroundColor:C.mint,alignItems:'center'}}><Text style={S.link}>진행 중인 여정으로 돌아가기</Text></Pressable>}
    <View style={{flexDirection:'row',backgroundColor:C.white,borderTopWidth:1,borderColor:C.line,paddingVertical:10}}>
      {([['home','home-outline','홈'],['route','navigate-outline','여정'],['missions','flag-outline','미션'],['ranking','podium-outline','랭킹'],['profile','person-outline','마이']] as const).map(([target,icon,label])=><Pressable key={target} accessibilityRole="tab" accessibilityState={{selected:tab===target}} accessibilityLabel={label} onPress={()=>setTab(target==='route'&&busy?'journey':target)} style={{flex:1,alignItems:'center',gap:5,paddingVertical:8}}><Icon name={icon} color={tab===target?C.green:C.muted}/><Text style={{fontSize:11,color:tab===target?C.green:C.muted,fontWeight:'600'}}>{label}</Text></Pressable>)}
    </View>
    <Modal visible={stopOpen||logout} transparent animationType="fade" onRequestClose={()=>{setStopOpen(false);setLogout(false);}}><View style={{flex:1,backgroundColor:'#102e2570',justifyContent:'center',padding:24}}><Card><Text style={S.heading}>{stopOpen?'여정을 종료할까요?':'로그아웃할까요?'}</Text><Note>{stopOpen?'GPS 기록을 멈추고 서버에서 결과를 처리합니다. 아직 보내지 못한 기록도 보관됩니다.':'저장한 프로필과 이동 기록은 이 기기에 남아 있습니다.'}</Note><Button title={stopOpen?'여정 종료':'로그아웃'} danger onPress={()=>{if(stopOpen){setStopOpen(false);p.onStop();}else{setLogout(false);p.onBack();}}}/><Button title="취소" quiet onPress={()=>{setStopOpen(false);setLogout(false);}}/></Card></View></Modal>
    <Modal visible={edit} animationType="slide" onRequestClose={()=>setEdit(false)}><SafeAreaView style={S.root}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={S.scroll}><View style={S.between}><Text style={S.heading}>나의 프로필</Text><Button title="닫기" quiet onPress={()=>setEdit(false)}/></View><Field label="닉네임" value={draft.nickname} onChangeText={nickname=>setDraft({...draft,nickname})} maxLength={30}/><PlacePicker title="집" value={draft.home} onPick={home=>setDraft({...draft,home})}/><PlacePicker title="직장" value={draft.work} onPick={work=>setDraft({...draft,work})}/><Note>출근은 집 → 직장, 퇴근은 직장 → 집으로 바꿔 검색할 수 있어요. 다른 목적지도 선택할 수 있습니다.</Note>{!!saveError&&<Note error>{saveError}</Note>}<Button title="저장하기" busy={saving} onPress={()=>void save()}/></ScrollView></SafeAreaView></Modal>
  </SafeAreaView>;
}
