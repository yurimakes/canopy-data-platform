import {beforeEach,expect,it,vi} from 'vitest';
import {accountRequest,checkedSession} from '../src/accountClient';
import type {Profile} from '../src/service';
const stored=vi.hoisted(()=>new Map<string,string>());
vi.mock('expo-secure-store',()=>({AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY:3,
  getItemAsync:vi.fn(async(key:string)=>stored.get(key)??null),
  setItemAsync:vi.fn(async(key:string,value:string)=>{stored.set(key,value);}),
  deleteItemAsync:vi.fn(async(key:string)=>{stored.delete(key);})}));
vi.mock('expo-constants',()=>({default:{expoConfig:{extra:{tripApiUrl:'https://example.com/api',tripFunctionKey:'key'}}}}));
const profile:Profile={id:'server-id',email:'u@example.com',nickname:'사용자',role:'user',campaignCode:'TEST',campaign_id:'server-campaign',home:null,work:null};
const signed=()=>({profile,access_token:'canopy1.server-token',expires_at:Date.now()/1000+3600});
const reply=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status});
beforeEach(()=>{vi.resetModules();stored.clear();vi.stubGlobal('__DEV__',true);vi.stubGlobal('fetch',vi.fn());});

it('registers only server-supported fields and persists no password',async()=>{
  vi.mocked(fetch).mockResolvedValue(reply(signed(),201));
  const {registerProfile}=await import('../src/profileStore');
  expect(await registerProfile({...profile,id:'local-random',role:'developer'},'long password','TEST')).toEqual(profile);
  const [url,options]=vi.mocked(fetch).mock.calls[0];
  expect(url).toBe('https://example.com/api/auth/signup');
  expect(JSON.parse(String(options?.body))).toEqual({email:profile.email,password:'long password',nickname:profile.nickname,campaign_code:'TEST',home:null,work:null});
  expect([...stored.values()].join()).not.toContain('long password');
});

it('does not accept the former hardcoded developer password without the server',async()=>{
  vi.mocked(fetch).mockResolvedValue(reply({message:'이메일 또는 비밀번호를 확인해주세요.'},401));
  const {loginProfile}=await import('../src/profileStore');
  await expect(loginProfile('canopydev','1234')).rejects.toThrow('비밀번호');
  expect(stored.size).toBe(0);expect(fetch).toHaveBeenCalledOnce();
});

it('restores the server profile and verifies developer access after reopening',async()=>{
  const developer={...profile,role:'developer' as const};
  vi.mocked(fetch).mockResolvedValueOnce(reply({...signed(),profile:developer}));
  const api=await import('../src/profileStore');await api.loginProfile('canopydev','strong password');
  vi.resetModules();vi.mocked(fetch).mockResolvedValueOnce(reply(developer)).mockResolvedValueOnce(reply({role:'developer'}));
  const reopened=await import('../src/profileStore');
  expect((await reopened.restoreProfile())?.role).toBe('developer');
  expect(vi.mocked(fetch).mock.calls.at(-1)?.[0]).toBe('https://example.com/api/auth/developer');
});

it('revokes the server session before removing local login',async()=>{
  const api=await import('../src/profileStore');
  vi.mocked(fetch).mockResolvedValueOnce(reply(signed()));await api.loginProfile('u@example.com','password');
  vi.mocked(fetch).mockRejectedValueOnce(Error('offline'));
  await expect(api.logoutProfile()).rejects.toThrow('offline');expect(stored.size).toBe(1);
  vi.mocked(fetch).mockResolvedValueOnce(reply({status:'signed_out'}));await api.logoutProfile();expect(stored.size).toBe(0);
});

it('removes a revoked session and never sends credentials to an unsafe URL',async()=>{
  const api=await import('../src/profileStore');
  vi.mocked(fetch).mockResolvedValueOnce(reply(signed()));await api.loginProfile('u@example.com','password');
  vi.mocked(fetch).mockResolvedValueOnce(reply({},401));expect(await api.restoreProfile()).toBeNull();expect(stored.size).toBe(0);
  const request=vi.fn();await expect(accountRequest({url:'http://public.example/api'},'login','POST',{},undefined,request)).rejects.toThrow();expect(request).not.toHaveBeenCalled();
  expect(()=>checkedSession({...signed(),expires_at:0},{url:'https://example.com/api'})).toThrow();
});

it('updates only profile fields and keeps campaign assignment server-owned',async()=>{
  const api=await import('../src/profileStore');
  vi.mocked(fetch).mockResolvedValueOnce(reply(signed()));await api.loginProfile('u@example.com','password');
  vi.mocked(fetch).mockResolvedValueOnce(reply({...profile,nickname:'수정'}));
  await api.updateProfile({...profile,role:'developer',campaignCode:'FAKE',nickname:'수정'});
  const body=JSON.parse(String(vi.mocked(fetch).mock.calls.at(-1)?.[1]?.body));
  expect(body).toEqual({nickname:'수정',home:null,work:null});
});
