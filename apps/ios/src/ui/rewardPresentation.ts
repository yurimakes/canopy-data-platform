/** Presentation only: reward status and amounts always come from the server. */
export type RewardComparison={status:string;planned_baseline_kg?:number;planned_baseline_source?:string;comparison_message?:string;comparison_scope?:string;points?:number;title?:string;classification?:string;baseline_kg?:number;saved_kg?:number;actual_kg?:number;source?:string;development_only?:boolean};
export function rewardPresentation(result:RewardComparison|null){
 const amount=result?.status==='paid'&&typeof result.points==='number'&&Number.isFinite(result.points)&&result.points>0?result.points:0;
 const waiting=!result||['processing','awaiting_baseline','retrying'].includes(result.status);
 const messages:Record<string,string>={no_reduction:'이번에는 적립된 토큰이 없어요. 다음 이동도 함께해요.',insufficient_gps:'위치 기록이 부족해 이번 여정에는 토큰이 없어요.',invalid_trip:'이동 결과를 확인하지 못해 보상이 제외됐어요.',test_trip:'테스트 여정은 보상에 포함되지 않아요.',legacy_weekly_paid:'이 여정의 보상은 이미 주간 보상으로 받았어요.'};
 return {amount,waiting,canCelebrate:amount>0,label:amount>0?'적립 완료':waiting?'확인 중':result?.status==='legacy_weekly_paid'?'이미 지급됨':'적립 없음',message:amount>0?'좋은 이동이 토큰으로 쌓였어요.':waiting?'보상을 확인하고 있어요.':messages[result?.status??'']??'이번 여정의 보상 내역을 확인해주세요.'};
}
