import {IllustratedIcon,type ArtName} from './IllustratedIcon';
import Text from './AppText';
import {ProfileAvatar,chooseProfilePhoto} from './ProfileAvatar';
import {Eyebrow} from './DesignPrimitives';
import {NotificationPanel,type NotificationView} from './NotificationPanel';
import {JourneyHistory} from './JourneyHistory';
import {HomeDashboard} from './HomeDashboard';
import {ActiveJourney} from './ActiveJourney';
import {JourneyInfoPanel} from './JourneyInfoPanel';
import {JourneyComplete} from './RewardExperience';
import {CanopyMascot} from './CanopyMascot';
import Constants from 'expo-constants';
import {LivePrediction,LocalWeekly} from './LocalTools';
import React,{useEffect,useRef,useState} from 'react';
import {ActivityIndicator,Image,ImageBackground,Modal,Pressable,ScrollView,View} from 'react-native';
import {SafeAreaView,SafeAreaProvider} from 'react-native-safe-area-context';
import type {MeasurementProps} from './MeasurementScreen';
import {MeasurementScreen} from './MeasurementScreen';
import {TripResult} from './TripResult';
import {Button,Card,C,Fade,Field,Icon,Note,S,Stat} from './theme';
import {PlacePicker,RoutePlanner,RouteStrip} from './RoutePlanner';
import JourneyMap from './JourneyMap';
import {BaselinePanel,type BaselineView,MissionPanel,RankingPanel,RewardPanel,PanelPreview,type RemotePanel,type MissionView,type RankingView,type RewardView} from './CommunityPanels';
import {gpsDistance,km,journeyStage,type PlannedRoute,type Profile} from '../service';
import type {GpsEvent,Summary} from '../types';
export type ServiceProps=MeasurementProps&{profile:Profile;trips:Summary[];events:GpsEvent[];route:PlannedRoute|null;weeklyStatus?:{state:string;message:string};
  onCollectionMode(mode:'user'|'developer'):void;onProfile(p:Profile):Promise<void>;onRoute(p:PlannedRoute|null):void;onSelect(id:string):void;preview?:boolean;notifications?:RemotePanel<NotificationView>;baseline?:RemotePanel<BaselineView>;missions?:RemotePanel<MissionView>;ranking?:RemotePanel<RankingView>;rewards?:RemotePanel<RewardView>;onRefreshCommunity?:()=>void};
