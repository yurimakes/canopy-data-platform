import {expect,it} from 'vitest';
import {rewardPresentation} from './rewardPresentation';
it('celebrates only finite positive amounts confirmed as paid',()=>{
 expect(rewardPresentation({status:'paid',points:12})).toMatchObject({canCelebrate:true,amount:12,waiting:false});
 for(const points of [0,-1,NaN,Infinity,undefined])expect(rewardPresentation({status:'paid',points}).canCelebrate).toBe(false);
 for(const status of ['processing','retrying','awaiting_baseline','no_reduction','insufficient_gps','invalid_trip','test_trip','legacy_weekly_paid'])expect(rewardPresentation({status,points:99}).canCelebrate).toBe(false);
});
it('does not show endless checking for terminal exclusions',()=>{
 for(const status of ['no_reduction','insufficient_gps','invalid_trip','test_trip','legacy_weekly_paid'])expect(rewardPresentation({status})).toMatchObject({waiting:false,canCelebrate:false});
 for(const status of ['processing','retrying','awaiting_baseline'])expect(rewardPresentation({status}).waiting).toBe(true);
 expect(rewardPresentation(null).waiting).toBe(true);
 expect(rewardPresentation({status:'legacy_weekly_paid'}).label).toBe('이미 지급됨');
});
