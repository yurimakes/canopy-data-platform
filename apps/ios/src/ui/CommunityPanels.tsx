import React,{useState} from 'react';
import {ActivityIndicator,Pressable,Text,View} from 'react-native';
import {Button,Card,C,Icon,Note,S,Stat} from './theme';

// 앱 표시 모델. 서버 공통 스키마를 변경하지 않고 API 어댑터에서 변환 후 전달
export type RemotePanel<T> = {state:'unavailable'|'loading'|'empty'|'forbidden'} | {state:'error';message:string} | {state:'ready';data:T};
export type MissionView = {week:string;updatedAt:string;items:{id:string;title:string;category:string;description:string;progress:number;goal:number;unit:string;status:'active'|'completed'|'expired'}[]};
export type RankingView = {week:string;updatedAt:string;personal:{id:string;name:string;rank:number;carbonKg:number;isMe?:boolean}[];department:{id:string;name:string;rank:number;carbonKg:number}[]};
export type RewardView = {balance:number;items:{id:string;title:string;time:string;amount:number;status:'pending'|'paid'}[]};
export type BaselineView = {status:'collecting'|'ready';updatedAt:string;personalKg:number|null;globalKg:number|null;reason:string};
export const unavailable={state:'unavailable'} as const;

function Status({value,onRetry}:{value:Exclude<RemotePanel<unknown>,{state:'ready'}>;onRetry?:()=>void}) {
  const content={unavailable:['연결을 준비하고 있어요','서비스가 연결되면 실제 결과가 여기에 표시됩니다.'],loading:['불러오는 중','최신 정보를 확인하고 있어요.'],empty:['아직 내역이 없어요','첫 결과가 만들어지면 이곳에서 확인할 수 있어요.'],forbidden:['접근 권한을 확인해주세요','실제 계정 인증이 연결된 뒤 이용할 수 있어요.'],error:['불러오지 못했어요',value.state==='error'?value.message:'']}[value.state];
  return <Card>{value.state==='loading'?<ActivityIndicator color={C.green}/>:<Icon name={value.state==='error'?'cloud-offline-outline':'leaf-outline'} size={36}/>}<Text style={S.heading}>{content[0]}</Text><Note error={value.state==='error'}>{content[1]}</Note>{value.state==='error'&&onRetry&&<Button title="다시 불러오기" onPress={onRetry}/>}</Card>;
}
function Updated({week,time}:{week:string;time:string}) {return <View style={{gap:5}}><Text style={S.pill}>{week}</Text><Note>갱신 {new Date(time).toLocaleString('ko-KR')}</Note></View>;}

export function BaselinePanel({value=unavailable,onRetry}:{value?:RemotePanel<BaselineView>;onRetry?:()=>void}) {
  return <><Text style={S.title}>나의 이동을{ '\n'}알아가는 시간.</Text><Note>Baseline은 이동 기록을 바탕으로 서버에서 계산한 비교 기준입니다. 경로 검색의 예상값과는 달라요.</Note>
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<><Card><Text style={S.pill}>{value.data.status==='ready'?'기준 생성 완료':'이동 데이터 수집 중'}</Text><Note>{value.data.reason}</Note><View style={S.row}><Stat label="개인 기준" value={value.data.personalKg==null?'—':`${value.data.personalKg.toFixed(2)} kg`}/><Stat label="전체 기준" value={value.data.globalKg==null?'—':`${value.data.globalKg.toFixed(2)} kg`}/></View><Note>탄소 배출량 단위: kgCO₂e</Note><Note>갱신 {new Date(value.data.updatedAt).toLocaleString('ko-KR')}</Note></Card></>}
    <Card><Icon name="footsteps-outline"/><Text style={S.heading}>평소처럼 이동해주세요</Text><Note>기준이 준비되기 전에도 여정을 기록할 수 있어요. 기준 생성 조건과 준비 여부는 서버에서 판단합니다.</Note></Card>
  </>;
}

