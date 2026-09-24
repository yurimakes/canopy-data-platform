// Synthetic locations and desktop SQLite. This does not claim an iPhone device test.
import {afterAll,afterEach,beforeAll,expect,it,vi} from 'vitest';
import {DatabaseSync} from 'node:sqlite';
import {randomUUID} from 'node:crypto';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {spawn,type ChildProcess} from 'node:child_process';
import type {SQLiteDatabase} from 'expo-sqlite';
import type {LocationObject} from 'expo-location';
import {Storage} from '../src/storage';
import {Collector,type CollectorPorts} from '../src/collector';
import {TripApi,type TripConfig} from '../src/tripApi';
import {Uploader} from '../src/upload';

const directory=mkdtempSync(join(tmpdir(),'canopy-trip-tests-'));
const token='test-'+randomUUID();
let server:ChildProcess;
let base='';
const connections:DatabaseSync[]=[];

beforeAll(async()=>{
  const api=resolve('../api');
  const python=process.env.CANOPY_TEST_PYTHON ?? join(api,'.venv',process.platform==='win32'?'Scripts/python.exe':'bin/python');
  server=spawn(python,['local.py'],{cwd:api,windowsHide:true,env:{...process.env,
    APP_ENV:'development',TRIP_STORE:'sqlite',TRIP_SQLITE_PATH:join(directory,'server.sqlite'),
    API_HOST:'127.0.0.1',API_PORT:'0',TRIP_AUTH_MODE:'local',TRIP_LOCAL_TOKENS:JSON.stringify({alice:token}),
    TRIP_PROCESSOR:'mock',TRIP_CAMPAIGN_ID:'local-test',TRIP_PROCESS_DELAY_SECONDS:'0',WEBSITE_HOSTNAME:''},stdio:['ignore','pipe','pipe']});
  await new Promise<void>((done,fail)=>{
    const timeout=setTimeout(()=>fail(new Error('Local Trip API did not start')),15000);
    server.once('error',fail);
    server.once('exit',code=>{if(!base)fail(new Error('Local Trip API exited '+code));});
    server.stdout!.on('data',data=>{
      const match=String(data).match(/Local Trip API: (http:\/\/[^\s]+)/);
      if(match){base=match[1]+'/api';clearTimeout(timeout);done();}
    });
    server.stderr!.on('data',()=>{});
  });
},20000);
afterEach(()=>{for(const connection of connections.splice(0))connection.close();});
afterAll(async()=>{
  if(server && server.exitCode===null) {
    await new Promise<void>(done=>{server.once('exit',()=>done());server.kill();});
  }
  // Remove only the test directory created under the OS temp directory.
  if(!resolve(directory).startsWith(resolve(tmpdir())+sep))throw Error('Unsafe cleanup path');
  rmSync(directory,{recursive:true,force:true});
});

function database(path=':memory:') {
  const native=new DatabaseSync(path);connections.push(native);
  const adapter={
    execAsync:async(sql:string)=>{native.exec(sql);},
    runAsync:async(sql:string,...params:any[])=>native.prepare(sql).run(...params),
    getFirstAsync:async(sql:string,...params:any[])=>native.prepare(sql).get(...params)??null,
    getAllAsync:async(sql:string,...params:any[])=>native.prepare(sql).all(...params),
    async *getEachAsync(sql:string,...params:any[]){yield* native.prepare(sql).iterate(...params);},
  } as unknown as SQLiteDatabase;
  return {db:new Storage(adapter),native};
}
function config():TripConfig{return {url:base,token,allowLocalHttp:true};}
it('restores only completed owned server history without uploading GPS or stopping a remote recording',async()=>{
  const {db}=database();await db.init(randomUUID,new Date().toISOString());
  const row={trip_id:'remote-trip',user_id:'alice',device_id:'other-phone',started_at:'2026-09-19T00:00:00Z',ended_at:'2026-09-19T00:20:00Z',status:'ready',segments:[],is_mock:false};
  const request=vi.fn(async()=>new Response(JSON.stringify({trips:[row,{...row,trip_id:'other-user',user_id:'bob'},{...row,trip_id:'active',status:'collecting',ended_at:null}]}),{status:200}));
  const api=new TripApi(db,()=>({...config(),userId:'alice'}),randomUUID,request);
  await api.syncHistory();
  expect((await db.list()).map(t=>t.trip_id)).toEqual(['remote-trip']);
  expect((await api.result('remote-trip'))?.result?.status).toBe('ready');
  expect((await db.deliveryStatus('remote-trip')).pending).toBe(0);
  await api.tick(true);expect(request).toHaveBeenCalledTimes(1);
});
async function finish(s:Awaited<ReturnType<typeof setup>>) {
  await s.collector.start();s.emit();await s.collector.stop();await acceptGps(s.db);
  await vi.waitFor(async()=>{await s.api.tick(true);expect((await s.api.result(s.collector.trip!.trip_id))?.result?.status).toBe('ready');},
    {timeout:7000,interval:100});
  return (await s.api.result(s.collector.trip!.trip_id))!.result!;
}

