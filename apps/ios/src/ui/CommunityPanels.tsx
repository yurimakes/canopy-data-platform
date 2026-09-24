import {RankMedal} from './RankMedal';
import {MissionCard} from './MissionCard';
import {IllustratedIcon} from './IllustratedIcon';
import {MascotConversation} from './MascotConversation';
import Text from './AppText';
import {LinearGradient} from 'expo-linear-gradient';
import {ProfileAvatar} from './ProfileAvatar';
import {Disclosure,Eyebrow,ProgressTrack,Segmented,SectionTitle} from './DesignPrimitives';
import {CanopyMascot} from './CanopyMascot';
import {localAction} from '../communityClient';
import {RewardCelebration} from './RewardExperience';
import React,{useState,useEffect,useRef} from 'react';
import {randomUUID} from 'expo-crypto';
import {ActivityIndicator,Pressable,View} from 'react-native';
import {Button,Card,C,Icon,Note,S,Stat} from './theme';

// 앱 표시 모델. 서버 공통 스키마를 변경하지 않고 API 어댑터에서 변환 후 전달
export type RemotePanel<T> = {state:'unavailable'|'loading'|'empty'|'forbidden'} | {state:'error';message:string} | {state:'ready';data:T};
export type MissionView = {week:string;updatedAt:string;items:{id:string;week?:string;title:string;category:string;description:string;progress:number;goal:number;unit:string;rewardPoints?:number;status:'active'|'claimable'|'completed'|'expired'}[]};
export type RankingView = {cumulative?:{label:string;personal:RankingView['personal'];department:RankingView['department'];rewardPolicy:string};awards?:Record<string,number>;week:string;updatedAt:string;personal:{id:string;name:string;rank:number;carbonKg:number;points?:number;isMe?:boolean;avatarDataUri?:string|null}[];department:{id:string;name:string;rank:number;carbonKg:number;points?:number}[]};
export type RewardView = {balance:number;developmentOnly?:boolean;items:{id:string;title:string;time:string;amount:number;kind?:string;status:'pending'|'paid'}[]};
export type BaselineView = {status:'collecting'|'ready';updatedAt:string;personalKg:number|null;globalKg:number|null;reason:string;unit?:string;developmentOnly?:boolean;source?:string;trips?:number;observationDays?:number;week?:string;actualG?:number;rewardStatus?:string;expectedPoints?:number|null};
export const unavailable={state:'unavailable'} as const;

function Status({value,onRetry}:{value:Exclude<RemotePanel<unknown>,{state:'ready'}>;onRetry?:()=>void}) {
  const content={unavailable:['연결을 준비하고 있어요','잠시 후 다시 확인해주세요.'],loading:['불러오는 중','최신 정보를 확인하고 있어요.'],empty:['아직 내역이 없어요','첫 결과가 만들어지면 이곳에서 확인할 수 있어요.'],forbidden:['접근 권한을 확인해주세요','다시 로그인해주세요.'],error:['불러오지 못했어요',value.state==='error'?'연결을 확인하고 다시 시도해주세요.':'']}[value.state];
  return <Card>{value.state==='loading'?<ActivityIndicator color={C.green}/>:<Icon name={value.state==='error'?'cloud-offline-outline':'leaf-outline'} size={36}/>}<Text style={S.heading}>{content[0]}</Text><Note error={value.state==='error'}>{content[1]}</Note>{value.state==='error'&&onRetry&&<Button title="다시 불러오기" onPress={onRetry}/>}</Card>;
}
function Updated({week,time}:{week:string;time:string}) {return <Text style={{fontSize:11,color:C.muted}}>이번 주 {week}</Text>;}

