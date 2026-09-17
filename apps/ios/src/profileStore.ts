import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {developerProfile,type Profile} from './service';
const key='canopy.local-profile.v1';
type Saved={profile:Profile;salt:string;verifier:string};
async function read():Promise<Saved|null>{const value=await SecureStore.getItemAsync(key);return value?JSON.parse(value):null;}
const digest=(salt:string,password:string)=>Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,salt+':'+password);
// 기기 내 화면 테스트 전용. 서버 로그인 또는 권한 부여에 사용 금지
export async function registerProfile(profile:Profile,password:string,code:string) {
  if(code.trim().toUpperCase()!=='TEST')throw Error('현재는 TEST 캠페인 코드로 참여할 수 있어요.');
  if(!profile.nickname.trim()||!/^\S+@\S+\.\S+$/.test(profile.email))throw Error('이름과 이메일을 확인해주세요.');
  if(password.length<8)throw Error('비밀번호를 8자 이상 입력해주세요.');
  if(await read())throw Error('이 기기에 저장된 프로필이 있습니다. 기존 이메일로 로그인해주세요.');
  const salt=Crypto.randomUUID();await SecureStore.setItemAsync(key,JSON.stringify({profile,salt,verifier:await digest(salt,password)}));
  return profile;
}
export async function loginProfile(email:string,password:string):Promise<Profile> {
  if(__DEV__ && email==='canopydev'&&password==='1234')return developerProfile;
  const saved=await read();
  if(!saved||saved.profile.email!==email.toLowerCase().trim()||saved.verifier!==await digest(saved.salt,password))throw Error('이메일 또는 비밀번호를 확인해주세요. 이 기기에서 만든 프로필로 로그인할 수 있어요.');
  return saved.profile;
}
export async function updateProfile(profile:Profile) {
  if(profile.role==='developer')return;
  const saved=await read();if(!saved||saved.profile.id!==profile.id)throw Error('로그인한 프로필을 확인해주세요.');
  await SecureStore.setItemAsync(key,JSON.stringify({...saved,profile}));
}
