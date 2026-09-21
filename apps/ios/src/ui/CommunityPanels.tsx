import Text from './AppText';
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
export type RankingView = {cumulative?:{label:string;personal:RankingView['personal'];department:RankingView['department'];rewardPolicy:string};awards?:Record<string,number>;week:string;updatedAt:string;personal:{id:string;name:string;rank:number;carbonKg:number;points?:number;isMe?:boolean}[];department:{id:string;name:string;rank:number;carbonKg:number;points?:number}[]};
export type RewardView = {balance:number;developmentOnly?:boolean;items:{id:string;title:string;time:string;amount:number;kind?:string;status:'pending'|'paid'}[]};
export type BaselineView = {status:'collecting'|'ready';updatedAt:string;personalKg:number|null;globalKg:number|null;reason:string;unit?:string;developmentOnly?:boolean;source?:string;trips?:number;observationDays?:number;week?:string;actualG?:number;rewardStatus?:string;expectedPoints?:number|null};
export const unavailable={state:'unavailable'} as const;

function Status({value,onRetry}:{value:Exclude<RemotePanel<unknown>,{state:'ready'}>;onRetry?:()=>void}) {
  const content={unavailable:['연결을 준비하고 있어요','서비스가 연결되면 실제 결과가 여기에 표시됩니다.'],loading:['불러오는 중','최신 정보를 확인하고 있어요.'],empty:['아직 내역이 없어요','첫 결과가 만들어지면 이곳에서 확인할 수 있어요.'],forbidden:['접근 권한을 확인해주세요','실제 계정 인증이 연결된 뒤 이용할 수 있어요.'],error:['불러오지 못했어요',value.state==='error'?value.message:'']}[value.state];
  return <Card>{value.state==='loading'?<ActivityIndicator color={C.green}/>:<Icon name={value.state==='error'?'cloud-offline-outline':'leaf-outline'} size={36}/>}<Text style={S.heading}>{content[0]}</Text><Note error={value.state==='error'}>{content[1]}</Note>{value.state==='error'&&onRetry&&<Button title="다시 불러오기" onPress={onRetry}/>}</Card>;
}
function Updated({week,time}:{week:string;time:string}) {return <View style={{gap:5}}><Text style={S.pill}>{week}</Text><Note>갱신 {new Date(time).toLocaleString('ko-KR')}</Note></View>;}

export function BaselinePanel({value=unavailable,onRetry,onRoute}:{value?:RemotePanel<BaselineView>;onRetry?:()=>void;onRoute?:()=>void}) {
  return <>{onRoute&&<Card><Text style={S.pill}>출발 전 · KTDB POPULATION</Text><Text style={S.heading}>다른 사람들은 어떻게 이동할까요?</Text><Note>출발지와 목적지를 선택하면 KTDB 모델이 예측한 이동수단별 선택 확률과 예상 탄소량을 보여드려요. 개인 기록이 없어도 확인할 수 있어요.</Note><Button title="경로별 KTDB 기준 보기" onPress={onRoute}/></Card>}<Text style={S.title}>나의 이동을{ '\n'}알아가는 시간.</Text><Note>Baseline은 이동 기록을 바탕으로 서버에서 계산한 비교 기준입니다. 경로 검색의 예상값과는 달라요.</Note>
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<><Card><Text style={S.pill}>{value.data.status==='ready'?'기준 생성 완료':'이동 데이터 수집 중'}</Text><Note>{value.data.reason}</Note><View style={S.row}><Stat label="개인 기준" value={value.data.personalKg==null?'—':value.data.personalKg.toFixed(2)}/><Stat label="전체 기준" value={value.data.globalKg==null?'—':value.data.globalKg.toFixed(2)}/></View>{value.data.developmentOnly&&<Note>검증용 기준 · {value.data.source}</Note>}<Note>비교 기준은 매주 고정되고, 여정마다 거리당 배출량과 비교해 보상을 계산해요. 개인 기준이 준비되기 전에는 KTDB 기준을 사용합니다. 기준 생성에는 관찰 기간과 유효한 출퇴근 기록이 필요해요.</Note>{value.data.actualG!==undefined&&<View style={{backgroundColor:C.mint,padding:18,borderRadius:18,gap:12}}><Text style={S.label}>{value.data.week} 집계된 나의 배출량</Text><Text style={[S.metric,{fontSize:30}]}>{value.data.actualG.toFixed(2)} gCO₂e/km</Text><Note>개선 보상: 개인 기준보다 낮게 / 유지 보상: 개선에 해당하지 않을 때 전체 기준 이하</Note></View>}<Note>탄소 기준 단위: {value.data.unit??'kgCO₂e'}</Note><Note>갱신 {new Date(value.data.updatedAt).toLocaleString('ko-KR')}</Note></Card></>}
    <Card><Icon name="footsteps-outline"/><Text style={S.heading}>평소처럼 이동해주세요</Text><Note>기준이 준비되기 전에도 여정을 기록할 수 있어요. 기준 생성 조건과 준비 여부는 서버에서 판단합니다.</Note></Card>
  </>;
}