export function BaselinePanel({value=unavailable,onRetry,onRoute}:{value?:RemotePanel<BaselineView>;onRetry?:()=>void;onRoute?:()=>void}) {
 return <><Eyebrow>YOUR IMPACT</Eyebrow><Text style={S.title}>얼마나 줄이면{'\n'}보상을 받나요?</Text><Note>이동할 때 탄소를 줄이면 토큰이 쌓여요.</Note>
 {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<><View style={[S.card,{backgroundColor:C.deep,borderWidth:0}]}><Text style={{color:C.leaf,fontWeight:'600'}}>이번 주 나의 기준</Text><Text style={{fontSize:38,color:'white',fontWeight:'700'}}>{value.data.personalKg==null?'첫날부터 가능':`${value.data.personalKg.toFixed(1)} g/km`}</Text><Text style={{color:'#BFD3C6',fontSize:14,lineHeight:23}}>{value.data.personalKg==null?'경로를 선택하면 보상 기준을 확인할 수 있어요.':'1km마다 이보다 적게 배출하면 보상 대상이에요.'}</Text></View>
 <Card><View style={S.row}><Icon name="footsteps-outline"/><Text style={S.heading}>내 기록으로 더 정확하게</Text></View><Note>이동 기록이 쌓이면 나에게 맞는 기준이 만들어져요.</Note><View style={S.row}><Stat label="기록한 여정" value={value.data.trips==null?'—':`${value.data.trips}회`}/><Stat label="기록한 기간" value={value.data.observationDays==null?'—':`${value.data.observationDays}일`}/></View>
 <Disclosure title="기준과 보상 자세히 보기"><Note>개인 기준은 매주 갱신돼요. 준비 전에는 국가교통DB의 경로 예측을 사용해요.</Note><Note>주간 개인 기준: {value.data.personalKg??'준비 중'}, 전체 기준: {value.data.globalKg??'준비 중'} {value.data.unit??'gCO₂e/km'}</Note><Note>실제 이동거리와 탄소량으로 계산해요. 절감량이 적으면 토큰이 없을 수 있어요.</Note></Disclosure></Card></>}
 {onRoute&&<Button title="경로별 보상 기준 보기" onPress={onRoute}/>}</>;
}

export function MissionPanel({value=unavailable,onRetry,preview=false,nickname='회원'}:{value?:RemotePanel<MissionView>;onRetry?:()=>void;preview?:boolean;nickname?:string}) {
  const [filter,setFilter]=useState<'all'|'active'|'completed'>('active');
  const [busy,setBusy]=useState<string|null>(null),[error,setError]=useState('');
  const [reward,setReward]=useState<{amount:number;title:string}|null>(null);
  const [claimed,setClaimed]=useState<string[]>([]),[leaving,setLeaving]=useState<string|null>(null);
  const claimLock=useRef(false);
  async function claim(id:string){if(claimLock.current)return;claimLock.current=true;setBusy(id);setError('');try{
    const example=preview&&value.state==='ready'?value.data.items.find(m=>m.id===id):undefined;
    const r=preview?{status:'paid',points:example?.rewardPoints??0,title:example?.title??'미션 보상'}:await localAction('/missions/acknowledge',{assignment_id:id});
    if(r.status!=='paid')throw Error('지급 결과를 확인하지 못했어요. 다시 시도해주세요.');
    setLeaving(id);await new Promise(resolve=>setTimeout(resolve,420));setClaimed(v=>[...v,id]);setLeaving(null);if(Number.isFinite(r.points)&&r.points>0)setReward({amount:r.points,title:r.title});onRetry?.();
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(null);claimLock.current=false;}}
  const items=value.state==='ready'?value.data.items.map(m=>({...m,status:claimed.includes(m.id)?'completed':m.status})):[];
  const shown=useRef(new Set<string>());
  async function track(id:string,event_type:'shown'){if(preview)return;await localAction('/missions/events',{assignment_id:id,event_type,event_id:randomUUID()});}
  const visible=items.filter(m=>filter==='all'||(filter==='active'?['active','claimable'].includes(m.status):m.status===filter));
  const shownKey=visible.map(m=>m.id).join('|');
  useEffect(()=>{for(const m of visible){if(shown.current.has(m.id)||m.id.startsWith('preview-'))continue;shown.current.add(m.id);void track(m.id,'shown').catch(()=>shown.current.delete(m.id));}},[shownKey]);
  return <>
    <View style={{gap:8}}><Eyebrow>SMALL STEPS. BIG CHANGE.</Eyebrow><Text style={[S.title,{fontSize:25,lineHeight:36}]}>{nickname}님만을 위한{'\n'}이번 주 미션</Text></View>
    <View style={[S.between,{backgroundColor:'#E6F2EA',borderRadius:26,padding:20,borderWidth:1,borderColor:'white'}]}><View style={{gap:8}}><Text style={{color:C.muted,fontSize:12}}>이번 주 달성</Text><Text style={{fontSize:32,fontWeight:'700',color:C.deep}}>{items.filter(m=>m.status==='completed'||m.status==='claimable').length}<Text style={{fontSize:16,color:C.muted}}> / {items.length}</Text></Text></View><View style={{width:95}}><IllustratedIcon name="mission" size={95}/></View></View>
    <Segmented items={[{id:'active',label:'도전 중'},{id:'completed',label:'완료'},{id:'all',label:'전체'}]} value={filter} onChange={v=>setFilter(v as typeof filter)}/>
    {!!error&&<Note error>{error}</Note>}
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>
      <Updated week={value.data.week} time={value.data.updatedAt}/>
      {visible.map(m=><MissionCard key={m.id} mission={m} week={value.data.week} busy={!!busy} leaving={leaving===m.id} onClaim={()=>void claim(m.id)}/>)}
      {!visible.length&&<Status value={{state:'empty'}}/>}
    </>}

    {reward&&<RewardCelebration {...reward} headline={"작은 실천이\n보상이 되었어요."} confirmLabel="완료한 미션 보기" onClose={()=>{setReward(null);setFilter('completed');onRetry?.();}}/>}
  </>;
}

