import React,{useCallback,useEffect,useMemo,useRef,useState} from 'react';
import {ActivityIndicator,Pressable,RefreshControl,ScrollView,StyleSheet,Text,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import type {EngagementClient,EngagementDashboard,RankingScope,WeeklyMission} from '../engagementApi';

type Tab='missions'|'ranking';
const date=(value:string)=>new Date(value+'T00:00:00').toLocaleDateString('ko-KR',{month:'short',day:'numeric'});
const time=(value:string)=>new Date(value).toLocaleString('ko-KR',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
const categoryColor:Record<string,string>={challenge:'#d9653b',habit:'#287a5c',easy_win:'#3f75bd',explore:'#7559a8'};
export const missionProgress=(mission:WeeklyMission)=>Math.max(0,Math.min(100,Math.round(mission.achievement_rate*100)));

export function MissionRankingScreen({api,initialTab='missions',onBack}:{api:EngagementClient;initialTab?:Tab;onBack():void}){
  const [tab,setTab]=useState<Tab>(initialTab),[scope,setScope]=useState<RankingScope>('individual');
  const [data,setData]=useState<EngagementDashboard>(),[loading,setLoading]=useState(true),[refreshing,setRefreshing]=useState(false),[error,setError]=useState('');
  const alive=useRef(true);
  const load=useCallback(async(refresh=false)=>{
    refresh?setRefreshing(true):setLoading(true);setError('');
    try{const next=await api.loadDashboard();if(alive.current)setData(next);}
    catch(e){if(alive.current)setError((e as {status?:number}).status===403?'이 캠페인의 미션·랭킹을 볼 권한이 없습니다.':String(e instanceof Error?e.message:e));}
    finally{if(alive.current){setLoading(false);setRefreshing(false);}}
  },[api]);
  useEffect(()=>{alive.current=true;void load();return()=>{alive.current=false;};},[load]);
  const completed=useMemo(()=>data?.missions?.missions.filter(m=>m.completed).length??0,[data]);
  const ranking=data?.rankings[scope];
  return <SafeAreaView style={s.root}><View style={s.header}>
    <Pressable accessibilityRole="button" onPress={onBack}><Text style={s.back}>← 이동 기록</Text></Pressable><Text style={s.brand}>Canopy</Text><View style={{width:72}}/>
  </View><View style={s.tabs}>{(['missions','ranking'] as Tab[]).map(value=><Pressable key={value} accessibilityRole="tab" accessibilityState={{selected:tab===value}}
    onPress={()=>setTab(value)} style={[s.tab,tab===value&&s.tabOn]}><Text style={[s.tabText,tab===value&&s.tabTextOn]}>{value==='missions'?'주간 미션':'랭킹'}</Text></Pressable>)}</View>
  {loading?<View style={s.center}><ActivityIndicator color="#087f5b"/><Text style={s.note}>이번 주 정보를 불러오는 중입니다.</Text></View>:
  error?<View style={s.center}><Text accessibilityRole="alert" style={s.error}>{error}</Text><Pressable accessibilityRole="button" onPress={()=>void load()} style={s.primary}><Text style={s.primaryText}>다시 시도</Text></Pressable></View>:
  <ScrollView contentContainerStyle={s.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={()=>void load(true)} tintColor="#087f5b"/>}>
    {data?.source==='mock'&&<Text style={s.mock}>개발용 Mock 데이터</Text>}
    {tab==='missions'?<>
      <View style={s.hero}><Text style={s.eyebrow}>THIS WEEK</Text><Text style={s.heroTitle}>이번 주 미션 {completed}/{data?.missions?.missions.length??0}</Text>
        <Text style={s.heroNote}>{data?.missions?`${date(data.missions.week_start)} – ${date(data.missions.week_end)}`:'현재 부여된 미션이 없습니다.'}</Text>
        {!!data?.missions&&<View style={s.summaryTrack}><View style={[s.summaryFill,{width:`${data.missions.missions.length?completed/data.missions.missions.length*100:0}%` as `${number}%`}]} /></View>}
      </View>
      {data?.errors.missions?<SectionError message={data.errors.missions} onRetry={()=>void load()}/>:
      !data?.missions?<Empty title="아직 이번 주 미션이 없습니다." detail="Baseline 수집 중이어도 첫 주 미션은 별도로 발급될 수 있습니다. 잠시 후 다시 확인해 주세요."/>:
      <>{data.missions.profile_status_at_issue==='cold_start'&&<View style={s.info}><Text style={s.infoTitle}>첫 주 미션이에요</Text><Text style={s.note}>이동 기록이 없어도 네 가지 시작 미션이 자동으로 부여됩니다.</Text></View>}
      <Text style={s.sectionTitle}>자동 배정된 미션</Text><Text style={s.note}>서버 진행률을 그대로 표시합니다. 이동 완료와 보상 확정 시점은 다를 수 있습니다.</Text>
      {data.missions.missions.map(mission=><MissionCard key={mission.assignment_id} mission={mission}/>)}</>}
      {data?.errors.reward?<SectionError message={data.errors.reward} onRetry={()=>void load()}/>:
      data?.reward?<><View style={s.reward}><View><Text style={s.eyebrow}>WEEKLY POINTS</Text><Text style={s.rewardPoints}>{data.reward.total_points.toLocaleString('ko-KR')} P</Text></View>
        <Text style={s.badge}>{data.reward.status==='processing'?'일부 처리 중':data.reward.status==='settled'?'정산 완료':'내역 없음'}</Text></View>
      {!!data.reward.entries.length&&<View style={s.card}><Text style={s.sectionTitle}>포인트 내역</Text>{data.reward.entries.map(entry=><View key={entry.reward_id} style={s.rewardRow}>
        <View><Text style={s.rowTitle}>{entry.label}</Text><Text style={s.caption}>{time(entry.occurred_at)}</Text></View><Text style={entry.points<0?s.negative:s.points}>{entry.points>0?'+':''}{entry.points} P</Text></View>)}
        <Text style={s.caption}>갱신 {time(data.reward.updated_at)}{data.reward.policy_version?` · ${data.reward.policy_version}`:''}</Text></View>}</>:null}
    </>:<>
      <View style={s.hero}><Text style={s.eyebrow}>WEEKLY RANKING</Text><Text style={s.heroTitle}>{ranking?.snapshot_status==='finalized'?'주간 확정 순위':'순위 집계 중'}</Text>
        <Text style={s.heroNote}>{ranking?`${date(ranking.week_start)} – ${date(ranking.week_end)}`:'랭킹 정보를 불러오지 못했습니다.'}</Text></View>
      <View style={s.scope}>{(['individual','department'] as RankingScope[]).map(value=><Pressable key={value} accessibilityRole="button" accessibilityState={{selected:scope===value}}
        onPress={()=>setScope(value)} style={[s.scopeButton,scope===value&&s.scopeOn]}><Text style={[s.scopeText,scope===value&&s.scopeTextOn]}>{value==='individual'?'개인':'부서'}</Text></Pressable>)}</View>
      <View style={s.info}><Text style={s.infoTitle}>실시간 순위가 아닙니다</Text><Text style={s.note}>마감된 주간 Snapshot입니다. 승인된 보상 조정은 다음 Snapshot 갱신에 반영됩니다.</Text></View>
      {data?.errors[scope]?<SectionError message={data.errors[scope]!} onRetry={()=>void load()}/>:
      !ranking?<Empty title="랭킹 자료가 없습니다." detail="집계가 시작되면 이 화면에 표시됩니다."/>:
      ranking.snapshot_status==='in_progress'?<Empty title="이번 주 순위를 집계 중입니다." detail="확정 Snapshot이 생성되면 순위가 표시됩니다."/>:
      <View style={s.card}>{ranking.entries.length?ranking.entries.map(entry=><View key={entry.subject_id} style={[s.rankRow,entry.is_me&&s.me]}>
        <Text style={[s.rank,entry.rank<=3&&s.top]}>{entry.rank}</Text><Text style={s.rankName}>{entry.display_name}</Text><Text style={s.rankScore}>{entry.score.toLocaleString('ko-KR')} P</Text></View>):
        <Empty title="공개할 순위가 없습니다." detail="참여 조건과 공개 범위를 충족한 결과가 생기면 표시됩니다."/>}
        {!!ranking.generated_at&&<Text style={s.caption}>생성 {time(ranking.generated_at)}{ranking.policy_version?` · ${ranking.policy_version}`:''}</Text>}</View>}
    </>}
  </ScrollView>}</SafeAreaView>;
}

function MissionCard({mission}:{mission:WeeklyMission}){
  const progress=missionProgress(mission),color=categoryColor[mission.category_id]??'#287a5c';
  return <View style={s.card}><View style={s.cardTop}><Text style={[s.category,{color}]}>{mission.category_label}</Text><Text style={[s.badge,mission.completed&&s.completeBadge]}>{mission.completed?'완료':'진행 중'}</Text></View>
    <Text style={s.missionTitle}>{mission.mission_name}</Text>{!!mission.mission_description&&<Text style={s.note}>{mission.mission_description}</Text>}
    <View style={s.progressLabel}><Text style={s.rowTitle}>{mission.progress_count}/{mission.target_count}{mission.progress_unit}</Text><Text style={s.caption}>{progress}%</Text></View>
    <View style={s.track}><View style={[s.fill,{width:`${progress}%` as `${number}%`,backgroundColor:color}]}/></View>
  </View>;
}
function Empty({title,detail}:{title:string;detail:string}){return <View style={s.empty}><Text style={s.infoTitle}>{title}</Text><Text style={s.note}>{detail}</Text></View>;}
function SectionError({message,onRetry}:{message:string;onRetry():void}){return <View style={s.empty}><Text accessibilityRole="alert" style={s.error}>{message}</Text><Pressable accessibilityRole="button" onPress={onRetry} style={s.primary}><Text style={s.primaryText}>다시 시도</Text></Pressable></View>;}

const s=StyleSheet.create({root:{flex:1,backgroundColor:'#f6f8f6'},header:{height:56,paddingHorizontal:20,flexDirection:'row',alignItems:'center',justifyContent:'space-between',backgroundColor:'#fff'},
  back:{color:'#174c39',fontWeight:'600'},brand:{fontSize:18,fontWeight:'800',color:'#162922'},tabs:{flexDirection:'row',backgroundColor:'#fff',paddingHorizontal:20,borderBottomWidth:1,borderColor:'#e2e8e4'},
  tab:{flex:1,alignItems:'center',paddingVertical:14},tabOn:{borderBottomWidth:3,borderColor:'#087f5b'},tabText:{color:'#7a8680',fontWeight:'600'},tabTextOn:{color:'#087f5b'},
  content:{padding:20,gap:14,paddingBottom:48},center:{flex:1,alignItems:'center',justifyContent:'center',gap:18,padding:28},error:{color:'#ad2929',textAlign:'center',lineHeight:21},
  hero:{backgroundColor:'#0b674e',padding:22,borderRadius:20,gap:8},eyebrow:{fontSize:11,fontWeight:'800',letterSpacing:1.2,color:'#9fd7c3'},heroTitle:{fontSize:25,fontWeight:'800',color:'#fff'},heroNote:{color:'#d9efe7'},
  summaryTrack:{height:7,borderRadius:7,backgroundColor:'#488a75',overflow:'hidden',marginTop:8},summaryFill:{height:'100%',backgroundColor:'#d8f089'},mock:{alignSelf:'flex-start',fontSize:11,color:'#7a641d',backgroundColor:'#fff2bd',paddingHorizontal:9,paddingVertical:5,borderRadius:10},
  sectionTitle:{fontSize:18,fontWeight:'800',color:'#162922',marginTop:4},note:{fontSize:13,color:'#66736e',lineHeight:20},card:{backgroundColor:'#fff',padding:18,borderRadius:16,gap:12,borderWidth:1,borderColor:'#e4e9e6'},
  cardTop:{flexDirection:'row',justifyContent:'space-between',alignItems:'center'},category:{fontSize:12,fontWeight:'800'},badge:{fontSize:11,fontWeight:'700',color:'#675f25',backgroundColor:'#f4edc5',paddingHorizontal:9,paddingVertical:5,borderRadius:12},completeBadge:{color:'#176344',backgroundColor:'#dcefe6'},
  missionTitle:{fontSize:17,fontWeight:'800',color:'#1c2e27',lineHeight:24},progressLabel:{flexDirection:'row',justifyContent:'space-between'},rowTitle:{fontSize:14,fontWeight:'700',color:'#263c33'},caption:{fontSize:11,color:'#79857f'},
  track:{height:8,borderRadius:8,backgroundColor:'#e8eeea',overflow:'hidden'},fill:{height:'100%',borderRadius:8},
  info:{backgroundColor:'#e9f4ef',padding:16,borderRadius:14,gap:5},infoTitle:{fontSize:15,fontWeight:'800',color:'#174c39'},reward:{backgroundColor:'#fff',padding:18,borderRadius:16,flexDirection:'row',justifyContent:'space-between',alignItems:'center',borderWidth:1,borderColor:'#e4e9e6'},
  rewardPoints:{fontSize:25,fontWeight:'800',color:'#174c39'},rewardRow:{flexDirection:'row',justifyContent:'space-between',alignItems:'center',paddingVertical:8,borderBottomWidth:1,borderColor:'#edf1ee'},points:{fontWeight:'800',color:'#087f5b'},negative:{fontWeight:'800',color:'#ad2929'},
  scope:{flexDirection:'row',backgroundColor:'#e7ece9',padding:4,borderRadius:12},scopeButton:{flex:1,padding:11,alignItems:'center',borderRadius:9},scopeOn:{backgroundColor:'#fff'},scopeText:{color:'#718078',fontWeight:'700'},scopeTextOn:{color:'#174c39'},
  rankRow:{flexDirection:'row',alignItems:'center',paddingVertical:13,borderBottomWidth:1,borderColor:'#edf1ee',gap:12},me:{backgroundColor:'#eef7f2',marginHorizontal:-10,paddingHorizontal:10,borderRadius:10},rank:{width:28,textAlign:'center',fontSize:16,fontWeight:'700',color:'#768179'},top:{color:'#d18b2e'},rankName:{flex:1,fontWeight:'700',color:'#263c33'},rankScore:{fontWeight:'800',color:'#174c39'},
  empty:{padding:22,backgroundColor:'#fff',borderRadius:16,gap:6,alignItems:'center'},primary:{backgroundColor:'#087f5b',borderRadius:12,paddingVertical:14,paddingHorizontal:26},primaryText:{color:'#fff',fontWeight:'800'},
});