export function MissionPanel({value=unavailable,onRetry}:{value?:RemotePanel<MissionView>;onRetry?:()=>void}) {
  const [filter,setFilter]=useState<'all'|'active'|'completed'>('active');
  const [busy,setBusy]=useState<string|null>(null),[error,setError]=useState('');
  const [reward,setReward]=useState<{amount:number;title:string}|null>(null);
  const [claimed,setClaimed]=useState<string[]>([]);
  async function claim(id:string){if(busy)return;setBusy(id);setError('');try{
    const r=await localAction('/missions/acknowledge',{assignment_id:id});
    if(r.status!=='paid')throw Error('지급 결과를 확인하지 못했어요. 다시 시도해주세요.');
    setClaimed(v=>[...v,id]);setReward({amount:r.points,title:r.title});onRetry?.();
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(null);}}
  const items=value.state==='ready'?value.data.items.map(m=>({...m,status:claimed.includes(m.id)?'completed':m.status})):[];
  const shown=useRef(new Set<string>());
  const [started,setStarted]=useState<string[]>([]);
  async function track(id:string,event_type:'shown'|'started'){await localAction('/missions/events',{assignment_id:id,event_type,event_id:randomUUID()});}
  const visible=items.filter(m=>filter==='all'||(filter==='active'?['active','claimable'].includes(m.status):m.status===filter));
  const shownKey=visible.map(m=>m.id).join('|');
  useEffect(()=>{for(const m of visible){if(shown.current.has(m.id)||m.id.startsWith('preview-'))continue;shown.current.add(m.id);void track(m.id,'shown').catch(()=>shown.current.delete(m.id));}},[shownKey]);
  return <>
    <View style={{flexDirection:'row',alignItems:'center',backgroundColor:'#edf3e3',borderRadius:28,padding:20}}><View style={{flex:1,minWidth:0,gap:10}}><Text style={[S.label,{color:C.green,fontSize:11}]}>작은 실천, 확실한 변화</Text><Text style={S.title}>이번 주의{'\n'}나를 위한 도전</Text></View><View style={{width:105}}><CanopyMascot pose="coin" height={140}/></View></View><Note>목표를 달성하면 보상을 받아보세요. 받은 보상은 지갑에 바로 쌓여요.</Note>
    <View style={[S.row,{backgroundColor:'#e5eee8',borderRadius:28,padding:4}]}>{([['active','진행 중'],['completed','완료'],['all','전체']] as const).map(([id,label])=><Pressable key={id} accessibilityRole="button" accessibilityState={{selected:filter===id}} onPress={()=>setFilter(id)} style={{flex:1,alignItems:'center',padding:12,borderRadius:24,backgroundColor:filter===id?C.white:'transparent'}}><Text style={{fontWeight:'700',color:filter===id?C.deep:C.muted}}>{label}</Text></Pressable>)}</View>
    {!!error&&<Note error>{error}</Note>}
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>
      <Updated week={value.data.week} time={value.data.updatedAt}/>
      {visible.map((m,i)=><Card key={m.id}>
        <View style={S.between}><View style={{backgroundColor:['#edf5d8','#e5eefb','#fff0db'][i%3],padding:14,borderRadius:20}}><Icon name={m.status==='completed'?'checkmark-circle':'leaf-outline'} size={30}/></View><Text style={S.pill}>{m.status==='completed'?'보상 수령 완료':m.status==='claimable'?'목표 달성!':m.category}</Text></View>
        <Text style={S.heading}>{m.title}</Text>{m.week&&m.week!==value.data.week&&<Note>{m.week} 주에 달성한 미션 · 지금도 수령할 수 있어요.</Note>}<Note>{m.description}</Note>
        <View style={S.between}><Text style={S.label}>{m.progress.toLocaleString()} / {m.goal.toLocaleString()} {m.unit}</Text><Text style={[S.label,{color:'#a27621'}]}>{m.rewardPoints!==undefined?`+${m.rewardPoints} T`:''}</Text></View>
        <View accessibilityRole="progressbar" accessibilityValue={{min:0,max:m.goal,now:Math.min(m.goal,m.progress)}} style={{height:8,borderRadius:8,backgroundColor:'#e8f0eb',overflow:'hidden'}}><View style={{height:8,borderRadius:8,backgroundColor:C.green,width:`${m.goal>0?Math.min(100,Math.max(0,m.progress/m.goal*100)):0}%`}}/></View>
        {m.status==='active'&&<><Button title={started.includes(m.id)?'실천 중':'실천 시작하기'} quiet disabled={started.includes(m.id)} onPress={()=>void track(m.id,'started').then(()=>setStarted(v=>[...v,m.id])).catch(e=>setError(String(e)))}/><Note>별도 시작 없이 여정을 기록해도 달성 조건에 자동 반영돼요.</Note></>}
        {m.status==='claimable'&&<Button title="보상 받기" busy={busy===m.id} disabled={!!busy} onPress={()=>void claim(m.id)}/>}
      </Card>)}
      {!visible.length&&<Status value={{state:'empty'}}/>}
    </>}
    {reward&&<RewardCelebration {...reward} onClose={()=>{setReward(null);setFilter('completed');onRetry?.();}}/>}
  </>;
}

