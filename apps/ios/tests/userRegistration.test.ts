import {describe,it,expect,vi} from 'vitest';
import {registerServerUser} from '../src/userRegistration';
const config={url:'https://example.com/api',token:'test',functionKey:'key'};
const saved={user_id:'server-user',campaign_id:'test-campaign',created_at:'2026-09-18T00:00:00Z',campaign_joined_at:'2026-09-18T00:00:00Z'};
describe('server registration',()=>{
 it('sends only nickname and campaign code; uses authenticated server identity and timestamps',async()=>{
  const request=vi.fn().mockResolvedValue(new Response(JSON.stringify(saved),{status:201}));
  expect(await registerServerUser(config,'사용자','TEST',request)).toEqual(saved);
  const [url,options]=request.mock.calls[0];
  expect(url).toBe('https://example.com/api/users/register');
  expect(JSON.parse(options.body)).toEqual({nickname:'사용자',campaign_code:'TEST'});
  expect(options.headers.Authorization).toBe('Bearer test');
 });
 it('does not treat conflicts or missing dates as completed registration',async()=>{
  await expect(registerServerUser(config,'사용자','TEST',vi.fn().mockResolvedValue(new Response('{}',{status:409})))).rejects.toThrow();
  await expect(registerServerUser(config,'사용자','TEST',vi.fn().mockResolvedValue(new Response('{}',{status:200})))).rejects.toThrow();
 });
 it('allows a retry response without changing server registration dates',async()=>{
  expect(await registerServerUser(config,'사용자','TEST',vi.fn().mockResolvedValue(new Response(JSON.stringify(saved),{status:200})))).toEqual(saved);
 });
});