export function RankingPanel({value=unavailable,onRetry}:{value?:RemotePanel<RankingView>;onRetry?:()=>void}) {
 const [group,setGroup]=useState<'personal'|'department'>('personal'),[season,setSeason]=useState(false);
 const data=value.state==='ready'?value.data:null,rows=(season?data?.cumulative?.[group]:data?.[group])??[];
 const me=rows.find(r=>'isMe' in r&&r.isMe);
 return <><View style={S.between}><View style={{gap:8}}><Eyebrow>THE GREEN LEAGUE</Eyebrow><Text style={S.title}>랭킹</Text></View></View>
 <Segmented items={[{id:'week',label:'이번 주'},{id:'season',label:'캠페인 전체'}]} value={season?'season':'week'} onChange={v=>setSeason(v==='season')}/>
 <View style={S.row}>{(['personal','department'] as const).map(g=><Pressable key={g} accessibilityRole="button" accessibilityState={{selected:group===g}} onPress={()=>setGroup(g)} style={{minHeight:44,paddingHorizontal:16,justifyContent:'center',borderBottomWidth:2,borderBottomColor:group===g?C.green:'transparent'}}><Text style={[S.label,{color:group===g?C.green:C.muted}]}>{g==='personal'?'개인':'부서'}</Text></Pressable>)}</View>
 {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>
 {rows.length>0&&<View style={{flexDirection:'row',alignItems:'flex-end',gap:8,paddingTop:10,paddingBottom:4}}>{[2,1,3].map(rank=>{const row=rows.find(r=>r.rank===rank);return <View key={rank} style={{flex:1,alignItems:'center',gap:8}}><ProfileAvatar size={48} name={row?.name??'—'} uri={row&&'avatarDataUri' in row&&typeof row.avatarDataUri==='string'?row.avatarDataUri:null}/><Text numberOfLines={1} style={[S.label,{fontSize:12}]}>{row?.name??'도전자를 기다려요'}</Text><View style={{width:'82%',height:rank===1?90:rank===2?65:49,borderTopLeftRadius:16,borderTopRightRadius:16,backgroundColor:rank===1?'#EBD88D':rank===2?'#DDE7CB':'#EBDDC5',alignItems:'center',justifyContent:'center',gap:3}}><RankMedal rank={rank}/><Text style={{fontSize:11,color:C.deep}}>{row?.points??0} P</Text></View></View>;})}</View>}
 {me&&<View style={[S.between,{padding:18,borderRadius:18,backgroundColor:C.leaf}]}><View style={S.row}><Icon name="trending-up"/><Text style={S.label}>현재 내 순위</Text></View><Text style={S.heading}>{me.rank}위</Text></View>}
 <Note>{season?'캠페인 동안 모은 여정 포인트':'이번 주에 모은 여정 포인트'}로 순위를 정해요.</Note>
 {rows.map(row=><View key={row.id} style={[S.row,{paddingVertical:16,borderBottomWidth:1,borderColor:C.line}]}>{row.rank<=3?<RankMedal rank={row.rank} size={26}/>:<Text style={[S.metric,{width:26,fontSize:18,color:C.muted}]}>{row.rank}</Text>}<ProfileAvatar name={row.name} uri={'avatarDataUri' in row&&typeof row.avatarDataUri==='string'?row.avatarDataUri:null} size={42}/><View style={{flex:1,gap:3}}><Text numberOfLines={1} style={S.label}>{row.name}{'isMe' in row&&row.isMe?' (나)':''}</Text><Text style={{fontSize:11,color:C.muted}}>{group==='personal'?'초록 발걸음':'함께 쌓은 변화'}</Text></View><Text style={S.label}>{(row.points??0).toLocaleString()} P</Text></View>)}
 {!rows.length&&<Status value={{state:'empty'}}/>}
 <Disclosure title="순위와 보상 안내"><Note>여정 포인트를 합산해요. 미션과 랭킹 보상은 순위에 포함되지 않아요.</Note><Note>{season?'캠페인 누적 순위는 추가 보상이 없어요.':'주간 집계 후 상위권 보상이 별도로 지급돼요.'}</Note>{!season&&data?.awards&&Object.entries(data.awards).map(([rank,amount])=><Note key={rank}>{rank}위 {amount} T</Note>)}</Disclosure>
 </>}</>;
}

