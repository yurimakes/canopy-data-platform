import {CanopyMascot} from './CanopyMascot';
import React,{useEffect,useRef,useState} from 'react';
import {ActivityIndicator,ImageBackground,Modal,Pressable,ScrollView,Text,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import type {MeasurementProps} from './MeasurementScreen';
import {MeasurementScreen} from './MeasurementScreen';
import {TripResult} from './TripResult';
import {Button,Card,C,Fade,Field,Icon,Note,S,Stat} from './theme';
import {PlacePicker,RoutePlanner,RouteStrip} from './RoutePlanner';
import JourneyMap from './JourneyMap';
import {BaselinePanel,type BaselineView,MissionPanel,RankingPanel,RewardPanel,PanelPreview,type RemotePanel,type MissionView,type RankingView,type RewardView} from './CommunityPanels';
import {gpsDistance,km,journeyStage,type PlannedRoute,type Profile} from '../service';
import type {GpsEvent,Summary} from '../types';
export type ServiceProps=MeasurementProps&{profile:Profile;trips:Summary[];events:GpsEvent[];route:PlannedRoute|null;
  onCollectionMode(mode:'user'|'developer'):void;onProfile(p:Profile):Promise<void>;onRoute(p:PlannedRoute|null):void;onSelect(id:string):void;preview?:boolean;baseline?:RemotePanel<BaselineView>;missions?:RemotePanel<MissionView>;ranking?:RemotePanel<RankingView>;rewards?:RemotePanel<RewardView>;onRefreshCommunity?:()=>void};
type Tab='home'|'route'|'journey'|'history'|'profile'|'missions'|'ranking'|'result'|'rewards'|'preview'|'baseline'|'tripdetail'|'notifications';
export function ServiceScreen(p:ServiceProps){
  const [tab,setTab]=useState<Tab>(p.active?'journey':'home'),[tools,setTools]=useState(p.collectionMode==='developer'),[stopOpen,setStopOpen]=useState(false),[edit,setEdit]=useState(false),[logout,setLogout]=useState(false);
  const [direction,setDirection]=useState<'outbound'|'return'>('outbound');
  const [draft,setDraft]=useState(p.profile),[saveError,setSaveError]=useState(''),[saving,setSaving]=useState(false);
  const wasActive=useRef(!!p.active);
  const busy=!!p.active||['starting','recording','stopping'].includes(p.phase);
  useEffect(()=>{if(p.active)setTab('journey');if(wasActive.current&&!p.active&&p.phase!=='starting')setTab('result');wasActive.current=!!p.active;},[p.active,p.phase]);
  const points=p.events.map(e=>({latitude:e.lat,longitude:e.lon,name:'GPS'}));
  const measured=gpsDistance(p.events);
  const stage=journeyStage(p.pending,p.serverTrip?.status,p.serverTrip?.error_message);
  const [historyFilter,setHistoryFilter]=useState<'all'|'user'|'developer'>('all');
  const filteredTrips=p.trips.filter(t=>historyFilter==='all'||(t.collection_mode??'developer')===historyFilter);
  const arrival=p.route&&p.events.length>0&&Math.hypot((p.events.at(-1)!.lat-p.route.to.latitude)*111000,(p.events.at(-1)!.lon-p.route.to.longitude)*88000)<100;
  const title:Record<Tab,string>={home:'Canopy',route:direction==='outbound'?'출근 길찾기':'퇴근 길찾기',journey:'나의 여정',history:'지난 여정',profile:'마이페이지',missions:'미션',ranking:'랭킹',result:'여정 결과',rewards:'리워드',preview:'화면 상태 미리보기',baseline:'나의 이동 기준',tripdetail:'트립 상세 내역',notifications:'알림'};
  function choose(route:PlannedRoute|null){p.onRoute(route);setTab('journey');}
  async function save(){if(saving)return;setSaving(true);setSaveError('');try{if(!draft.nickname.trim())throw Error('닉네임을 입력해주세요.');await p.onProfile(draft);setEdit(false);}catch(e){setSaveError(String(e));}finally{setSaving(false);}}
  if(tools&&p.profile.role==='developer')return <MeasurementScreen {...p} onBack={()=>{p.onCollectionMode('user');setTools(false);}}/>;
  return <SafeAreaView style={S.root} edges={['top','bottom']}>
    <View style={[S.between,{paddingHorizontal:20,minHeight:58,backgroundColor:tab==='home'?C.paper:C.white}]}>
      <View style={S.row}>{tab==='home'?<Icon name="leaf" size={25}/>:!['missions','rewards','ranking','profile'].includes(tab)?<Pressable accessibilityRole="button" accessibilityLabel="뒤로" onPress={()=>setTab('home')} style={{padding:8}}><Icon name="arrow-back" size={21}/></Pressable>:null}<Text style={[S.heading,tab==='home'&&{fontSize:24,color:C.green}]}>{title[tab]}</Text></View>
      <Pressable accessibilityRole="button" accessibilityLabel={tab==='home'?'알림':'프로필 설정'} onPress={()=>{if(tab==='home')setTab('notifications');else{setDraft(p.profile);setEdit(true);}}} style={{padding:10}}><Icon name={tab==='home'?'notifications-outline':'settings-outline'} size={21} color={C.deep}/></Pressable>
    </View>
    <ScrollView key={tab} keyboardShouldPersistTaps="handled" contentContainerStyle={tab==='home'?{flexGrow:1}:S.scroll} showsVerticalScrollIndicator={false}>
      {tab==='home'?<ImageBackground source={require('../../assets/canopy-ui/home-park.png')} resizeMode="cover" style={{flex:1,minHeight:560,backgroundColor:'#f1faf5'}} imageStyle={{width:'100%',height:'100%'}}>
        <View style={{flex:1,padding:26,paddingTop:34,justifyContent:'space-between'}}>
          <View style={{gap:14}}><Text style={[S.title,{fontSize:29,lineHeight:41}]}>오늘도{ '\n'}지구를 위한{ '\n'}좋은 선택을 해볼까요?</Text><Text style={[S.note,{color:C.deep,lineHeight:23}]}>당신의 작은 이동이{ '\n'}더 큰 변화를 만들어요</Text></View>
          <CanopyMascot animated={false} height={250}/>
          <View style={{gap:12,paddingBottom:10}}>{([['outbound','출근 길찾기','leaf-outline'],['return','퇴근 길찾기','home-outline']] as const).map(([value,label,icon])=><Pressable key={value} accessibilityRole="button" onPress={()=>{setDirection(value);setTab(busy?'journey':'route');}} style={[S.between,{backgroundColor:C.white,borderRadius:30,paddingHorizontal:22,minHeight:57,boxShadow:'0 4px 18px #174c3910'}]}><View style={S.row}><Icon name={icon}/><Text style={[S.label,{fontSize:16}]}>{busy?'진행 중인 여정 보기':label}</Text></View><Icon name="chevron-forward" size={17}/></Pressable>)}</View>
        </View>
      </ImageBackground>:<Fade key={tab}>
      {tab==='route'&&(busy?<Card><Text style={S.heading}>이미 여정을 기록 중이에요</Text><Button title="진행 중인 여정" onPress={()=>setTab('journey')}/></Card>:<RoutePlanner direction={direction} profile={p.profile} onChoose={choose} onFree={()=>choose(null)}/>)}
      {tab==='journey'&&<>
        <View style={[S.card,S.between,{zIndex:1}]}><View><Text style={S.heading}>{busy?'지금 이동 중이에요!':'출발할 준비 됐나요?'}</Text><Note>{busy?'현재 위치를 기록하고 있어요':'선택한 경로를 확인해주세요'}</Note></View><Icon name="navigate-circle-outline" size={30}/></View>
        <View style={{marginHorizontal:-20,marginTop:-28}}><JourneyMap height={400} points={busy?points:[]} route={p.route}/></View>
        <Card><Text style={S.heading}>{p.route?`${p.route.from.name} → ${p.route.to.name}`:'자유로운 여정'}</Text>
          {p.route&&<><Note>선택한 경로 / 예상 {p.route.minutes}분</Note><RouteStrip route={p.route}/></>}
          <View style={S.row}><Stat label="기록 시간" value={busy?p.duration:'00:00'}/><Stat label="GPS 추정 거리" value={busy?km(measured):'0.00 km'}/></View>
          <View style={S.divider}/><View style={S.row}><Stat label="저장된 위치" value={`${busy?p.count:0}개`}/><Stat label="전송 대기" value={`${p.pending??0}개`}/></View>
          <Note>실시간 거리는 GPS로 추정한 값입니다. 최종 거리는 서버 처리 후 확정됩니다.</Note>
          {arrival&&p.active&&<Note>목적지 근처에 도착했어요. 이동을 마쳤다면 여정 종료를 눌러주세요.</Note>}
          {p.foregroundOnly&&<Note>Expo Go에서는 화면을 켜둔 상태로 측정해주세요.</Note>}
        </Card>
        {!!p.error&&<Card><Note error>{p.error}</Note><Button title="위치 설정 열기" quiet onPress={()=>p.onSettings?.()}/></Card>}
        {!!p.uploadError&&<Card><Text style={S.label}>기록은 휴대폰에 보관 중이에요</Text><Note>연결이 복구되면 자동 전송합니다.</Note><Button title="전송 다시 시도" quiet onPress={()=>p.onRetry?.()}/></Card>}
        {p.active&&!p.foregroundOnly&&!p.backgroundRunning&&<Button title="위치 기록 재개" quiet onPress={()=>p.onResume?.()}/>}

        {!busy&&<Button title="경로 다시 선택" quiet onPress={()=>setTab('route')}/>}
      </>}
      {tab==='notifications'&&<Card><Icon name="notifications-outline" size={32}/><Text style={S.heading}>새로운 알림이 없어요</Text><Note>알림 기능 연결 후 여정과 미션 소식을 확인할 수 있어요.</Note></Card>}
      {tab==='tripdetail'&&p.serverTrip?.status==='ready'&&<Card><TripResult trip={p.serverTrip} pending={p.feedbackPending} onFeedback={p.onFeedback}/></Card>}
      {tab==='result'&&<>
        {p.serverTrip?.status==='ready'?<>
          <CanopyMascot pose="complete" height={180}/><Text style={[S.heading,{textAlign:'center',fontSize:23}]}>여정 완료!</Text>
          <Text style={[S.note,{textAlign:'center'}]}>오늘의 이동 기록이 저장됐어요</Text>
          {p.serverTrip.is_mock&&<Note>테스트용 예시 결과입니다. 실제 GPS 분석 결과가 아닙니다.</Note>}
          <Card><View style={S.row}><Stat label="이동 거리" value={p.serverTrip.confirmed_trip?km(p.serverTrip.confirmed_trip.total_distance_m):'—'}/><Stat label="소요 시간" value={p.serverTrip.ended_at?`${Math.max(0,Math.round((Date.parse(p.serverTrip.ended_at)-Date.parse(p.serverTrip.started_at))/60000))}분`:'—'}/><Stat label="탄소 배출량" value={p.serverTrip.confirmed_trip?`${p.serverTrip.confirmed_trip.total_carbon_kg.toFixed(2)} kg`:'—'}/></View></Card>
          <Button title="상세 내역과 피드백" onPress={()=>setTab('tripdetail')}/>
          <Card><View style={S.row}><Icon name="gift-outline"/><Text style={S.heading}>캐노피 토큰</Text></View><Note>보상 기능 연결 후 실제 지급 내역이 표시됩니다. 현재는 토큰이 지급되지 않습니다.</Note><Button title="토큰 내역 보기" quiet onPress={()=>setTab('rewards')}/></Card>
        </>:(p.resultTrip||p.tripId)?<Card><Icon name="leaf-outline" size={42}/><Icon name={stage.failed?'alert-circle-outline':'hourglass-outline'} size={38}/><Text style={S.heading}>{stage.title}</Text>
          {!stage.failed&&<ActivityIndicator color={C.green}/>}<Note>{stage.detail}</Note>
          {['위치 전송','서버 분석','결과 확인'].map((label,i)=><View key={label} style={S.row}><Icon name={i<stage.step?'checkmark-circle':i===stage.step?'radio-button-on':'ellipse-outline'} color={i<=stage.step?C.green:C.muted}/><Text style={S.label}>{label}</Text></View>)}
          {!!p.tripError&&<Note error>{p.tripError}</Note>}
          {(stage.failed||!!p.tripError)&&<Button title="처리 다시 시도" onPress={()=>p.onRetryTrip?.()}/>}
          {!!p.pending&&<Button title="전송 재시도" quiet onPress={()=>p.onRetry?.()}/>}
        </Card>:<Card><Text style={S.heading}>먼저 여정을 선택해주세요</Text><Button title="지난 여정 보기" onPress={()=>setTab('history')}/></Card>}
        <Button title="홈으로 돌아가기" quiet onPress={()=>setTab('home')}/>
      </>}
      {tab==='history'&&<><Text style={S.title}>내가 남긴 발자취</Text><Note>이 기기의 현재 프로필로 기록한 여정입니다.</Note>
        <View style={S.row}>{([['all','전체'],['user','사용자'],['developer','개발자']] as const).filter(([id])=>p.profile.role==='developer'||id==='all').map(([id,label])=><Button key={id} title={label} quiet={historyFilter!==id} onPress={()=>setHistoryFilter(id)}/>)}</View>
        {!filteredTrips.length&&<Card><Icon name="footsteps-outline" size={36}/><Text style={S.heading}>첫 여정을 기다리고 있어요</Text><Button title="여정 준비하기" onPress={()=>setTab('route')}/></Card>}
        {filteredTrips.map(t=><Pressable key={t.trip_id} accessibilityRole="button" disabled={busy} onPress={()=>{p.onSelect(t.trip_id);setTab('result');}} style={S.card}><View style={S.between}><Text style={S.heading}>{new Date(t.started_at).toLocaleDateString('ko-KR')}</Text><Icon name="chevron-forward" size={18}/></View><Note>{new Date(t.started_at).toLocaleTimeString('ko-KR')} / GPS {t.gps_count}개</Note><Text style={S.pill}>{t.status==='recording'?'기록 중':t.status==='interrupted'?'기록 중단':'기록 종료'}</Text></Pressable>)}
      </>}
      {tab==='baseline'&&<BaselinePanel value={p.baseline} onRetry={p.onRefreshCommunity}/>}
      {tab==='missions'&&<MissionPanel value={p.missions} onRetry={p.onRefreshCommunity}/>}
      {tab==='ranking'&&<RankingPanel value={p.ranking} onRetry={p.onRefreshCommunity}/>}
      {tab==='rewards'&&<RewardPanel value={p.rewards} onRetry={p.onRefreshCommunity}/>}
      {tab==='preview'&&p.profile.role==='developer'&&<PanelPreview/>}
      {tab==='profile'&&<>
        <View style={[S.row,{paddingVertical:16}]}><View accessibilityLabel="프로필 아바타" style={{width:72,height:72,borderRadius:36,backgroundColor:'#dcefe6',alignItems:'center',justifyContent:'center',borderWidth:3,borderColor:C.white}}><Text style={{fontSize:28,fontWeight:'700',color:C.deep}}>{Array.from(p.profile.nickname.trim())[0]??'C'}</Text></View><View style={{flex:1,gap:6}}><Text style={S.heading}>{p.profile.nickname}</Text><Note>{p.profile.email}</Note><Text style={S.pill}>테스트 캠페인 소속</Text></View></View>
        <Card><Text style={S.label}>나의 탄소 절감량</Text><Text style={[S.metric,{color:C.green}]}>— kg</Text><Note>주간 분석 결과 연결 후 표시됩니다.</Note><Pressable accessibilityRole="button" onPress={()=>setTab('baseline')}><Text style={S.link}>나의 이동 기준 보기</Text></Pressable></Card>
        <View style={S.row}>{([['집',p.profile.home,'home-outline'],['직장',p.profile.work,'business-outline']] as const).map(([label,place,icon])=><Pressable key={label} accessibilityRole="button" disabled={busy} onPress={()=>{setDraft(p.profile);setSaveError('');setEdit(true);}} style={[S.card,{flex:1,padding:12}]}><View style={S.row}><Icon name={icon}/><View style={{flex:1}}><Text style={S.note}>{label}</Text><Text numberOfLines={2} style={S.label}>{place?.name??'장소 설정'}</Text></View></View></Pressable>)}</View>

        {([['이동 기록','history','time-outline'],['리워드 내역','rewards','gift-outline'],['나의 미션','missions','flag-outline'],['캠페인 랭킹','ranking','podium-outline']] as const).map(([label,target,icon])=><Pressable key={target} accessibilityRole="button" onPress={()=>setTab(target)} style={[S.between,{paddingVertical:14,borderBottomWidth:1,borderColor:C.line}]}><View style={S.row}><Icon name={icon}/><Text style={S.label}>{label}</Text></View><Icon name="chevron-forward" size={18}/></Pressable>)}
        {p.profile.role==='developer'&&<><Button title="개발자 GPS 수집 도구" quiet disabled={busy} onPress={()=>{p.onCollectionMode('developer');setTools(true);}}/><Button title="화면 상태 미리보기" quiet onPress={()=>setTab('preview')}/></>}
        <Button title="로그아웃" quiet disabled={busy} onPress={()=>setLogout(true)}/><Note>프로필은 계정에 저장됩니다. 측정 중에는 로그아웃할 수 없어요.</Note>
      </>}
      </Fade>}
    </ScrollView>
    {tab==='journey'&&<View style={{paddingHorizontal:20,paddingVertical:10,backgroundColor:C.white}}><Button title={p.phase==='starting'?'위치를 준비하고 있어요':p.phase==='stopping'?'기록을 마무리하고 있어요':busy?'여정 종료':'여정 시작'} busy={p.phase==='starting'||p.phase==='stopping'} disabled={!p.ready||!!p.preview} onPress={()=>{if(busy)setStopOpen(true);else p.onStart();}}/></View>}
    {busy&&tab!=='journey'&&<Pressable accessibilityRole="button" onPress={()=>setTab('journey')} style={{padding:14,backgroundColor:C.mint,alignItems:'center'}}><Text style={S.link}>진행 중인 여정으로 돌아가기</Text></Pressable>}
    <View style={{flexDirection:'row',backgroundColor:C.white,borderTopWidth:1,borderColor:C.line,paddingVertical:10}}>
      {([['home','home-outline','홈'],['missions','checkmark-circle-outline','미션'],['rewards','gift-outline','리워드'],['ranking','trophy-outline','랭킹'],['profile','person-outline','마이페이지']] as const).map(([target,icon,label])=><Pressable key={target} accessibilityRole="tab" accessibilityState={{selected:tab===target}} accessibilityLabel={label} onPress={()=>setTab(target)} style={{flex:1,alignItems:'center',gap:5,paddingVertical:8}}><Icon name={icon} color={tab===target?C.green:C.muted}/><Text style={{fontSize:11,color:tab===target?C.green:C.muted,fontWeight:'600'}}>{label}</Text></Pressable>)}
    </View>
    <Modal visible={stopOpen||logout} transparent animationType="fade" onRequestClose={()=>{setStopOpen(false);setLogout(false);}}><View style={{flex:1,backgroundColor:'#102e2570',justifyContent:'center',padding:24}}><Card><Text style={S.heading}>{stopOpen?'여정을 종료할까요?':'로그아웃할까요?'}</Text><Note>{stopOpen?'GPS 기록을 멈추고 서버에서 결과를 처리합니다. 아직 보내지 못한 기록도 보관됩니다.':'저장한 프로필과 이동 기록은 이 기기에 남아 있습니다.'}</Note><Button title={stopOpen?'여정 종료':'로그아웃'} danger onPress={()=>{if(stopOpen){setStopOpen(false);p.onStop();}else{setLogout(false);p.onBack();}}}/><Button title="취소" quiet onPress={()=>{setStopOpen(false);setLogout(false);}}/></Card></View></Modal>
    <Modal visible={edit} animationType="slide" onRequestClose={()=>setEdit(false)}><SafeAreaView style={S.root}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={S.scroll}><View style={S.between}><Text style={S.heading}>나의 프로필</Text><Button title="닫기" quiet onPress={()=>setEdit(false)}/></View><Field label="닉네임" value={draft.nickname} onChangeText={nickname=>setDraft({...draft,nickname})} maxLength={30}/><PlacePicker title="집" value={draft.home} onPick={home=>setDraft({...draft,home})}/><PlacePicker title="직장" value={draft.work} onPick={work=>setDraft({...draft,work})}/><Note>출근은 집 → 직장, 퇴근은 직장 → 집으로 바꿔 검색할 수 있어요. 다른 목적지도 선택할 수 있습니다.</Note>{!!saveError&&<Note error>{saveError}</Note>}<Button title="저장하기" busy={saving} onPress={()=>void save()}/></ScrollView></SafeAreaView></Modal>
  </SafeAreaView>;
}
