import {describe,it,expect} from 'vitest';
import {webJourneyStore} from './webJourneyStore';
import type {WebJourney} from './webJourneyStore';
describe('web journey recovery',()=>{
  function storage(){const values=new Map<string,string>();return {getItem:(k:string)=>values.get(k)??null,setItem:(k:string,v:string)=>{values.set(k,v);},removeItem:(k:string)=>{values.delete(k);}};}
  it('keeps start id across response loss and isolates account/server',()=>{
    const db=storage(),first=webJourneyStore(db,'http://localhost/api','alice');
    expect(first.startId(()=>'original')).toBe('original');
    expect(webJourneyStore(db,'http://localhost/api/','alice').startId(()=>'wrong')).toBe('original');
    expect(webJourneyStore(db,'http://localhost/api','bob').startId(()=>'bob')).toBe('bob');
    first.started();expect(first.startId(()=>'next')).toBe('next');
  });
  it('restores unsent observations and exact stop intent after a lost response',()=>{
    const db=storage(),store=webJourneyStore(db,'https://service/api','alice');
    const value={trip:{trip_id:'trip',user_id:'alice'},points:[{event_id:'one',trip_id:'trip',user_id:'alice',sequence:1},{event_id:'two',trip_id:'trip',user_id:'alice',sequence:2}],ack:1,
      stop:{ended_at:'2026-09-20T01:00:00Z',expected_last_sequence:2}} as WebJourney;
    store.write(value);
    expect(webJourneyStore(db,'https://service/api','alice').read()).toEqual(value);
    expect(webJourneyStore(db,'https://service/api','bob').read()).toBeNull();
    store.clear();expect(store.read()).toBeNull();
  });
  it('does not erase a corrupt saved record',()=>{
    const db=storage(),store=webJourneyStore(db,'https://service/api','alice');
    store.write({trip:{user_id:'bob'},points:[],ack:0} as unknown as WebJourney);
    expect(()=>store.read()).toThrow('기록을 삭제하지 말고');
    expect(()=>store.read()).toThrow('기록을 삭제하지 말고');
  });
});