export function MissionPanel({value=unavailable,onRetry}:{value?:RemotePanel<MissionView>;onRetry?:()=>void}) {
  const [filter,setFilter]=useState<'all'|'active'|'completed'>('all');
  return <><Text style={S.title}>작은 도전,{ '\n'}일상 속 큰 변화.</Text><Note>주간 미션과 나의 실천을 한곳에서 확인해요.</Note>
    <View style={S.row}>{([['all','전체'],['active','진행 중'],['completed','완료']] as const).map(([id,label])=><Pressable key={id} accessibilityRole="button" accessibilityState={{selected:filter===id}} onPress={()=>setFilter(id)} style={[S.pill,{backgroundColor:filter===id?C.green:C.mint}]}><Text style={{color:filter===id?C.white:C.green}}>{label}</Text></Pressable>)}</View>
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>
      <Updated week={value.data.week} time={value.data.updatedAt}/>
      {value.data.items.filter(m=>filter==='all'||m.status===filter).map(m=><Card key={m.id}>
        <View style={S.between}><Text style={S.pill}>{m.category}</Text><Icon name={m.status==='completed'?'checkmark-circle':'flag-outline'}/></View>
        <Text style={S.heading}>{m.title}</Text><Note>{m.description}</Note>
        <View style={S.between}><Text style={S.label}>{m.progress} / {m.goal} {m.unit}</Text><Text style={S.note}>{m.status==='completed'?'완료':m.status==='expired'?'기간 종료':'진행 중'}</Text></View>
        <View accessibilityRole="progressbar" accessibilityValue={{min:0,max:m.goal,now:m.progress}} style={{height:8,borderRadius:8,backgroundColor:C.mint,overflow:'hidden'}}><View style={{height:8,backgroundColor:C.green,width:`${m.goal>0?Math.min(100,Math.max(0,m.progress/m.goal*100)):0}%`}}/></View>
        <Note>진행 상황과 완료 여부는 서버에서 확인한 결과입니다.</Note>
      </Card>)}
      {!value.data.items.some(m=>filter==='all'||m.status===filter)&&<Status value={{state:'empty'}}/>}
    </>}
  </>;
}

export function RankingPanel({value=unavailable,onRetry}:{value?:RemotePanel<RankingView>;onRetry?:()=>void}) {
  const [group,setGroup]=useState<'personal'|'department'>('personal');
  return <><Text style={S.title}>함께 만드는{ '\n'}더 큰 변화.</Text><Note>TEST 캠페인의 주간 탄소 감축 순위</Note>
    <View style={S.row}>{([['personal','개인'],['department','부서']] as const).map(([id,label])=><View key={id} style={{flex:1}}><Button title={label} quiet={group!==id} onPress={()=>setGroup(id)}/></View>)}</View>
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>
      <Updated week={value.data.week} time={value.data.updatedAt}/><Note>주간 집계 결과입니다. 실시간 순위가 아닙니다.</Note>
      {!value.data[group].length&&<Status value={{state:'empty'}}/>}
      {value.data[group].map(row=><Card key={row.id}><View style={S.between}>
        <View style={[S.row,{flex:1}]}><Text style={[S.metric,{width:36}]}>{row.rank}</Text><View style={{flex:1,gap:4}}><Text style={S.label}>{row.name}{'isMe' in row&&row.isMe?' (나)':''}</Text><Note>{row.carbonKg.toFixed(2)} kgCO₂e 감축</Note></View></View>
        {row.rank<=3&&<Icon name="trophy-outline" color="#ac862b"/>}
      </View></Card>)}
    </>}
  </>;
}

export function RewardPanel({value=unavailable,onRetry}:{value?:RemotePanel<RewardView>;onRetry?:()=>void}) {
  return <><Text style={S.title}>나의 캐노피 토큰</Text><Card><Icon name="wallet-outline" size={36}/><Stat label="보유 토큰" value={value.state==='ready'?`${value.data.balance.toLocaleString()} T`:'—'}/><Note>서버에서 지급이 확정된 토큰만 잔액에 반영됩니다.</Note></Card>
    <Text style={S.heading}>적립 내역</Text>
    {value.state!=='ready'?<Status value={value} onRetry={onRetry}/>:<>
      {!value.data.items.length&&<Status value={{state:'empty'}}/>}
      {value.data.items.map(row=><Card key={row.id}><View style={S.between}><View style={{flex:1,gap:6}}><Text style={S.label}>{row.title}</Text><Note>{new Date(row.time).toLocaleString('ko-KR')}</Note></View><View style={{alignItems:'flex-end',gap:6}}><Text style={S.heading}>{row.status==='paid'?`+${row.amount} T`:'처리 중'}</Text><Note>{row.status==='paid'?'지급 완료':'지급 확인 대기'}</Note></View></View></Card>)}
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