export function RankingPanel({value=unavailable,onRetry}:{value?:RemotePanel<RankingView>;onRetry?:()=>void}) {
  const [group,setGroup]=useState<'personal'|'department'>('personal'),[season,setSeason]=useState(false);
  if(season)return <><Text style={S.title}>{value.state==='ready'?value.data.cumulative?.label??'캠페인 누적':'캠페인 누적'}</Text><Note>참여 기간에 지급된 여정별 포인트를 합산해요. 미션·랭킹 보상은 순위 점수에 더하지 않아요.</Note>
    <View style={S.row}><Button title="개인" quiet={group!=='personal'} onPress={()=>setGroup('personal')}/><Button title="부서" quiet={group!=='department'} onPress={()=>setGroup('department')}/></View>
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>{(value.data.cumulative?.[group]??[]).map(row=><Card key={row.id}><Text style={S.heading}>{row.rank}위 · {row.name}</Text><Note>{row.points??0} 포인트</Note></Card>)}{!value.data.cumulative?.[group].length&&<Note>아직 집계할 여정 보상이 없어요.</Note>}<Note>{value.data.cumulative?.rewardPolicy}</Note></>}
    <Button title="주간 랭킹 보기" onPress={()=>setSeason(false)}/></>;
  return <><View style={S.row}><View style={{flex:1}}><Button title="주간 랭킹" quiet onPress={()=>setSeason(false)}/></View><View style={{flex:1}}><Button title="캠페인 누적" quiet onPress={()=>setSeason(true)}/></View></View>
    <View style={S.row}>{([['personal','개인'],['department','부서']] as const).map(([id,label])=><View key={id} style={{flex:1}}><Button title={label} quiet={group!==id} onPress={()=>setGroup(id)}/></View>)}</View>
    <View style={{backgroundColor:C.mint,borderRadius:18,padding:20,gap:14}}><Text style={[S.label,{textAlign:'center',letterSpacing:2}]}>THE GREEN LEAGUE</Text><CanopyMascot pose="trophy" height={160}/><Text style={[S.heading,{textAlign:'center'}]}>이번 주의 초록빛 주인공</Text><View style={{flexDirection:'row',alignItems:'flex-end',justifyContent:'center',gap:16}}>{[2,1,3].map(rank=>{const peers=value.state==='ready'?value.data[group].filter(r=>r.rank===rank):[];const row=peers[0];return <View key={rank} style={{flex:1,alignItems:'center',gap:6}}><View style={{width:rank===1?66:52,height:rank===1?66:52,borderRadius:40,backgroundColor:rank===1?'#fff1c4':rank===2?'#e5edf0':'#f3e5d9',alignItems:'center',justifyContent:'center',borderWidth:2,borderColor:C.white}}><Icon name={rank===1?'trophy':'ribbon-outline'} size={rank===1?35:27} color={rank===1?'#b88a28':rank===2?'#708b97':'#ad805e'}/></View><Text style={[S.metric,{fontSize:18,color:rank===1?'#bd8d30':C.muted}]}>{rank}</Text><Text numberOfLines={1} style={S.label}>{row?`${row.name}${peers.length>1?` 외 ${peers.length-1}명`:''}`:'—'}</Text><Text style={[S.note,{fontSize:11}]}>{row?row.points!==undefined?`${row.points.toLocaleString('ko-KR',{maximumFractionDigits:2})} P`:`${row.carbonKg.toFixed(2)} kg`:value.state==='ready'?'해당 순위 없음':'집계 대기'}</Text></View>;})}</View></View>
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>
      <Updated week={value.data.week} time={value.data.updatedAt}/><Note>주간 집계 결과입니다. 주가 마감되고 집계가 완료되면 상위권 보상이 따로 지급됩니다. 랭킹 보상 자체는 순위 점수에 더하지 않습니다.</Note>{value.data.awards&&<View style={[S.row,{flexWrap:'wrap'}]}>{Object.entries(value.data.awards).map(([rank,amount])=><Text key={rank} style={S.pill}>{rank}위 +{amount} T</Text>)}</View>}
      {!value.data[group].length&&<Status value={{state:'empty'}}/>}
      {value.data[group].map(row=><Card key={row.id}><View style={S.between}>
        <View style={[S.row,{flex:1}]}><Text style={[S.metric,{width:36}]}>{row.rank}</Text><View style={{flex:1,gap:4}}><Text style={S.label}>{row.name}{'isMe' in row&&row.isMe?' (나)':''}</Text><Note>{row.points!==undefined?`${row.points.toLocaleString('ko-KR',{maximumFractionDigits:2})} 포인트`:`${row.carbonKg.toFixed(2)} kgCO₂e 감축`}</Note></View></View>
        {row.rank<=3&&<Icon name="trophy-outline" color="#ac862b"/>}
      </View></Card>)}
    </>}
  </>;
}