it('shows carbon before feedback and keeps the result unchanged after an issue report',async()=>{
  const s=await setup();const result=await finish(s);
  expect(result.confirmed_trip?.mode_source).toBe('model_prediction');
  const accepted=await s.api.sendFeedback(result.trip_id,{has_issue:true,feedback_text:'버스 구간 확인 부탁드립니다.'});
  expect(accepted.feedback_status).toBe('submitted');expect(accepted.review_required).toBe(true);
  expect(accepted.segments).toEqual(result.segments);expect(accepted.confirmed_trip).toEqual(result.confirmed_trip);
  expect((await s.api.refresh(result.trip_id)).feedback_id).toBe(accepted.feedback_id);
});

it('persists a lost feedback response and retries the same request after SQLite reopen',async()=>{
  const path=join(directory,randomUUID()+'.sqlite');let drop=true;const ids:string[]=[];
  const request=(async(url,options)=>{
    if(String(url).endsWith('/feedback')) {
      ids.push(JSON.parse(String(options?.body)).request_id);
      const response=await fetch(url,options);
      if(drop){drop=false;throw Error('feedback response lost');}
      return response;
    }
    return fetch(url,options);
  }) as typeof fetch;
  const s=await setup(path,request);const trip=await finish(s);
  await expect(s.api.sendFeedback(trip.trip_id,{has_issue:true})).rejects.toThrow('response lost');
  expect((await s.api.result(trip.trip_id))?.feedback?.has_issue).toBe(true);
  const reopened=database(path);await reopened.db.init(randomUUID,new Date().toISOString());
  const restored=new TripApi(reopened.db,config,randomUUID,request);await restored.tick(true);
  const state=await restored.result(trip.trip_id);
  expect(state?.feedback).toBeUndefined();expect(state?.result?.feedback_status).toBe('submitted');
  expect(state?.result?.confirmed_trip).toEqual(trip.confirmed_trip);
  expect(ids).toHaveLength(2);expect(ids[0]).toBe(ids[1]);
});

it('reloads an existing response instead of overwriting it with a different answer',async()=>{
  const s=await setup();const trip=await finish(s);
  const response=await fetch(base+`/trips/${trip.trip_id}/feedback`,{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:JSON.stringify({request_id:randomUUID(),has_issue:false})});
  expect(response.status).toBe(200);
  await expect(s.api.sendFeedback(trip.trip_id,{has_issue:true})).rejects.toThrow('409');
  const state=await s.api.result(trip.trip_id);
  expect(state?.feedback).toBeUndefined();expect(state?.result?.feedback_status).toBe('no_issue');
  expect(state?.result?.segments).toEqual(trip.segments);
});

it('archives old pending correction requests without submitting them',async()=>{
  const s=await setup();const trip=await finish(s);
  const confirmation={request_id:randomUUID(),api_url:base,expected_revision:1,segments:[]};
  await s.db.saveSync('trip:'+trip.trip_id,{result:trip,confirmation});
  const request=vi.fn(fetch);const api=new TripApi(s.db,config,randomUUID,request);
  await api.tick(true);
  expect(request).not.toHaveBeenCalled();expect((await api.result(trip.trip_id))?.legacy_confirmation).toEqual(confirmation);
});
it('retries a transient CAS conflict using the same feedback ID',async()=>{
  let conflict=true;const ids:string[]=[];
  const request=(async(url,options)=>{
    if(String(url).endsWith('/feedback')) {
      ids.push(JSON.parse(String(options?.body)).request_id);
      if(conflict){conflict=false;return new Response(JSON.stringify({status:'concurrent_update'}),{status:409});}
    }
    return fetch(url,options);
  }) as typeof fetch;
  const s=await setup(':memory:',request);const trip=await finish(s);
  await expect(s.api.sendFeedback(trip.trip_id,{has_issue:false})).rejects.toThrow('409');
  expect((await s.api.result(trip.trip_id))?.feedback).toBeDefined();
  await s.api.tick(true);
  expect((await s.api.result(trip.trip_id))?.result?.feedback_status).toBe('no_issue');
  expect(ids[0]).toBe(ids[1]);expect(ids).toHaveLength(2);
});
function location():LocationObject{return {timestamp:Date.now(),coords:{latitude:37.5,longitude:127,
  accuracy:150,speed:null,heading:null,altitude:null,altitudeAccuracy:null}};}
