import {describe,expect,it,vi} from 'vitest';
import {HttpEngagementApi,parseMissionBundle,parseRanking,parseReward} from '../src/engagementApi';
import {engagementReadyFixture,MockEngagementApi} from '../src/engagementMock';

describe('weekly mission and ranking contract',()=>{
  it('keeps all four server assignments and never asks the user to select one',()=>{
    const fixture=engagementReadyFixture();
    const parsed=parseMissionBundle({status:'assigned',bundle:fixture.missions});
    expect(parsed.missions).toHaveLength(4);
    expect(new Set(parsed.missions.map(item=>item.category_id))).toEqual(new Set(['challenge','habit','easy_win','explore']));
  });
  it('rejects duplicate assignments instead of rendering ambiguous progress',()=>{
    const fixture=engagementReadyFixture();
    const bundle=structuredClone(fixture.missions)!;bundle.missions[1].assignment_id=bundle.missions[0].assignment_id;
    expect(()=>parseMissionBundle({status:'assigned',bundle})).toThrow('중복된 미션');
  });
  it('parses reward ledger and finalized ranking snapshot separately',()=>{
    const fixture=engagementReadyFixture();
    expect(parseReward(fixture.reward).total_points).toBe(320);
    const ranking=parseRanking(fixture.rankings.individual,'individual');
    expect(ranking.snapshot_status).toBe('finalized');expect(ranking.entries.find(item=>item.is_me)?.rank).toBe(3);
  });
  it('deduplicates repeated viewed and started events in the mock adapter',async()=>{
    const api=new MockEngagementApi();
    await api.recordMissionEvent('assign-habit','viewed');await api.recordMissionEvent('assign-habit','viewed');
    await api.recordMissionEvent('assign-habit','started');await api.recordMissionEvent('assign-habit','started');
    expect(api.events).toEqual([{assignmentId:'assign-habit',eventType:'viewed'},{assignmentId:'assign-habit',eventType:'started'}]);
  });
  it('loads mission, reward, personal ranking and department ranking through API only',async()=>{
    const fixture=engagementReadyFixture();const request=vi.fn(async(url:string|URL|Request)=>{
      const value=String(url);let body:unknown;
      if(value.includes('/missions'))body={status:'assigned',bundle:fixture.missions};
      else if(value.includes('/rewards'))body=fixture.reward;
      else body=value.includes('scope=department')?fixture.rankings.department:fixture.rankings.individual;
      return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
    });
    const api=new HttpEngagementApi({url:'https://example.test/api',token:'test'},request as unknown as typeof fetch,()=> 'request-1');
    const result=await api.loadDashboard('2026-09-14');
    expect(result.missions?.bundle_id).toBe('bundle_demo_20260914');expect(request).toHaveBeenCalledTimes(4);
    expect(request.mock.calls.every(([url])=>String(url).startsWith('https://example.test/api/'))).toBe(true);
  });
});
