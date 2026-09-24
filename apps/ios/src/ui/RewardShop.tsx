import {PreviewIcon} from './PreviewIcon';
import React,{useState} from 'react';
import {Image,Modal,Pressable,View} from 'react-native';
import {SafeAreaView} from 'react-native-safe-area-context';
import {LinearGradient} from 'expo-linear-gradient';
import Text from './AppText';
import {C,S,Button,Note} from './theme';
import {Eyebrow,Segmented} from './DesignPrimitives';
import {CanopyMascot} from './CanopyMascot';
import type {RemotePanel,RewardView} from './CommunityPanels';

const products=[
 {id:'coffee',brand:'데모 카페',name:'아이스 아메리카노',detail:'예시 음료',cost:1500,category:'cafe',color:'#EAF2EA'},
 {id:'cu',brand:'데모 금액권',name:'모바일 금액권',detail:'5,000원권',cost:2000,category:'voucher',color:'#F0E9F8'},
 {id:'npay',brand:'데모 포인트',name:'포인트 교환 예시',detail:'5,000원',cost:5000,category:'voucher',color:'#E4F4E8'},
];
export function RewardShop({value}:{value?:RemotePanel<RewardView>}){
 const [category,setCategory]=useState('all'),[selected,setSelected]=useState<typeof products[number]|null>(null);
 return <><Eyebrow>MY CANOPY WALLET</Eyebrow>
 <View style={{backgroundColor:'#274D3D',borderRadius:26,borderBottomLeftRadius:10,borderBottomRightRadius:10,padding:24}}><Text style={{fontSize:10,color:'#C6D4B0',letterSpacing:1}}>CANOPY TOKEN</Text><View style={S.between}><Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.55} style={{flex:1,fontFamily:'Jua',fontSize:43,color:'#F3F5D8'}}>{value?.state==='ready'?value.data.balance.toLocaleString('ko-KR',{maximumFractionDigits:2}):'—'}<Text style={{fontFamily:'Nunito_800ExtraBold',fontSize:22}}> T</Text></Text><View style={{width:85}}><CanopyMascot pose="coin" height={95} animated/></View></View><View style={{borderTopWidth:1,borderStyle:"dashed",borderColor:"#73916B",paddingTop:16}}><Text style={{fontSize:11,color:"#D1DDBC"}}>작은 실천의 보상</Text></View></View>
 <View style={S.between}><Text style={S.heading}>일상 속 작은 선물</Text><Text style={{fontSize:11,color:C.green,backgroundColor:C.mint,borderRadius:9,padding:7}}>미리보기</Text></View>
 <Note>교환 기능 준비 중입니다. 상품과 필요 토큰은 예시입니다.</Note>
 <Segmented items={[{id:'all',label:'전체'},{id:'cafe',label:'카페'},{id:'voucher',label:'금액권'}]} value={category} onChange={setCategory}/>
 <View style={{flexDirection:'row',flexWrap:'wrap',gap:12}}>{products.filter(p=>category==='all'||p.category===category).map(p=><Pressable key={p.id} accessibilityRole="button" accessibilityLabel={p.brand+' '+p.name+' 미리보기'} onPress={()=>setSelected(p)} style={{width:'47%',flexGrow:1,maxWidth:'49%',backgroundColor:'white',borderRadius:24,padding:12,gap:12,borderWidth:1,borderColor:'#FFFFFF',boxShadow:'0 5px 20px #1A41300B'}}>
  <View style={{height:104,backgroundColor:p.color,borderRadius:18,alignItems:'center',justifyContent:'center'}}>{p.id==='coffee'?<PreviewIcon name="coffee" size={48}/>:<View style={{padding:10,borderRadius:12,backgroundColor:'#315B48',width:'85%',minHeight:78,justifyContent:'center',boxShadow:'0 5px 12px #153A2520'}}><Text numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.65} style={{fontFamily:'Nunito_800ExtraBold',fontSize:26,color:'white'}}>{p.brand}</Text><Text style={{fontSize:10,color:'white',marginTop:5}}>GIFT CARD</Text></View>}</View>
  <View style={{gap:4}}><Text style={{fontSize:10,color:C.muted}}>{p.brand}</Text><Text style={{fontSize:13,lineHeight:20,color:C.deep,fontWeight:'600'}}>{p.name}</Text><Text style={{fontSize:11,color:C.muted}}>{p.detail}</Text><Text style={{fontFamily:'Nunito_800ExtraBold',fontSize:19,color:C.deep,marginTop:6}}>{p.cost.toLocaleString()} T</Text></View>
 </Pressable>)}</View>
 <Modal visible={!!selected} transparent animationType="slide" onRequestClose={()=>setSelected(null)}><View style={{flex:1,backgroundColor:'#102D2466',justifyContent:'flex-end'}}><SafeAreaView edges={['bottom']} style={{backgroundColor:C.paper,borderTopLeftRadius:30,borderTopRightRadius:30,padding:26,gap:18}}><Text style={S.heading}>{selected?.brand} {selected?.name}</Text><Note>리워드 교환 화면의 예시입니다. 지금은 토큰이 차감되거나 상품이 발급되지 않습니다.</Note><Button title="확인" onPress={()=>setSelected(null)}/></SafeAreaView></View></Modal>
 </>;
}