async function setup(path=':memory:',request:typeof fetch=fetch,background=false) {
  const {db,native}=database(path);const identity=await db.init(randomUUID,new Date().toISOString());
  const api=new TripApi(db,config,randomUUID,request);
  let callback:(value:LocationObject)=>void=()=>{};let running=false;
  const ports:CollectorPorts={uuid:randomUUID,now:()=>new Date().toISOString(),settings:{},environment:{},
    startTrip:id=>api.start(id),permission:async()=>{},awake:async()=>{},
    watch:async cb=>{callback=cb;return {remove(){}};},
    background:background?{start:async()=>{running=true;},stop:async()=>{running=false;},isRunning:async()=>running}:undefined};
  const collector=new Collector(db,identity,ports);await collector.selectMode('walk');
  return {db,native,api,collector,ports,emit:(raw=location())=>callback(raw),identity};
}
async function acceptGps(db:Storage) {
  const events:any[]=[];
  const upload=new Uploader(db,()=>({url:'https://synthetic.test/api/gps',functionKey:'local-fixture'}),randomUUID,Date.now,
    (async(_url,options)=>{events.push(JSON.parse(String(options!.body)));return new Response('{"status":"accepted"}',{status:202});}) as typeof fetch);
  await upload.tick();
  return events;
}

it('TEST 7 simulation: real HTTP start → collector GPS → stop → ready with the same ID',async()=>{
  const s=await setup();await s.collector.start();
  expect(s.collector.phase).toBe('recording');
  const trip=s.collector.trip!;
  expect(trip.user_id).toBe('alice');
  s.emit();await s.collector.stop();
  const event=(await s.db.eventPage(trip.trip_id,0,10))[0];
  expect(event).toMatchObject({trip_id:trip.trip_id,user_id:'alice',label:'walk',speed:null,accuracy:150});
  expect(event.quality_flags).toContain('accuracy_above_100m');
  const sent=await acceptGps(s.db);expect(sent[0]).toEqual(event);
  await s.api.tick(true);
  await vi.waitFor(async()=>{
    await s.api.tick(true);
    expect((await s.api.result(trip.trip_id))?.result?.status).toBe('ready');
  },{timeout:7000,interval:100});
  const result=(await s.api.result(trip.trip_id))!.result!;
  expect(result.trip_id).toBe(event.trip_id);
  expect(result.model_version).toBe('mock_v1');expect(result.segments).toHaveLength(1);
  console.info(JSON.stringify({test:'same-trip-id',source:'synthetic desktop test',api:trip.trip_id,gps:event.trip_id,
    result:result.trip_id,event_id:event.event_id,status:result.status}));
});

it('reuses a persisted request_id after the server accepted start but its response was lost',async()=>{
  let lost=true;const ids:string[]=[];const serverIds:string[]=[];
  const request=(async(url,options)=>{
    ids.push(JSON.parse(String(options!.body)).request_id);
    const response=await fetch(url,options);serverIds.push((await response.clone().json()).trip_id);
    if(lost){lost=false;throw Error('response lost');}
    return response;
  }) as typeof fetch;
  const s=await setup(':memory:',request);
  await s.collector.start();
  await vi.waitFor(()=>expect(s.collector.phase).toBe('error'));
  const next=new TripApi(s.db,config,randomUUID,request);
  const recovered=await next.start(s.identity);
  expect(ids).toHaveLength(2);expect(ids[0]).toBe(ids[1]);expect(serverIds[0]).toBe(recovered.trip_id);
});

