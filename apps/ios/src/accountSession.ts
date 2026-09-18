import * as SecureStore from 'expo-secure-store';
import type {AccountSession} from './accountClient';
const key='canopy.server-session.v1';
let current:AccountSession|null=null,loaded=false;
export async function loadSession(){
  if(!loaded){const raw=await SecureStore.getItemAsync(key);current=raw?JSON.parse(raw):null;loaded=true;}
  return session();
}
export function session(){return current&&current.expires_at*1000>Date.now()?current:null;}
export async function saveSession(value:AccountSession|null){
  if(value)await SecureStore.setItemAsync(key,JSON.stringify(value),{keychainAccessible:SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY});
  else await SecureStore.deleteItemAsync(key);
  current=value;loaded=true;
}
