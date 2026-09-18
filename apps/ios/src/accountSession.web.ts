import type {AccountSession} from './accountClient';
// 웹 미리보기의 토큰은 메모리에만 보관. 브라우저 영구 저장 제외.
let current:AccountSession|null=null;
export function session(){return current&&current.expires_at*1000>Date.now()?current:null;}
export async function loadSession(){return session();}
export async function saveSession(value:AccountSession|null){current=value;}