it('does not collect GPS when initial server start is offline',async()=>{
  const s=await setup(':memory:',(async()=>{throw Error('offline');}) as typeof fetch);
  await s.collector.start();await vi.waitFor(()=>expect(s.collector.phase).toBe('error'));
  s.emit();expect(await s.db.list()).toHaveLength(0);expect(s.collector.trip).toBeNull();
  expect(await s.db.syncValue('start')).not.toBeNull();
});

it('retains stopped GPS across SQLite reopen and sends stop only after pending GPS are accepted',async()=>{
  const path=join(directory,randomUUID()+'.sqlite');const s=await setup(path);
  await s.collector.start();s.emit();await s.collector.stop();
  const trip=s.collector.trip!;await s.api.tick(true);
  expect(await s.api.result(trip.trip_id)).toBeNull();
  const before=await s.db.eventPage(trip.trip_id,0,10);
  s.native.close();connections.splice(connections.indexOf(s.native),1);
  const recovered=await setup(path);
  expect(await recovered.db.eventPage(trip.trip_id,0,10)).toEqual(before);
  await acceptGps(recovered.db);await recovered.api.tick(true);
  expect((await recovered.api.result(trip.trip_id))?.result?.trip_id).toBe(trip.trip_id);
});

it('background GPS uses the server ID and label timeline while stop drains the same queue',async()=>{
  const s=await setup(':memory:',fetch,true);await s.collector.start();
  const id=s.collector.trip!.trip_id;
  await s.db.appendBackground([location()],new Date().toISOString(),randomUUID);
  await s.collector.selectMode('bus');
  await new Promise(done=>setTimeout(done,5));
  await s.db.appendBackground([location()],new Date().toISOString(),randomUUID);
  await s.collector.stop();
  const events=await s.db.eventPage(id,0,10);
  expect(events.map(e=>e.trip_id)).toEqual([id,id]);
  expect(events.map(e=>e.label)).toEqual(['walk','bus']);
  expect(events.map(e=>e.sequence)).toEqual([1,2]);
  expect((await s.db.deliveryStatus(id)).pending).toBe(2);
});

it('does not reroute an existing Trip to a different API after a config change',async()=>{
  const s=await setup();await s.collector.start();await s.collector.stop();
  const changed=new TripApi(s.db,()=>({...config(),url:'https://other.test/api'}),randomUUID);
  await changed.tick(true);
  expect((await changed.result(s.collector.trip!.trip_id))?.error).toContain('서버 주소');
});

it('retries a lost stop response without losing the stored Trip or starting a new one',async()=>{
  let loseStop=true;let stopCount=0;
  const request=(async(url,options)=>{
    const response=await fetch(url,options);
    if(String(url).endsWith('/stop')) {
      stopCount++;
      if(loseStop){loseStop=false;throw Error('stop response lost');}
    }
    return response;
  }) as typeof fetch;
  const s=await setup(':memory:',request);await s.collector.start();await s.collector.stop();
  const id=s.collector.trip!.trip_id;
  await s.api.tick(true);expect((await s.api.result(id))?.error).toContain('response lost');
  const recovered=new TripApi(s.db,config,randomUUID,request);await recovered.tick(true);
  expect((await recovered.result(id))?.result?.trip_id).toBe(id);
  expect(stopCount).toBe(1);expect(await s.db.list()).toHaveLength(1);
  expect((await recovered.result(id))?.error).toBeUndefined();
});

it('user screen collects unlabeled GPS and cannot switch to developer during a Trip',async()=>{
  const s=await setup();s.collector.selectCollectionMode('user');
  await s.collector.start();expect(s.collector.phase).toBe('recording');
  s.collector.selectCollectionMode('developer');await s.collector.selectMode('bus');
  expect(s.collector.collectionMode).toBe('user');
  s.emit();await s.collector.stop();
  const events=await acceptGps(s.db);
  expect(events).toHaveLength(1);
  expect(events[0]).toMatchObject({collection_mode:'user',label:null});
  s.collector.selectCollectionMode('developer');await s.collector.selectMode('bus');
  await s.collector.start();s.emit();await s.collector.stop();
  expect((await acceptGps(s.db))[0]).toMatchObject({collection_mode:'developer',label:'bus'});
});
it('user background Trip refresh preserves null labels',async()=>{
  const s=await setup(':memory:',fetch,true);s.collector.selectCollectionMode('user');
  await s.collector.start();
  await s.db.appendBackground([location()],new Date().toISOString(),randomUUID);
  await s.collector.refresh();
  expect(s.collector.collectionMode).toBe('user');expect(s.collector.mode).toBeNull();
  expect(s.collector.latest).toMatchObject({collection_mode:'user',label:null});
  await s.collector.stop();
});