export function RewardPanel({value=unavailable,onRetry}:{value?:RemotePanel<RewardView>;onRetry?:()=>void}) {
 const [kind,setKind]=useState('all');
 const rows=value.state==='ready'?value.data.items.filter(r=>kind==='all'||(r.kind??'weekly')===kind):[];
 return <><Eyebrow>REWARD HISTORY</Eyebrow>
 <View style={{flexDirection:'row',gap:6,flexWrap:'wrap'}}>{[['all','전체'],['trip','이동'],['mission','미션'],['weekly','주간'],['ranking','랭킹']].map(([id,label])=><Pressable key={id} accessibilityRole="button" accessibilityState={{selected:kind===id}} onPress={()=>setKind(id)} style={{paddingHorizontal:16,minHeight:44,justifyContent:'center',borderRadius:14,backgroundColor:kind===id?C.deep:'#EAF0E5'}}><Text style={{fontSize:13,fontWeight:'600',color:kind===id?'white':C.muted}}>{label}</Text></Pressable>)}</View>
 {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>{!rows.length&&<Status value={{state:'empty'}}/>}{rows.map(row=><View key={row.id} style={[S.row,{padding:16,borderRadius:22,backgroundColor:'white',borderWidth:1,borderColor:'#E7EEE8'}]}><View style={{padding:12,borderRadius:16,backgroundColor:C.mint}}><IllustratedIcon name={row.kind==='mission'?'mission':row.kind==='ranking'?'trophy':'walk'} size={42}/></View><View style={{flex:1,gap:5}}><Text style={[S.label,{fontSize:13}]}>{row.title}</Text><Note>{new Date(row.time).toLocaleDateString('ko-KR',{month:'short',day:'numeric'})}  {row.status==='paid'?'적립 완료':'확인 중'}</Note></View><Text style={[S.label,{color:C.green}]}>{row.status==='paid'?`+${row.amount.toLocaleString()} T`:'확인 중'}</Text></View>)}</>}
 <Disclosure title="토큰은 어떻게 모으나요?"><Note>이동: 기준보다 탄소를 줄이면 적립돼요.</Note><Note>미션: 목표를 달성하고 보상을 받으세요.</Note><Note>랭킹: 주간 상위권에 들면 추가 적립돼요.</Note></Disclosure></>;
}

// 개발자 화면 검토 전용. 일반 프로필과 서버 기록에 저장하거나 전송하지 않는 예시
export function PanelPreview() {
  const [state,setState]=useState<'ready'|'loading'|'empty'|'error'|'forbidden'>('ready');
  const common=state==='error'?{state,message:'화면 확인용 네트워크 오류입니다.'} as const:{state};
  const week='2026.09.14 ~ 09.20',updatedAt='2026-09-17T00:00:00Z';
  return <><Note>개발자 화면 예시입니다. 실제 미션, 순위, 보상 내역이 아니며 서버로 전송하지 않습니다.</Note>
    <View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{(['ready','loading','empty','error','forbidden'] as const).map((s,i)=><Button key={s} title={['결과','로딩','빈값','오류','접근 불가'][i]} quiet={state!==s} onPress={()=>setState(s)}/>)}</View>
    <MissionPanel value={state==='ready'?{state,data:{week,updatedAt,items:[{id:'preview-mission',title:'대중교통과 친해지기',category:'습관',description:'이번 주 대중교통을 이용하는 작은 실천',progress:2,goal:3,unit:'회',status:'active'}]}}:common as RemotePanel<MissionView>} onRetry={()=>setState('ready')}/>
    <RankingPanel value={state==='ready'?{state,data:{week,updatedAt,personal:[{id:'preview-user',name:'화면 예시 사용자',rank:1,carbonKg:3.2,isMe:true}],department:[{id:'preview-dept',name:'화면 예시 부서',rank:1,carbonKg:12.4}]}}:common as RemotePanel<RankingView>} onRetry={()=>setState('ready')}/>
    <RewardPanel value={state==='ready'?{state,data:{balance:100,items:[{id:'preview-paid',title:'화면 예시 보상',time:updatedAt,amount:100,status:'paid'},{id:'preview-pending',title:'화면 예시 지급 대기',time:updatedAt,amount:0,status:'pending'}]}}:common as RemotePanel<RewardView>} onRetry={()=>setState('ready')}/>
  </>;
}
