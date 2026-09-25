import React,{useState} from 'react';
import {Image,Modal,Pressable,ScrollView,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import Text from './AppText';
import {C,S,Button,Note} from './theme';
import {Eyebrow,Segmented} from './DesignPrimitives';
import {CanopyMascot} from './CanopyMascot';
import type {RemotePanel,RewardView} from './CommunityPanels';

const products=[
 {id:'coffee',brand:'데모 카페',name:'아이스 아메리카노',detail:'예시 음료',cost:150,category:'cafe',color:'#EAF2EA'},
 {id:'cu',brand:'데모 금액권',name:'모바일 금액권',detail:'5,000원권',cost:200,category:'voucher',color:'#F0E9F8'},
 {id:'npay',brand:'데모 포인트',name:'포인트 교환 예시',detail:'5,000원',cost:200,category:'voucher',color:'#E4F4E8'},
];
export function RewardShop({value}:{value?:RemotePanel<RewardView>}){
 const [redeemed,setRedeemed]=useState(false);
 const [category,setCategory]=useState('all'),[selected,setSelected]=useState<typeof products[number]|null>(null);
 return <><Eyebrow>MY CANOPY WALLET</Eyebrow>
 <View style={{backgroundColor:'#274D3D',borderRadius:26,borderBottomLeftRadius:10,borderBottomRightRadius:10,padding:24}}><Text style={{fontSize:10,color:'#C6D4B0',letterSpacing:1}}>CANOPY TOKEN</Text><View style={S.between}><Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.55} style={{flex:1,fontFamily:'Jua',fontSize:43,color:'#F3F5D8'}}>{value?.state==='ready'?value.data.balance.toLocaleString('ko-KR',{maximumFractionDigits:2}):'—'}<Text style={{fontFamily:'Nunito_800ExtraBold',fontSize:22}}> T</Text></Text><View style={{width:85}}><CanopyMascot pose="coin" height={95} animated/></View></View><View style={{borderTopWidth:1,borderStyle:"dashed",borderColor:"#73916B",paddingTop:16}}><Text style={{fontSize:11,color:"#D1DDBC"}}>작은 실천의 보상</Text></View></View>
 <View style={S.between}><Text style={S.heading}>일상 속 작은 선물</Text></View>
 <Note>모아둔 토큰으로 나에게 작은 선물을 건네보세요.</Note>
 <Segmented items={[{id:'all',label:'전체'},{id:'cafe',label:'카페'},{id:'voucher',label:'금액권'}]} value={category} onChange={setCategory}/>
 <View style={{flexDirection:'row',flexWrap:'wrap',gap:12}}>{products.filter(p=>category==='all'||p.category===category).map(p=><Pressable key={p.id} accessibilityRole="button" accessibilityLabel={p.brand+' '+p.name+' 상세보기'} onPress={()=>{setRedeemed(false);setSelected(p);}} style={{width:'47%',flexGrow:1,maxWidth:'49%',backgroundColor:'white',borderRadius:24,padding:12,gap:12,borderWidth:1,borderColor:'#FFFFFF',boxShadow:'0 5px 20px #1A41300B'}}>
  <View style={{height:104,backgroundColor:p.color,borderRadius:18,alignItems:'center',justifyContent:'center'}}>{p.id==='coffee'?<Image source={require('../../assets/reward-products/coffee.png')} resizeMode="contain" style={{width:110,height:104}}/>:<View style={{width:'85%',minHeight:78,padding:12,borderRadius:12,backgroundColor:'#315B48',alignItems:'center',justifyContent:'center'}}><Text style={{fontSize:24,color:'white'}}>{p.id==='cu'?'5,000':'P'}</Text><Text style={{fontSize:10,color:'white',marginTop:5}}>DEMO</Text></View>}</View>
  <View style={{gap:4}}><Text style={{fontSize:10,color:C.muted}}>{p.brand}</Text><Text style={{fontSize:13,lineHeight:20,color:C.deep,fontWeight:'600'}}>{p.name}</Text><Text style={{fontSize:11,color:C.muted}}>{p.detail}</Text><Text style={{fontFamily:'Nunito_800ExtraBold',fontSize:19,color:C.deep,marginTop:6}}>{p.cost.toLocaleString()} T</Text></View>
 </Pressable>)}</View>
 <Modal visible={!!selected} transparent animationType="slide" onRequestClose={()=>setSelected(null)}><View style={{flex:1,backgroundColor:'#102D2470',justifyContent:'flex-end'}}><SafeAreaView edges={['bottom']} style={{backgroundColor:C.paper,borderTopLeftRadius:32,borderTopRightRadius:32,maxHeight:'92%',width:'100%',maxWidth:480,alignSelf:'center'}}><ScrollView contentContainerStyle={{padding:24,gap:18}}>
 <View style={S.between}><Text style={S.heading}>{redeemed?'나의 선물 교환권':'상품 상세정보'}</Text><Pressable accessibilityRole="button" accessibilityLabel="상품 창 닫기" onPress={()=>setSelected(null)} style={{padding:10}}><Text style={S.label}>닫기 ×</Text></Pressable></View>
 {selected&&<><View style={{backgroundColor:selected.color,borderRadius:24,padding:16,alignItems:'center'}}>{selected.id==='coffee'?<Image source={require('../../assets/reward-products/coffee.png')} resizeMode="contain" style={{width:110,height:104}}/>:<View style={{width:'85%',minHeight:78,padding:12,borderRadius:12,backgroundColor:'#315B48',alignItems:'center',justifyContent:'center'}}><Text style={{fontSize:24,color:'white'}}>{selected.id==='cu'?'5,000':'P'}</Text><Text style={{fontSize:10,color:'white',marginTop:5}}>DEMO</Text></View>}</View>
 <View style={{alignItems:'center',gap:7}}><Text style={{fontSize:12,color:C.green}}>{selected.brand}</Text><Text style={{fontSize:23,color:C.deep,textAlign:'center'}}>{selected.name}</Text><Note>{selected.detail}</Note></View>
 {redeemed?<View style={{backgroundColor:'white',borderRadius:24,padding:22,gap:14,alignItems:'center',borderWidth:1,borderColor:C.line}}><Text style={{fontSize:12,color:C.green}}>작은 실천이, 달콤한 선물로</Text><View accessibilityLabel="예시 바코드 · 실제 사용 불가" style={{height:65,width:'100%',flexDirection:'row',justifyContent:'center',gap:2}}>{Array.from({length:52},(_,i)=><View key={i} style={{height:i%7===0?65:58,width:[2,1,3,1,2,4,1][i%7],backgroundColor:C.deep}}/>)}</View><Text style={{fontSize:16,letterSpacing:3,color:C.deep}}>DEMO 2026 0925</Text><Text style={{fontSize:12,color:C.muted}}>미리보기 전용 · 매장에서 사용할 수 없어요</Text></View>:<><View style={[S.between,{backgroundColor:'white',borderRadius:18,padding:18}]}><Text style={S.label}>필요한 토큰</Text><Text style={{fontSize:27,color:C.deep}}>{selected.cost} T</Text></View><Note>차곡차곡 모은 토큰을 일상 속 작은 선물로 바꿔보세요.</Note></>}
 <Text style={{fontSize:11,color:C.muted,textAlign:'center'}}>예시 체험이에요. 실제 토큰은 차감되지 않아요.</Text>
 <Button title={redeemed?'지갑으로 돌아가기':'교환하기'} onPress={()=>redeemed?setSelected(null):setRedeemed(true)}/></>}
 </ScrollView></SafeAreaView></View></Modal>
 </>;
}