it('excludes cached fixes from before the start button and appends a fresh stop fix',async()=>{
  const s=await setup();await s.collector.start();
  const start=Math.max(Date.parse(s.collector.trip!.started_at),Date.parse(s.collector.trip!.button_started_at!));
  s.emit({...location(),timestamp:start-33000});
  s.emit({...location(),timestamp:start+1});
  let stopFix=0;
  s.ports.finalLocation=async since=>{stopFix=since+1;return {...location(),timestamp:stopFix};};
  await s.collector.stop();
  const sent=await acceptGps(s.db);
  expect(sent).toHaveLength(2);
  expect(sent.map(e=>e.sequence)).toEqual([1,2]);
  expect(sent[1].event_time).toBe(new Date(stopFix).toISOString());
  expect(Date.parse(s.collector.trip!.ended_at!)).toBeGreaterThanOrEqual(stopFix);
});

it('keeps the saved GPS and stops after the final fix deadline',async()=>{
  const s=await setup();await s.collector.start();s.emit();
  s.ports.finalLocation=()=>new Promise(()=>{});
  vi.useFakeTimers();
  try {
    const stopping=s.collector.stop();
    await vi.advanceTimersByTimeAsync(8001);await stopping;
    expect(s.collector.phase).toBe('idle');
    expect((await s.db.summary(s.collector.trip!.trip_id)).gps_count).toBe(1);
  } finally {vi.useRealTimers();}
});

it('stores a fresh final background fix after the stop boundary but excludes late background callbacks',async()=>{
  const s=await setup(':memory:',fetch,true);await s.collector.start();
  await s.db.appendBackground([location()],new Date().toISOString(),randomUUID);
  s.ports.finalLocation=async since=>{
    await s.db.appendBackground([{...location(),timestamp:since+1}],new Date().toISOString(),randomUUID);
    return {...location(),timestamp:since+2};
  };
  await s.collector.stop();
  const sent=await acceptGps(s.db);expect(sent).toHaveLength(2);
  expect(sent.map(e=>e.sequence)).toEqual([1,2]);
  expect(await s.db.active()).toBeNull();
});

it('keeps another account\'s pending Trip untouched after account switching',async()=>{
  const s=await setup();await s.collector.start();s.emit();await s.collector.stop();await acceptGps(s.db);
  const request=vi.fn();
  const other=new TripApi(s.db,()=>({...config(),userId:'bob'}),randomUUID,request);
  await other.tick(true);expect(request).not.toHaveBeenCalled();
  expect(await s.api.result(s.collector.trip!.trip_id)).toBeNull();
});

it('does not reuse a start request from another logged-in account',async()=>{
  const {db}=database();await db.init(randomUUID,new Date().toISOString());
  const identity=await db.identity();
  await db.saveSync('start',{request_id:'owned-by-alice',device_id:identity.device_id,api_url:base,user_id:'alice'});
  const request=vi.fn();
  const other=new TripApi(db,()=>({...config(),userId:'bob'}),randomUUID,request);
  await expect(other.start(identity)).rejects.toThrow('이전 계정');expect(request).not.toHaveBeenCalled();
});

it('recovers a native cancelled Stop request that never reached the server',async()=>{
  let cancel=true;
  const request=(async(url,options)=>{
    if(String(url).endsWith('/stop')&&cancel){cancel=false;throw Error('FetchRequestCanceledException: Fetch request has been canceled');}
    return fetch(url,options);
  }) as typeof fetch;
  const s=await setup(':memory:',request);await s.collector.start();await s.collector.stop();
  const id=s.collector.trip!.trip_id;await s.api.tick(true);
  expect((await s.api.result(id))?.error).toContain('자동으로 다시 확인');
  expect((await s.api.result(id))?.error).not.toContain('FetchRequestCanceledException');
  await s.api.tick(true);
  expect((await s.api.result(id))?.result?.status).not.toBe('collecting');
  expect((await s.api.result(id))?.error).toBeUndefined();
  expect(await s.db.list()).toHaveLength(1);
});
