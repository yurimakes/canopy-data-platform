import React,{useState} from 'react';
import {View,Pressable,ScrollView} from 'react-native';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import {ServiceScreen,type ServiceProps} from './ServiceScreen';
import {LandingScreen} from './LandingScreen';
import {AuthScreen} from './AuthScreen';
import {PopulationPreview} from './PopulationPreview';
import {JourneyInfoPanel} from './JourneyInfoPanel';
import {CanopyMascot} from './CanopyMascot';
import {Button,S} from './theme';
import {RewardCelebration} from './RewardExperience';
import Text from './AppText';
import {C} from './theme';
import type {Profile} from '../service';
export default function DesignPreview(){
 const [page,setPage]=useState('앱'),[celebrate,setCelebrate]=useState(false),[profile,setProfile]=useState<Profile>({id:'preview-me',nickname:'민철',email:'hello@canopy.example',role:'user',campaignCode:'MSDS',home:{name:'우리 집',latitude:36.79,longitude:127.14},work:{name:'캠퍼스',latitude:36.80,longitude:127.15}});
 const [missionDone,setMissionDone]=useState(false);
 const time='2026-09-21T09:00:00Z',noop=()=>{};
 const props:ServiceProps={profile,onProfile:async p=>setProfile(p),trips:[],events:[],route:null,onCollectionMode:noop,onRoute:noop,onSelect:noop,onBack:()=>setPage('시작'),mode:null,phase:'idle',ready:true,count:0,duration:'00:00',accuracy:null,error:'',onMode:noop,onStart:noop,onStop:noop,onExport:noop,canExport:false,sharing:false,onFeedback:async()=>{},preview:true,
 baseline:{state:'ready',data:{status:'collecting',updatedAt:time,personalKg:null,globalKg:null,reason:'',trips:4,observationDays:2}},
 missions:{state:'ready',data:{week:'2026-09-21',updatedAt:time,items:[{id:'preview-walk',title:'가까운 곳은 두 발로',category:'걷기',description:'2km 이상 친환경 이동을 3번 기록해요.',progress:2,goal:3,unit:'회',rewardPoints:10,status:'active'},{id:'preview-bus',title:'이번 주, 버스 한 번',category:'새로운 도전',description:'버스로 이동하는 여정을 기록해요.',progress:missionDone?1:0,goal:1,unit:'회',rewardPoints:5,status:missionDone?'claimable':'active'}]}},
 ranking:{state:'ready',data:{week:'2026-09-21',updatedAt:time,personal:[{id:'a',name:'초록하루',rank:1,carbonKg:1,points:320},{id:'b',name:'숲길산책',rank:2,carbonKg:2,points:280},{id:'preview-me',name:profile.nickname,rank:3,carbonKg:2,points:240,isMe:true,avatarDataUri:profile.avatarDataUri}],department:[{id:'d',name:'데이터팀',rank:1,carbonKg:3,points:840}]}},
 rewards:{state:'ready',data:{balance:240,items:[{id:'r1',title:'오늘의 가벼운 출근',time,amount:12,kind:'trip',status:'paid'},{id:'r2',title:'두 발로 만든 변화',time,amount:10,kind:'mission',status:'paid'},{id:'r3',title:'주간 랭킹 3위',time,amount:20,kind:'ranking',status:'paid'}]}},notifications:{state:'ready',data:{unread:0,items:[]}}};
 return <SafeAreaProvider><View style={{flex:1,backgroundColor:C.paper}}><View style={{flexWrap:'wrap',gap:8,padding:7,backgroundColor:'#D7F88B',flexDirection:'row',alignItems:'center',justifyContent:'space-between'}}><Text style={{fontSize:10}}>디자인 미리보기 · 예시 데이터</Text><View style={{flexDirection:'row',gap:14}}>{['앱','시작','경로','이동','보상','달성'].map(v=><Pressable key={v} onPress={()=>v==='보상'?setCelebrate(true):v==='달성'?setMissionDone(v=>!v):setPage(v)} accessibilityRole="button"><Text style={{fontSize:12,fontWeight:'700'}}>{v}</Text></Pressable>)}</View></View>{page==='시작'?<AuthScreen onEnter={()=>setPage('앱')}/>:page==='경로'?<ScrollView contentContainerStyle={S.scroll}><Text style={S.title}>출발할 준비,{ '\n'}되셨나요?</Text><PopulationPreview baseline={props.baseline} route={{id:'preview-route',provider:'tmap',searchedAt:time,minutes:24,distance_m:3200,fare:1500,legs:[],from:profile.home!,to:profile.work!,expectedKg:.439,baselineRateG:137.43,baselineSource:'KTDB'}}/><Button title="이동 화면 보기" onPress={()=>setPage('이동')}/></ScrollView>:page==='이동'?<View style={{flex:1}}><View style={{flex:1,backgroundColor:C.mint,alignItems:'center',justifyContent:'center',gap:12}}><View style={{width:130,height:180}}><CanopyMascot pose="walk" animated height={180}/></View><Text style={S.note}>걷기 모션 예시 · 실제 지도는 iPhone에서 표시</Text></View><JourneyInfoPanel p={{active:false,events:[],duration:'12:34'}}/><View style={{padding:16}}><Button title="여정 종료 예시" onPress={()=>setCelebrate(true)}/></View></View>:<ServiceScreen {...props}/ >}{celebrate&&<RewardCelebration amount={12} title="여정 탄소 절감 보상" onClose={()=>setCelebrate(false)}/>}</View></SafeAreaProvider>;
}
