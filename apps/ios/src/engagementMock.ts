import type {EngagementClient,EngagementDashboard,RankingEntry,RankingScope} from './engagementApi';

const weekStart='2026-09-14',weekEnd='2026-09-21';
const ranks=(scope:RankingScope,names:string[],me:number):RankingEntry[]=>(names.map((display_name,index)=>({
  rank:index+1,subject_id:`${scope}-${index+1}`,display_name,score:[860,790,710,640,580][index]??500,is_me:index===me,
})));
export function engagementReadyFixture():EngagementDashboard {
  return {source:'mock',missions:{bundle_id:'bundle_demo_20260914',campaign_id:'canopy-demo',week_start:weekStart,week_end:weekEnd,
    policy_version:'mission-policy-v3.2',profile_status_at_issue:'current',common_target_count:2,missions:[
      {assignment_id:'assign-challenge',category_id:'challenge',category_label:'도전형',mission_template_id:'challenge_car_to_transit',
        mission_name:'3km 이상 대중교통 이동 2번 도전',mission_description:'자동차 대신 버스·철도로 이동해 보세요.',progress_unit:'회',target_count:2,progress_count:1,achievement_rate:.5,completed:false,status:'active'},
      {assignment_id:'assign-habit',category_id:'habit',category_label:'꾸준형',mission_template_id:'habit_transit_repeat',
        mission_name:'서로 다른 2일에 대중교통 이용하기',mission_description:'한 번에 몰아서 타기보다 여러 날에 나누어 이용해 보세요.',progress_unit:'일',target_count:2,progress_count:2,achievement_rate:1,completed:true,status:'completed'},
      {assignment_id:'assign-easy',category_id:'easy_win',category_label:'가벼운 실천형',mission_template_id:'easy_short_car_replace',
        mission_name:'짧은 자동차 이동 2번 바꾸기',mission_description:'2km 이하 이동을 걷기나 자전거로 바꿔 보세요.',progress_unit:'회',target_count:2,progress_count:0,achievement_rate:0,completed:false,status:'active'},
      {assignment_id:'assign-explore',category_id:'explore',category_label:'새로운 시도형',mission_template_id:'explore_new_mode',
        mission_name:'새로운 친환경 이동 1번 경험하기',mission_description:'평소와 다른 저탄소 이동수단을 이용해 보세요.',progress_unit:'회',target_count:1,progress_count:1,achievement_rate:1,completed:true,status:'completed'},
    ]},reward:{week_start:weekStart,week_end:weekEnd,status:'settled',total_points:320,updated_at:'2026-09-17T07:30:00Z',
      policy_version:'reward-policy-v1',finalized:true,next_cursor:null,entries:[
      {reward_id:'reward-1',label:'주간 저탄소 이동 보상',points:300,status:'paid',occurred_at:'2026-09-16T09:15:00Z'},
      {reward_id:'adjustment-1',label:'승인된 보상 조정',points:20,status:'adjusted',occurred_at:'2026-09-17T06:10:00Z'},
    ]},rankings:{
      individual:{scope:'individual',campaign_id:'canopy-demo',week_start:weekStart,week_end:weekEnd,snapshot_status:'finalized',generated_at:'2026-09-16T23:00:00Z',policy_version:'ranking-policy-v1',aggregation_version:'ranking-build-v1',finalized:true,score_unit:'points',next_cursor:null,entries:ranks('individual',['이서준','김하늘','나','박지민','최유진'],2)},
      department:{scope:'department',campaign_id:'canopy-demo',week_start:weekStart,week_end:weekEnd,snapshot_status:'finalized',generated_at:'2026-09-16T23:00:00Z',policy_version:'ranking-policy-v1',aggregation_version:'ranking-build-v1',finalized:true,score_unit:'points',next_cursor:null,entries:ranks('department',['데이터팀','서비스팀','플랫폼팀','기획팀'],0)},
    },errors:{}};
}

export class MockEngagementApi implements EngagementClient {
  constructor(private scenario:'ready'|'empty'|'forbidden'|'error'='ready'){}
  async loadDashboard():Promise<EngagementDashboard>{
    if(this.scenario==='forbidden')throw Object.assign(Error('이 캠페인의 랭킹을 볼 권한이 없습니다.'),{status:403});
    if(this.scenario==='error')throw Error('미션·랭킹 정보를 불러오지 못했습니다.');
    const fixture=engagementReadyFixture();
    if(this.scenario==='empty'){fixture.missions=null;fixture.reward={...fixture.reward!,status:'empty',total_points:0,entries:[]};}
    return JSON.parse(JSON.stringify(fixture));
  }
}
