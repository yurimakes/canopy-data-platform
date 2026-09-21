import type {Profile} from './service';
import {accountConfig} from './accountConfig';
import {AccountError,accountRequest,accountUrl,checkedProfile,checkedSession} from './accountClient';
import {loadSession,saveSession,session} from './accountSession';

export async function registerProfile(profile:Profile,password:string,code:string){
  const config=accountConfig();
  const result=checkedSession(await accountRequest(config,'signup','POST',{
    email:profile.email,password,nickname:profile.nickname,campaign_code:code,home:profile.home,work:profile.work,
  }),config);
  await saveSession(result);return result.profile;
}
export async function loginProfile(email:string,password:string):Promise<Profile>{
  const config=accountConfig();
  const result=checkedSession(await accountRequest(config,'login','POST',{email,password}),config);
  await saveSession(result);return result.profile;
}
export async function restoreProfile():Promise<Profile|null>{
  const saved=await loadSession();if(!saved)return null;
  const config=accountConfig();
  if(saved.api_url!==accountUrl(config)){await saveSession(null);return null;}
  try {
    const profile=checkedProfile(await accountRequest(config,'me','GET',undefined,saved.access_token));
    if(profile.role==='developer')await accountRequest(config,'developer','GET',undefined,saved.access_token);
    await saveSession({...saved,profile});return profile;
  }catch(e){if(e instanceof AccountError&&[401,403].includes(e.status)){await saveSession(null);return null;}throw e;}
}
export async function updateProfile(profile:Profile){
  const saved=session();if(!saved||saved.profile.id!==profile.id)throw Error('다시 로그인해주세요.');
  const result=checkedProfile(await accountRequest(accountConfig(),'me','PATCH',{
    nickname:profile.nickname,home:profile.home,work:profile.work,department_name:profile.department_name??'',
  },saved.access_token));
  await saveSession({...saved,profile:result});return result;
}
export async function logoutProfile(){
  const saved=await loadSession();
  if(saved){try{await accountRequest(accountConfig(),'logout','POST',{},saved.access_token);}catch(e){if(!(e instanceof AccountError&&e.status===401))throw e;}}
  await saveSession(null);
}
