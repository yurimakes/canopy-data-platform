import React,{useState} from 'react';
import {Image,KeyboardAvoidingView,Platform,Pressable,ScrollView,Text,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import * as Crypto from 'expo-crypto';
import {loginProfile,registerProfile} from '../profileStore';
import type {Profile,Place} from '../service';
import {PlacePicker} from './RoutePlanner';
import {Button,C,Fade,Floating,Field,Icon,Note,S} from './theme';
export function AuthScreen({onEnter,error:runtimeError,ready=true}:{onEnter(p:Profile):void;error?:string;ready?:boolean}) {
  const [page,setPage]=useState<'welcome'|'login'|'signup'>('welcome');
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[nickname,setNickname]=useState(''),[code,setCode]=useState('');
  const [visible,setVisible]=useState(false),[agreed,setAgreed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [step,setStep]=useState(0),[home,setHome]=useState<Place|null>(null),[work,setWork]=useState<Place|null>(null);
  async function submit(){if(busy)return;setBusy(true);setError('');try{
    if(page==='signup'&&!agreed)throw Error('기기 내 프로필 저장 안내를 확인해주세요.');
    if(page==='signup'&&step===0){
      if(!nickname.trim()||!/^\S+@\S+\.\S+$/.test(email.trim()))throw Error('이름과 이메일을 확인해주세요.');
      if(password.length<8)throw Error('비밀번호를 8자 이상 입력해주세요.');
      if(code.trim().toUpperCase()!=='TEST')throw Error('현재는 TEST 캠페인 코드로 참여할 수 있어요.');
      setStep(1);return;
    }
    const result=page==='signup'?await registerProfile({id:Crypto.randomUUID(),nickname:nickname.trim(),email:email.trim().toLowerCase(),role:'user',campaignCode:'TEST',home,work},password,code):await loginProfile(email.trim(),password);
    onEnter(result);
  }catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  function navigate(p:typeof page){setPage(p);setStep(0);setError('');setPassword('');}
  return <SafeAreaView style={[S.root,{backgroundColor:page==='welcome'?'#eaf6ef':C.paper}]}><KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[S.scroll,{flexGrow:1,justifyContent:'center',paddingVertical:36}]}>
      <Fade key={page}>
      <View style={S.between}><View style={S.row}><Icon name="leaf" size={27}/><Text style={{fontSize:23,fontWeight:'800',letterSpacing:2,color:C.deep}}>CANOPY</Text></View>{page!=='welcome'&&<Pressable accessibilityRole="button" accessibilityLabel="처음으로" onPress={()=>navigate('welcome')} style={{padding:12}}><Icon name="close"/></Pressable>}</View>
      {page==='welcome'?<>
        <Floating><Image source={require('../../assets/canopy-ui/landing-mascot-point.png')} style={{width:'100%',height:280}} resizeMode="contain"/></Floating>
        <Text style={[S.title,{fontSize:37,lineHeight:48}]}>매일의 이동이,{ '\n'}더 나은 내일로.</Text>
        <Text style={[S.note,{fontSize:16,lineHeight:26}]}>익숙한 출근길에 작은 변화를 더해보세요.{ '\n'}나의 여정부터 함께 만드는 변화까지.</Text>
        <View style={{gap:10,marginTop:18}}><Button title="캐노피 시작하기" onPress={()=>navigate('signup')}/><Button title="이미 계정이 있어요" quiet onPress={()=>navigate('login')}/></View>
      </>:page==='signup'&&step===1?<>
        <Text style={S.pill}>2 / 2  출퇴근 장소</Text>
        <Text style={S.title}>매일의 출발과{ '\n'}도착을 알려주세요.</Text>
        <Note>저장한 장소로 출퇴근 경로를 빠르게 찾을 수 있어요. 나중에 설정하거나 다른 목적지로 이동해도 괜찮아요.</Note>
        <PlacePicker title="집" value={home} onPick={setHome}/><PlacePicker title="직장" value={work} onPick={setWork}/>
        <Note>출근은 집 → 직장, 퇴근은 직장 → 집으로 안내합니다. 장소를 입력해도 이동이 자동으로 시작되지는 않아요.</Note>
        {!!(error||runtimeError)&&<Note error>{error||runtimeError}</Note>}
        <Button title={home&&work?'설정하고 시작하기':'장소는 나중에 설정하고 시작하기'} busy={busy} disabled={!ready} onPress={()=>void submit()}/>
        <Button title="이전 단계" quiet disabled={busy} onPress={()=>{setStep(0);setError('');}}/>
      </>:<>
        {page==='signup'&&<Text style={S.pill}>1 / 2  프로필</Text>}
        <Text style={[S.title,{marginTop:28}]}>{page==='signup'?'반가워요!\n함께 시작해볼까요?':'다시 만나 반가워요'}</Text>
        <Note>{page==='signup'?'프로필을 만들고 TEST 캠페인에 참여하세요.':'나의 일상 속 초록빛 여정을 이어가세요.'}</Note>
        {page==='signup'&&<Field label="이름 또는 닉네임" value={nickname} onChangeText={setNickname} placeholder="어떻게 불러드릴까요?" maxLength={30}/>}
        <Field label={page==='login'?'이메일 또는 개발자 ID':'이메일'} value={email} onChangeText={setEmail} autoCapitalize="none" autoCorrect={false} keyboardType="email-address" placeholder="canopy@example.com" maxLength={120}/>
        <Field label="비밀번호" value={password} onChangeText={setPassword} secureTextEntry={!visible} placeholder={page==='signup'?'8자 이상 입력':'비밀번호 입력'} autoCapitalize="none" maxLength={128}/>
        <Pressable accessibilityRole="button" onPress={()=>setVisible(!visible)}><Text style={S.link}>{visible?'비밀번호 가리기':'비밀번호 보기'}</Text></Pressable>
        {page==='signup'&&<><Field label="캠페인 코드" value={code} onChangeText={setCode} autoCapitalize="characters" placeholder="TEST" maxLength={20}/><Note>집과 직장 위치는 다음 화면에서 설정할 수 있어요.</Note>
          <Pressable accessibilityRole="checkbox" aria-checked={agreed} accessibilityState={{checked:agreed}} onPress={()=>setAgreed(!agreed)} style={S.row}><Icon name={agreed?'checkbox':'square-outline'}/><Text style={[S.note,{flex:1}]}>프로필이 이 기기에 저장되는 테스트 버전임을 확인했습니다.</Text></Pressable></>}
        {!!(error||runtimeError)&&<Note error>{error||runtimeError}</Note>}
        <Button title={page==='signup'?'다음: 출퇴근 장소':'로그인'} busy={busy} disabled={!ready} onPress={()=>void submit()}/>
        <Button quiet title={page==='signup'?'이미 계정이 있어요':'처음이에요. 가입하기'} onPress={()=>navigate(page==='signup'?'login':'signup')}/>
      </>}
      <Note>현재는 기기 내 프로필로 사용하는 테스트 버전입니다. 실제 회원가입과 계정 인증은 추후 연결됩니다.</Note>
      </Fade>
    </ScrollView></KeyboardAvoidingView></SafeAreaView>;
}