export function RewardPanel({value=unavailable,onRetry}:{value?:RemotePanel<RewardView>;onRetry?:()=>void}) {
  const [info,setInfo]=useState(false),[kind,setKind]=useState('all');
  return <><Card><View style={S.between}><View style={[S.row,{flex:1,flexWrap:'wrap'}]}><View style={{width:76}}><CanopyMascot pose="coin" height={92}/></View><View><Text style={S.note}>보유 토큰</Text><Text style={[S.metric,{color:C.green}]}>{value.state==='ready'?`${value.data.balance.toLocaleString('ko-KR',{maximumFractionDigits:2})} T`:'— T'}</Text></View></View><Pressable accessibilityRole="button" onPress={()=>setInfo(!info)} style={{borderWidth:1,borderColor:C.green,borderRadius:20,padding:10}}><Text style={[S.link,{fontSize:12}]}>리워드 안내</Text></Pressable></View></Card>
    {info&&<Card><View style={{alignItems:'center',padding:24}}><Icon name="gift-outline" size={48}/></View><Text style={S.heading}>일상의 이동을 가치 있게</Text><Note>여정: 출발 전에 정한 기준보다 탄소를 적게 배출하면 적립. 미션: 목표 달성 후 보상 받기. 기준은 매주 갱신되며 여정 보상을 주간으로 다시 지급하지 않아요. 랭킹: 마감된 주의 순위에 따라 별도 적립. 각 보상은 한 번만 지급됩니다.</Note><Button title="닫기" quiet onPress={()=>setInfo(false)}/></Card>}
    <Text style={S.heading}>차곡차곡 쌓인 변화</Text>
    {value.state==='ready'&&value.data.developmentOnly&&<Note>로컬 테스트 포인트 · 실제 자산으로 지급되지 않습니다.</Note>}
    <View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{[['all','전체'],['trip','여정'],['mission','미션'],['weekly','주간'],['ranking','랭킹']].map(([id,label])=><Pressable key={id} accessibilityRole="button" accessibilityState={{selected:kind===id}} onPress={()=>setKind(id)} style={{paddingHorizontal:15,paddingVertical:10,borderRadius:22,backgroundColor:kind===id?C.deep:C.white}}><Text style={{color:kind===id?C.white:C.deep,fontWeight:'600'}}>{label}</Text></Pressable>)}</View>
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>
      {!value.data.items.length&&<Status value={{state:'empty'}}/>}
      {value.data.items.filter(row=>kind==='all'||(row.kind??'weekly')===kind).map(row=><Card key={row.id}><View style={S.between}><Icon name="sparkles-outline"/><View style={{flex:1,gap:6}}><Text style={S.label}>{row.title}</Text><Note>{new Date(row.time).toLocaleString('ko-KR')}</Note></View><View style={{alignItems:'flex-end',gap:6,maxWidth:'42%'}}><Text style={S.heading}>{row.status==='paid'?`+${row.amount.toLocaleString('ko-KR',{maximumFractionDigits:2})} T`:'처리 중'}</Text><Note>{row.status==='paid'?'지급 완료':'지급 확인 대기'}</Note></View></View></Card>)}
    </>}
  </>;
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
