import {it,expect,vi} from 'vitest';
import {Uploader} from './upload';
import type {Storage} from './storage';

it('keeps queued GPS on expired login and authenticates unchanged payload on retry',async()=>{
  const payload=JSON.stringify({event_id:'event',user_id:'alice',trip_id:'trip'});
  const job={payload,retry_count:0};
  const db={claimDelivery:vi.fn().mockResolvedValue(job),deliverySuccess:vi.fn(),deliveryFailure:vi.fn()} as unknown as Storage;
  const request=vi.fn().mockResolvedValueOnce(new Response('{}',{status:401})).mockResolvedValueOnce(new Response('{"status":"accepted"}',{status:202}));
  const upload=new Uploader(db,()=>({url:'https://service/api/gps',functionKey:'fixture'}),()=> 'id',Date.now,request,async()=> 'session');
  await upload.tick(1);
  expect(db.deliveryFailure).toHaveBeenCalledWith(job,expect.any(Number),'GPS API HTTP 401',false);
  expect(db.deliverySuccess).not.toHaveBeenCalled();
  await upload.tick(1);
  expect(request.mock.calls[1][1].headers.Authorization).toBe('Bearer session');
  expect(request.mock.calls[1][1].body).toBe(payload);
  expect(db.deliverySuccess).toHaveBeenCalledOnce();
});
