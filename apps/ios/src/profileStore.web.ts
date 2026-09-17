import {developerProfile,type Profile} from './service';
import * as Crypto from 'expo-crypto';
// 브라우저는 화면 확인 전용. 실제 계정, 비밀번호, 서버 인증 저장 제외
let profile:Profile|undefined;
let verifier='';
const digest=(value:string)=>Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256,value);
export async function registerProfile(p:Profile,password:string,code:string){if(code.trim().toUpperCase()!=='TEST')throw Error('TEST 코드를 입력해주세요.');if(!p.nickname.trim()||!/^\S+@\S+\.\S+$/.test(p.email))throw Error('이름과 이메일을 확인해주세요.');if(password.length<8)throw Error('비밀번호를 8자 이상 입력해주세요.');profile=p;verifier=await digest(p.id+password);return p;}
export async function loginProfile(email:string,password:string){if(__DEV__&&email==='canopydev'&&password==='1234')return developerProfile;if(profile&&profile.email===email&&verifier===await digest(profile.id+password))return profile;throw Error('이메일 또는 비밀번호를 확인해주세요. 브라우저에서는 새로고침하면 프로필이 초기화됩니다.');}
export async function updateProfile(p:Profile){profile=p;}
