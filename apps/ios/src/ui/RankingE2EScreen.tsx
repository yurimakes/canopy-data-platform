import React,{useEffect,useState} from 'react';
import {Pressable,ScrollView,Text,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {loadRanking} from '../rankingClient';
import {RankingPanel,type RankingView,type RemotePanel} from './CommunityPanels';
import {C,Icon,S} from './theme';

export function RankingE2EScreen(){
  const [value,setValue]=useState<RemotePanel<RankingView>>({state:'loading'});

  function refresh(){
    setValue({state:'loading'});
    void loadRanking('pipeline_test_weekly_20260918_u01')
      .then(setValue)
      .catch(()=>setValue({state:'error',message:'랭킹 API 호출에 실패했습니다.'}));
  }

  useEffect(()=>{refresh();},[]);

  return <SafeAreaView style={S.root}>
    <View style={[S.between,{paddingHorizontal:20,minHeight:58,backgroundColor:C.white}]}>
      <View style={S.row}><Icon name="leaf" size={25}/><Text style={[S.heading,{fontSize:22,color:C.green}]}>Canopy Ranking E2E</Text></View>
      <Pressable accessibilityRole="button" onPress={refresh} style={{padding:10}}>
        <Icon name="refresh-outline" size={21} color={C.deep}/>
      </Pressable>
    </View>
    <ScrollView contentContainerStyle={S.scroll}>
      <Text style={S.pill}>개발 검증 전용</Text>
      <Text style={S.title}>실제 주간 랭킹</Text>
      <Text style={S.note}>Cosmos → Azure Function → iPhone 표시 경로를 확인합니다.</Text>
      <RankingPanel value={value} onRetry={refresh}/>
    </ScrollView>
  </SafeAreaView>;
}
