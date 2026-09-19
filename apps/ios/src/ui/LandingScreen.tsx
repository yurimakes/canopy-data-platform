import Text from './AppText';
import React,{useEffect,useRef} from 'react';
import {AccessibilityInfo,Animated,Easing,Image,Platform,ScrollView,View} from 'react-native';
import {LinearGradient} from 'expo-linear-gradient';
import {SafeAreaView} from 'react-native-safe-area-context';
import {CanopyMascot} from './CanopyMascot';
import {Button,C,Note,S} from './theme';

// PoC 랜딩의 로고 등장, 민트 궤도, 캐릭터 입장 구성을 앱 로그인 진입점으로 연결
export function LandingScreen({onLogin,onSignup,onContinue,nickname,ready,error}:{onLogin():void;onSignup():void;onContinue?:()=>void;nickname?:string;ready:boolean;error?:string}){
  const letters=useRef(Array.from({length:6},()=>new Animated.Value(0))).current;
  const entrance=useRef(new Animated.Value(0)).current;
  useEffect(()=>{let alive=true;let animation:Animated.CompositeAnimation|undefined;
    void AccessibilityInfo.isReduceMotionEnabled().then(reduced=>{if(!alive)return;
      if(reduced){letters.forEach(v=>v.setValue(1));entrance.setValue(1);return;}
      animation=Animated.parallel([Animated.stagger(130,letters.map(v=>Animated.timing(v,{toValue:1,duration:700,easing:Easing.out(Easing.cubic),useNativeDriver:Platform.OS!=='web'}))),Animated.timing(entrance,{toValue:1,delay:350,duration:1400,easing:Easing.out(Easing.cubic),useNativeDriver:Platform.OS!=='web'})]);animation.start();
    }).catch(()=>{letters.forEach(v=>v.setValue(1));entrance.setValue(1);});
    return()=>{alive=false;animation?.stop();};},[]);
  return <SafeAreaView style={[S.root,{backgroundColor:'#f1f9f5'}]}>
    <ScrollView contentContainerStyle={{flexGrow:1,paddingHorizontal:28,paddingTop:65,paddingBottom:24,justifyContent:'space-between',gap:24}}>
      <View style={{alignItems:'center',gap:18}}>
        <Text style={{fontSize:9,letterSpacing:2.4,color:'#76968a',fontWeight:'600'}}>YOUR EVERYDAY GREEN JOURNEY</Text>
        <View accessibilityLabel="CANOPY" style={{flexDirection:'row',justifyContent:'center'}}>{Array.from('CANOPY').map((letter,i)=><Animated.Text key={i} style={{fontSize:49,fontWeight:'800',fontStyle:'italic',letterSpacing:1,color:'#087e5c',opacity:letters[i],transform:[{translateY:letters[i].interpolate({inputRange:[0,1],outputRange:[14,0]})}]}}>{letter}</Animated.Text>)}</View>
        <View style={{height:3,width:180,borderRadius:3,backgroundColor:'#e9b85c'}}/>
        <Text style={{fontSize:14,color:'#58766b'}}>작은 이동이 만드는 더 큰 변화</Text>
      </View>
      <View style={{height:275,alignItems:'center',justifyContent:'center'}}>
        <View pointerEvents="none" style={{position:'absolute',left:-16,right:-16,top:0,bottom:0,overflow:'hidden'}}>
          <Image source={require('../../assets/canopy-ui/landing-city-v2.png')} resizeMode="cover" style={{position:'absolute',width:'100%',height:500,bottom:-45,opacity:.8}}/>
          <LinearGradient colors={['#f1f9f5','#f1f9f500','#f1f9f500','#f1f9f5']} locations={[0,.28,.68,1]} style={{position:'absolute',inset:0}}/>
          <LinearGradient colors={['#f1f9f5','#f1f9f500','#f1f9f500','#f1f9f5']} locations={[0,.24,.76,1]} start={{x:0,y:0}} end={{x:1,y:0}} style={{position:'absolute',inset:0}}/>
        </View>
        <Animated.View style={{width:'100%',opacity:entrance,transform:[{translateY:entrance.interpolate({inputRange:[0,1],outputRange:[36,0]})},{scale:entrance.interpolate({inputRange:[0,1],outputRange:[.85,1]})}]}}><CanopyMascot pose="start" height={275}/></Animated.View>
      </View>
      <View style={{gap:10}}>
        {!!error&&<Note error>{error}</Note>}
        {nickname&&onContinue&&<Button title={`${nickname}님으로 계속하기`} disabled={!ready} onPress={onContinue}/>}
        <Button title={nickname?'다른 계정으로 로그인':'로그인'} quiet={!!nickname} onPress={onLogin}/>
        <Button title="회원가입" quiet onPress={onSignup}/>
        <Text style={[S.note,{fontSize:11,textAlign:'center',marginTop:8}]}>나의 계정으로 여정과 캠페인을 이어가세요.</Text>
      </View>
    </ScrollView>
  </SafeAreaView>;
}
