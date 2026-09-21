import * as TaskManager from 'expo-task-manager';
import * as Crypto from 'expo-crypto';
import Constants from 'expo-constants';
import { openDatabaseAsync } from 'expo-sqlite';
import type { LocationObject } from 'expo-location';
import { Storage } from './storage';
import { Uploader, type ApiConfig } from './upload';
import { TripApi, type TripConfig } from './tripApi';
import {loadSession,session} from './accountSession';

export const LOCATION_TASK = 'canopy-gps-background-v1';
let storage: Promise<Storage> | undefined;
export function getStorage() {
  return storage ??= (async () => {
    const db=new Storage(await openDatabaseAsync(Constants.expoConfig?.extra?.localOnly?'canopy-local-collector.db':'canopy-collector.db'));
    await db.init(Crypto.randomUUID,new Date().toISOString());
    return db;
  })().catch(e=>{storage=undefined;throw e;});
}
export function apiConfig(): ApiConfig | null {
  const extra=Constants.expoConfig?.extra;
  return extra?.gpsApiUrl && extra?.gpsFunctionKey ? {url:extra.gpsApiUrl,functionKey:extra.gpsFunctionKey,allowLocalHttp:__DEV__&&extra.localOnly===true} : null;
}
let uploader: Uploader | undefined;
export async function getUploader() {return uploader ??= new Uploader(await getStorage(),apiConfig,Crypto.randomUUID,Date.now,fetch,async(event,url)=>{
  await loadSession();
  const saved=session(), configured=Constants.expoConfig?.extra?.tripApiUrl?.replace(/\/+$/,'');
  if(!saved||saved.api_url!==configured||saved.profile.id!==event.user_id||new URL(saved.api_url).origin!==new URL(url).origin)
    throw new Error('GPS를 기록한 계정으로 로그인하면 전송을 재개합니다.');
  return saved.access_token;
});}
let tripApi: TripApi | undefined;
export function tripConfig():TripConfig|null {
  const extra=Constants.expoConfig?.extra;
  const saved=session();
  const matches=saved?.api_url===extra?.tripApiUrl?.replace(/\/+$/,'');
  return extra?.tripApiUrl ? {url:extra.tripApiUrl,token:matches?saved!.access_token:'',userId:matches?saved!.profile.id:undefined,
    functionKey:extra.tripFunctionKey||extra.gpsFunctionKey,allowLocalHttp:__DEV__ && extra.tripAllowLocalHttp===true}:null;
}
export async function getTripApi() {await loadSession();return tripApi ??= new TripApi(await getStorage(),tripConfig,Crypto.randomUUID);}

// Imported by index.ts before React mounts; works when iOS wakes the JS task alone.
TaskManager.defineTask<{locations:LocationObject[]}>(LOCATION_TASK, async ({data,error}) => {
  const db=await getStorage();
  if(error) {
    await db.setActiveError('백그라운드 GPS 오류: '+error.message);
    const active=await db.active();
    await db.diagnostic(active?.trip_id??null,{recorded_at:new Date().toISOString(),kind:'background_error',detail:error.message});
    return;
  }
  if(!data?.locations?.length) return;
  try {
    await db.appendBackground(data.locations,new Date().toISOString(),Crypto.randomUUID);
  } catch(e) {
    try {await db.setActiveError('GPS 로컬 저장 실패: '+String(e));} catch {}
    throw e; // Never report unsaved GPS as successfully processed.
  }
  // Storage is committed before networking. iOS may suspend retries; next wake resumes.
  await (await getUploader()).tick(2);
  await (await getTripApi()).tick();
});