type Tab='home'|'route'|'journey'|'history'|'profile'|'missions'|'ranking'|'result'|'rewards'|'preview'|'baseline'|'tripdetail'|'notifications';
function JourneyRecovery({p}:{p:ServiceProps}){
  return <>{!!p.error&&<Card><Note error>{p.error}</Note>{p.onSettings&&<Button title="위치 설정 열기" quiet onPress={p.onSettings}/>}</Card>}
    {!!p.uploadError&&<Card><Note>연결이 끊겨 기록을 기기에 보관하고 있어요. 연결되면 다시 전송합니다.</Note><Button title="전송 다시 시도" quiet onPress={()=>p.onRetry?.()}/></Card>}
    {p.active&&!p.foregroundOnly&&!p.backgroundRunning&&<Button title="위치 기록 재개" quiet onPress={()=>p.onResume?.()}/>}
    {p.active&&p.foregroundOnly&&<Note>이 환경에서는 화면을 켜고 앱을 열어둬야 위치를 기록할 수 있어요.</Note>}</>;
}
export function ServiceScreen(p:ServiceProps){
  const [tab,updateTab]=useState<Tab>(p.active?'journey':'home'),[tools,setTools]=useState(p.collectionMode==='developer'),[stopOpen,setStopOpen]=useState(false),[edit,setEdit]=useState(false),[logout,setLogout]=useState(false);
  const navigation=useRef<Tab[]>([]),currentTab=useRef<Tab>(tab);
  function setTab(next:Tab){if(busy&&next!=='journey')return;if(currentTab.current===next)return;navigation.current.push(currentTab.current);if(navigation.current.length>50)navigation.current.shift();currentTab.current=next;updateTab(next);}
  function goBack(){if(busy)return;const next=navigation.current.pop()??'home';currentTab.current=next;updateTab(next);}
  const [direction,setDirection]=useState<'outbound'|'return'>('outbound');
  const [draft,setDraft]=useState(p.profile),[saveError,setSaveError]=useState(''),[saving,setSaving]=useState(false);
  const wasActive=useRef(!!p.active);
  const busy=!!p.active||['starting','recording','stopping'].includes(p.phase);
  useEffect(()=>{if(busy)setTab('journey');if(p.active)wasActive.current=true;if(wasActive.current&&!busy){setTab('result');wasActive.current=false;}},[p.active,busy]);
  const points=p.events.map(e=>({latitude:e.lat,longitude:e.lon,name:'GPS'}));
  const measured=gpsDistance(p.events);
  const stage=journeyStage(p.pending,p.serverTrip?.status,p.serverTrip?.error_message);
  const arrival=p.route&&p.events.length>0&&Math.hypot((p.events.at(-1)!.lat-p.route.to.latitude)*111000,(p.events.at(-1)!.lon-p.route.to.longitude)*88000)<100;
  const title:Record<Tab,string>={home:'Canopy',route:direction==='outbound'?'출근 길찾기':'퇴근 길찾기',journey:'나의 여정',history:'지난 여정',profile:'내 정보',missions:'미션',ranking:'랭킹',result:'여정 결과',rewards:'지갑',preview:'화면 상태 미리보기',baseline:'나의 이동 기준',tripdetail:'이동 상세',notifications:'알림'};
  function choose(route:PlannedRoute|null){p.onRoute(route);setTab('journey');}
  async function save(){if(saving)return;setSaving(true);setSaveError('');try{if(!draft.nickname.trim())throw Error('닉네임을 입력해주세요.');await p.onProfile(draft);setEdit(false);}catch(e){setSaveError(String(e));}finally{setSaving(false);}}
  if(tools&&p.profile.role==='developer')return <MeasurementScreen {...p} onBack={()=>{p.onCollectionMode('user');setTools(false);}}/>;
  return <SafeAreaView style={[S.root,{minHeight:0}]} edges={['top','left','right']}>
    <View style={[S.between,{flexShrink:0,paddingHorizontal:20,minHeight:58,backgroundColor:C.paper}]}>
      <View style={S.row}>{tab==='home'?<Image accessibilityLabel="CANOPY" source={require('../../assets/canopy-ui/canopy-wordmark-v2.png')} resizeMode="contain" style={{width:145,height:46}}/>:!busy&&navigation.current.length>0?<Pressable accessibilityRole="button" accessibilityLabel="뒤로" onPress={goBack} style={{padding:8}}><Icon name="arrow-back" size={21}/></Pressable>:null}{tab!=='home'&&<Text style={S.heading}>{title[tab]}</Text>}</View>
      {!busy&&<Pressable accessibilityRole="button" accessibilityLabel={tab==='home'?'알림':'프로필 설정'} onPress={()=>{if(tab==='home')setTab('notifications');else{setDraft(p.profile);setEdit(true);}}} style={{padding:10}}><Icon name={tab==='home'?'notifications-outline':'settings-outline'} size={21} color={C.deep}/></Pressable>}
    </View>
    {tab==='journey'&&busy?<View style={{flex:1,minHeight:0,paddingHorizontal:12,paddingTop:8}}><ActiveJourney p={p} direction={direction} showInfo={false}/><ScrollView style={{flexGrow:0,flexShrink:1,maxHeight:76}}><JourneyRecovery p={p}/></ScrollView></View>:<ScrollView key={tab} style={{flex:1,minHeight:0}} scrollEnabled={tab!=='journey'||!busy} keyboardShouldPersistTaps="handled" contentContainerStyle={tab==='home'?{flexGrow:1}:tab==='journey'?{padding:12,gap:12}:S.scroll} showsVerticalScrollIndicator={false}>
      {tab==='home'&&!p.preview&&Constants.expoConfig?.extra?.localOnly===true&&<View style={{padding:12,backgroundColor:C.mint}}><Text style={S.note}>로컬 테스트 · PC에서 처리 · Azure 미사용</Text></View>}
      {!!p.weeklyStatus&&['home','baseline','missions','ranking'].includes(tab)&&<Note error>{p.weeklyStatus.message}</Note>}
      {['home','profile','route'].includes(tab)&&[p.profile.home,p.profile.work].some(place=>place?.address?.includes('행정동 중심점'))&&<Card><Note error>집·직장이 행정동 중심점으로 저장돼 있어요. 출퇴근을 정확히 확인하려면 프로필에서 실제 위치로 다시 설정해주세요.</Note><Button title="출퇴근 장소 수정" quiet onPress={()=>{setDraft(p.profile);setEdit(true);}}/></Card>}

      {tab==='home'?<><HomeDashboard p={p} busy={busy} onRoute={d=>{setDirection(d);setTab(busy?'journey':'route');}} onResult={()=>setTab('result')} onBaseline={()=>setTab('baseline')} onRewards={()=>setTab('rewards')} onMissions={()=>setTab('missions')}/>{p.profile.role==='developer'&&<View style={{padding:20}}><LocalWeekly/></View>}</>:<Fade key={tab}>
      {tab==='route'&&(busy?<Card><Text style={S.heading}>이미 여정을 기록 중이에요</Text><Button title="진행 중인 여정" onPress={()=>setTab('journey')}/></Card>:<RoutePlanner baseline={p.baseline} direction={direction} profile={p.profile} onChoose={choose} onFree={()=>choose(null)}/>)}
      {tab==='journey'&&<>
        <ActiveJourney p={p} direction={direction}/>
        {!!p.error&&<Card><Note error>{p.error}</Note><Button title="위치 설정 열기" quiet onPress={()=>p.onSettings?.()}/></Card>}
        {!!p.uploadError&&<Card><Text style={S.label}>기록은 휴대폰에 보관 중이에요</Text><Note>연결이 복구되면 자동 전송합니다.</Note><Button title="전송 다시 시도" quiet onPress={()=>p.onRetry?.()}/></Card>}
        {p.active&&!p.foregroundOnly&&!p.backgroundRunning&&<Button title="위치 기록 재개" quiet onPress={()=>p.onResume?.()}/>}

        {!busy&&<Button title="경로 다시 선택" quiet onPress={()=>setTab('route')}/>}
      </>}
      {tab==='notifications'&&<NotificationPanel value={p.notifications} onOpen={setTab} onRefresh={p.onRefreshCommunity}/>}
      {tab==='tripdetail'&&p.serverTrip?.status==='ready'&&<Card><TripResult trip={p.serverTrip} pending={p.feedbackPending} onFeedback={p.onFeedback}/></Card>}
      {tab==='result'&&<>
        {p.serverTrip?.status==='ready'?<JourneyComplete trip={p.serverTrip} onDetail={()=>setTab('tripdetail')} onWallet={()=>{p.onRefreshCommunity?.();setTab('rewards');}}/>:(p.resultTrip||p.tripId)?<Card><Icon name="leaf-outline" size={42}/><Icon name={stage.failed?'alert-circle-outline':'hourglass-outline'} size={38}/><Text style={S.heading}>{stage.title}</Text>
          {!stage.failed&&<ActivityIndicator color={C.green}/>}<Note>{stage.detail}</Note>
          {['위치 전송','이동 확인','결과 확인'].map((label,i)=><View key={label} style={S.row}><Icon name={i<stage.step?'checkmark-circle':i===stage.step?'radio-button-on':'ellipse-outline'} color={i<=stage.step?C.green:C.muted}/><Text style={S.label}>{label}</Text></View>)}
          {!!p.tripError&&<Note error>{p.tripError}</Note>}
          {(stage.failed||!!p.tripError)&&<Button title={stage.failed?"처리 다시 시도":"결과 다시 확인"} onPress={()=>p.onRetryTrip?.()}/>}
          {!!p.pending&&<Button title="전송 재시도" quiet onPress={()=>p.onRetry?.()}/>}
        </Card>:<Card><Text style={S.heading}>먼저 여정을 선택해주세요</Text><Button title="지난 여정 보기" onPress={()=>setTab('history')}/></Card>}
        <Button title="홈으로 돌아가기" quiet onPress={()=>setTab('home')}/>
      </>}
      {tab==='history'&&<JourneyHistory trips={p.trips} developer={p.profile.role==='developer'} busy={busy} onOpen={id=>{p.onSelect(id);setTab('result');}} onStart={()=>setTab('route')}/>}
      {tab==='baseline'&&<BaselinePanel onRoute={()=>setTab('route')} value={p.baseline} onRetry={p.onRefreshCommunity}/>}
      {tab==='missions'&&<MissionPanel value={p.missions} onRetry={p.onRefreshCommunity} preview={p.preview}/>}
      {tab==='ranking'&&<RankingPanel value={p.ranking} onRetry={p.onRefreshCommunity}/>}
      {tab==='rewards'&&<RewardPanel value={p.rewards} onRetry={p.onRefreshCommunity}/>}
      {tab==='preview'&&p.profile.role==='developer'&&<PanelPreview/>}
      {tab==='profile'&&<>
        <View style={{alignItems:'center',gap:10,paddingVertical:12}}><Pressable accessibilityRole="button" accessibilityLabel="프로필 사진과 정보 수정" onPress={()=>{setDraft(p.profile);setSaveError('');setEdit(true);}}><ProfileAvatar name={p.profile.nickname} uri={p.profile.avatarDataUri} size={88}/><View style={{position:'absolute',right:0,bottom:0,backgroundColor:C.deep,padding:6,borderRadius:14}}><Icon name="camera-outline" size={16} color={C.leaf}/></View></Pressable><Text style={[S.title,{fontSize:26}]}>{p.profile.nickname}</Text><Text style={S.note}>{p.profile.email}</Text><Text style={S.pill}>{p.profile.campaignCode} · 함께하는 캠페인</Text></View>
        <Card><Text style={S.label}>나의 캐노피 토큰</Text><Text style={[S.metric,{color:C.green}]}>{p.rewards?.state==='ready'?`${p.rewards.data.balance.toLocaleString()} T`:'— T'}</Text><Note>여정·미션·랭킹으로 쌓은 보상이에요.</Note><Pressable accessibilityRole="button" onPress={()=>setTab('baseline')}><Text style={S.link}>나의 이동 기준 보기</Text></Pressable></Card>
        <View style={S.row}>{([['집',p.profile.home,'home-outline'],['직장',p.profile.work,'business-outline']] as const).map(([label,place,icon])=><Pressable key={label} accessibilityRole="button" disabled={busy} onPress={()=>{setDraft(p.profile);setSaveError('');setEdit(true);}} style={[S.card,{flex:1,padding:12}]}><View style={S.row}><IllustratedIcon name={label==='집'?'home':'office'} size={45}/><View style={{flex:1}}><Text style={S.note}>{label}</Text><Text numberOfLines={2} style={S.label}>{place?.name??'장소 설정'}</Text></View></View></Pressable>)}</View>

        {([['이동 기록','history','time-outline'],['리워드 내역','rewards','gift-outline'],['나의 미션','missions','flag-outline'],['캠페인 랭킹','ranking','podium-outline']] as const).map(([label,target,icon])=><Pressable key={target} accessibilityRole="button" onPress={()=>setTab(target)} style={[S.between,{paddingVertical:14,borderBottomWidth:1,borderColor:C.line}]}><View style={S.row}><IllustratedIcon name={target==='history'?'walk':target==='rewards'?'wallet':target==='missions'?'mission':'trophy'} size={39}/><Text style={S.label}>{label}</Text></View><Icon name="chevron-forward" size={18}/></Pressable>)}
        {p.profile.role==='developer'&&<><Button title="개발자 GPS 수집 도구" quiet disabled={busy} onPress={()=>{p.onCollectionMode('developer');setTools(true);}}/><Button title="화면 상태 미리보기" quiet onPress={()=>setTab('preview')}/></>}
        <Button title="로그아웃" quiet disabled={busy} onPress={()=>setLogout(true)}/><Note>함께 만드는 더 가벼운 내일.</Note>
      </>}
      </Fade>}
    </ScrollView>}
    {tab==='journey'&&<SafeAreaView edges={busy?['bottom']:[]} style={{flexShrink:0,backgroundColor:C.white}}>{busy&&<JourneyInfoPanel p={p}/>}<View style={{paddingHorizontal:20,paddingVertical:10}}><Button title={p.phase==='starting'?'위치를 준비하고 있어요':p.phase==='stopping'?'기록을 마무리하고 있어요':busy?'여정 종료':'여정 시작'} busy={p.phase==='starting'||p.phase==='stopping'} disabled={!p.ready||!!p.preview} onPress={()=>{if(busy)setStopOpen(true);else p.onStart(direction);}}/></View></SafeAreaView>}
    {busy&&tab!=='journey'&&<Pressable accessibilityRole="button" onPress={()=>setTab('journey')} style={{padding:14,backgroundColor:C.mint,alignItems:'center'}}><Text style={S.link}>진행 중인 여정으로 돌아가기</Text></Pressable>}
    {!busy&&<SafeAreaView edges={['bottom']} style={{flexShrink:0,backgroundColor:'#FAFFFC',borderTopWidth:1,borderColor:'#E1EEE5',borderTopLeftRadius:26,borderTopRightRadius:26,boxShadow:'0 -6px 24px #193f3210'}}>
    <View style={{flexDirection:'row',paddingHorizontal:6,paddingTop:10,paddingBottom:6}}>
      {([['home','home-outline','홈'],['missions','checkmark-circle-outline','미션'],['rewards','wallet-outline','지갑'],['ranking','trophy-outline','랭킹'],['profile','person-outline','내 정보']] as const).map(([target,icon,label])=><Pressable key={target} accessibilityRole="tab" accessibilityState={{selected:tab===target}} accessibilityLabel={label} onPress={()=>setTab(target)} style={({pressed})=>({flex:1,minHeight:58,alignItems:'center',gap:4,paddingVertical:3,opacity:pressed?.72:1})}><View style={{width:46,height:32,borderRadius:16,alignItems:'center',justifyContent:'center',backgroundColor:tab===target?'#DCEEDD':'transparent'}}><IllustratedIcon name={({home:'home',missions:'mission',rewards:'wallet',ranking:'trophy',profile:'profile'} as const)[target]} size={32}/></View><Text style={{fontSize:11,color:tab===target?C.deep:C.muted,fontWeight:'600'}}>{label}</Text></Pressable>)}
    </View>
    </SafeAreaView>}
    <Modal visible={stopOpen||logout} transparent animationType="fade" onRequestClose={()=>{setStopOpen(false);setLogout(false);}}><View style={{flex:1,backgroundColor:'#102e2570',justifyContent:'center',padding:24}}><Card><Text style={S.heading}>{stopOpen?'여정을 종료할까요?':'로그아웃할까요?'}</Text><Note>{stopOpen?'이동 기록을 저장하고 보상을 확인할게요.':'저장한 프로필과 이동 기록은 이 기기에 남아 있습니다.'}</Note><Button title={stopOpen?'여정 종료':'로그아웃'} danger onPress={()=>{if(stopOpen){setStopOpen(false);p.onStop();}else{setLogout(false);p.onBack();}}}/><Button title="취소" quiet onPress={()=>{setStopOpen(false);setLogout(false);}}/></Card></View></Modal>
    <Modal visible={edit} animationType="slide" onRequestClose={()=>setEdit(false)}><SafeAreaProvider><SafeAreaView style={S.root}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={S.scroll}><View style={S.between}><Text style={S.heading}>나의 프로필</Text><Button title="닫기" quiet onPress={()=>setEdit(false)}/></View><View style={{alignItems:'center',gap:12}}><ProfileAvatar name={draft.nickname} uri={draft.avatarDataUri} size={96}/><Button title="사진 선택" quiet onPress={()=>{void chooseProfilePhoto().then(uri=>{if(uri)setDraft(previous=>({...previous,avatarDataUri:uri}));}).catch(()=>setSaveError('사진을 열지 못했어요. 다시 선택해주세요.'));}}/>{!!draft.avatarDataUri&&<Pressable accessibilityRole="button" onPress={()=>setDraft({...draft,avatarDataUri:null})} style={{padding:12}}><Text style={S.link}>사진 삭제</Text></Pressable>}<Note>사진과 닉네임은 캠페인 랭킹에 보여요.</Note></View><Field label="닉네임" value={draft.nickname} onChangeText={nickname=>setDraft({...draft,nickname})} maxLength={30}/><Field label="부서 (선택)" value={draft.department_name??''} onChangeText={department_name=>setDraft({...draft,department_name})} maxLength={50}/><Note>같은 캠페인에서 같은 부서명을 입력한 참여자는 부서 랭킹에 함께 표시돼요.</Note><PlacePicker title="집" value={draft.home} onPick={home=>setDraft({...draft,home})}/><PlacePicker title="직장" value={draft.work} onPick={work=>setDraft({...draft,work})}/><Note>출근은 집 → 직장, 퇴근은 직장 → 집으로 바꿔 검색할 수 있어요. 다른 목적지도 선택할 수 있습니다.</Note>{!!saveError&&<Note error>{saveError}</Note>}<Button title="저장하기" busy={saving} onPress={()=>void save()}/></ScrollView></SafeAreaView></SafeAreaProvider></Modal>
  </SafeAreaView>;
}
