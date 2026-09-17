export type MissionStatus = 'active' | 'completed' | 'expired';
export type RewardStatus = 'processing' | 'settled' | 'empty';
export type RankingScope = 'individual' | 'department';

export type WeeklyMission = {
  assignment_id:string;
  category_id:'challenge'|'habit'|'easy_win'|'explore'|string;
  category_label:string;
  mission_template_id:string;
  mission_name:string;
  mission_description?:string|null;
  progress_unit:string;
  target_count:number;
  progress_count:number;
  achievement_rate:number;
  completed:boolean;
  status:MissionStatus;
};

export type MissionBundle = {
  bundle_id:string;
  campaign_id:string;
  week_start:string;
  week_end:string;
  policy_version:string;
  profile_status_at_issue:'current'|'history_only'|'cold_start'|string;
  common_target_count:number;
  missions:WeeklyMission[];
};

export type RewardEntry = {
  reward_id:string;
  label:string;
  points:number;
  status:'processing'|'paid'|'adjusted';
  occurred_at:string;
};

export type WeeklyReward = {
  week_start:string;
  week_end:string;
  status:RewardStatus;
  total_points:number;
  updated_at:string;
  entries:RewardEntry[];
};

export type RankingEntry = {
  rank:number;
  subject_id:string;
  display_name:string;
  score:number;
  is_me:boolean;
};

export type RankingSnapshot = {
  scope:RankingScope;
  campaign_id:string;
  week_start:string;
  week_end:string;
  snapshot_status:'finalized'|'in_progress';
  generated_at:string;
  policy_version:string;
  score_unit:'points';
  entries:RankingEntry[];
};

export type EngagementDashboard = {
  source:'api'|'mock';
  missions:MissionBundle|null;
  reward:WeeklyReward;
  rankings:Record<RankingScope,RankingSnapshot>;
};

export type MissionEventType = 'viewed'|'started';
export interface EngagementClient {
  loadDashboard(week?:string,signal?:AbortSignal):Promise<EngagementDashboard>;
  recordMissionEvent(assignmentId:string,eventType:MissionEventType):Promise<void>;
}

export type EngagementConfig = {
  url:string;
  token?:string;
  functionKey?:string;
  allowLocalHttp?:boolean;
};

export class EngagementHttpError extends Error {
  constructor(public status:number,public code:string,message:string){super(message);}
}

const object=(value:unknown,label:string):Record<string,unknown>=>{
  if(!value || typeof value!=='object' || Array.isArray(value))throw Error(`${label} 응답 형식이 다릅니다.`);
  return value as Record<string,unknown>;
};
const text=(value:unknown,label:string)=>{if(typeof value!=='string'||!value)throw Error(`${label} 값이 없습니다.`);return value;};
const number=(value:unknown,label:string)=>{if(typeof value!=='number'||!Number.isFinite(value))throw Error(`${label} 값이 올바르지 않습니다.`);return value;};
const isoDate=(value:unknown,label:string)=>{const result=text(value,label);if(!/^\d{4}-\d{2}-\d{2}$/.test(result))throw Error(`${label} 형식이 다릅니다.`);return result;};

export function parseMissionBundle(payload:unknown):MissionBundle {
  const root=object(payload,'미션'),bundle=object(root.bundle,'미션 bundle');
  const rawMissions=bundle.missions;
  if(root.status!=='assigned'||!Array.isArray(rawMissions))throw Error('미션 응답 형식이 다릅니다.');
  const ids=new Set<string>();
  const missions=rawMissions.map((value,index)=>{
    const item=object(value,`미션 ${index+1}`),assignment=text(item.assignment_id,'assignment_id');
    if(ids.has(assignment))throw Error('중복된 미션 assignment가 있습니다.');ids.add(assignment);
    const status=text(item.status,'미션 상태') as MissionStatus;
    if(!['active','completed','expired'].includes(status))throw Error('미션 상태가 올바르지 않습니다.');
    return {
      assignment_id:assignment,category_id:text(item.category_id,'카테고리'),category_label:text(item.category_label,'카테고리 이름'),
      mission_template_id:text(item.mission_template_id,'미션 템플릿'),mission_name:text(item.mission_name,'미션 이름'),
      mission_description:typeof item.mission_description==='string'?item.mission_description:null,
      progress_unit:typeof item.progress_unit==='string'?item.progress_unit:'회',target_count:number(item.target_count,'목표'),
      progress_count:number(item.progress_count,'진행률'),achievement_rate:number(item.achievement_rate,'달성률'),
      completed:item.completed===true,status,
    };
  });
  return {bundle_id:text(bundle.bundle_id,'bundle_id'),campaign_id:text(bundle.campaign_id,'campaign_id'),
    week_start:isoDate(bundle.week_start,'시작 주차'),week_end:isoDate(bundle.week_end,'종료 주차'),
    policy_version:text(bundle.policy_version,'미션 정책 버전'),profile_status_at_issue:text(bundle.profile_status_at_issue,'프로필 상태'),
    common_target_count:number(bundle.common_target_count,'공통 목표'),missions};
}

export function parseReward(payload:unknown):WeeklyReward {
  const root=object(payload,'보상');
  if(!Array.isArray(root.entries)||!['processing','settled','empty'].includes(String(root.status)))throw Error('보상 응답 형식이 다릅니다.');
  return {week_start:isoDate(root.week_start,'보상 시작 주차'),week_end:isoDate(root.week_end,'보상 종료 주차'),status:root.status as RewardStatus,
    total_points:number(root.total_points,'보상 합계'),updated_at:text(root.updated_at,'보상 갱신 시각'),entries:root.entries.map((value,index)=>{
      const item=object(value,`보상 ${index+1}`);return {reward_id:text(item.reward_id,'reward_id'),label:text(item.label,'보상 이름'),
        points:number(item.points,'포인트'),status:text(item.status,'보상 상태') as RewardEntry['status'],occurred_at:text(item.occurred_at,'보상 시각')};
    })};
}

export function parseRanking(payload:unknown,expected:RankingScope):RankingSnapshot {
  const root=object(payload,'랭킹');
  if(root.scope!==expected||!Array.isArray(root.entries)||!['finalized','in_progress'].includes(String(root.snapshot_status)))throw Error('랭킹 응답 형식이 다릅니다.');
  return {scope:expected,campaign_id:text(root.campaign_id,'campaign_id'),week_start:isoDate(root.week_start,'랭킹 시작 주차'),
    week_end:isoDate(root.week_end,'랭킹 종료 주차'),snapshot_status:root.snapshot_status as RankingSnapshot['snapshot_status'],
    generated_at:text(root.generated_at,'랭킹 생성 시각'),policy_version:text(root.policy_version,'랭킹 정책 버전'),score_unit:'points',
    entries:root.entries.map((value,index)=>{const item=object(value,`순위 ${index+1}`);return {rank:number(item.rank,'순위'),
      subject_id:text(item.subject_id,'순위 대상'),display_name:text(item.display_name,'표시 이름'),score:number(item.score,'점수'),is_me:item.is_me===true};})};
}

export class HttpEngagementApi implements EngagementClient {
  constructor(private config:EngagementConfig,private request:typeof fetch=fetch,private uuid:()=>string=()=>`${Date.now()}-${Math.random()}`){
    const parsed=new URL(config.url);
    if(parsed.protocol!=='https:'&&!(config.allowLocalHttp&&parsed.protocol==='http:'))throw Error('미션·랭킹 API는 HTTPS 주소를 사용하세요.');
    if(parsed.username||parsed.password||parsed.search||parsed.hash||!/\/api\/?$/.test(parsed.pathname))throw Error('미션·랭킹 API 주소는 /api로 끝나야 합니다.');
  }
  private async call(path:string,init:RequestInit={},signal?:AbortSignal){
    const response=await this.request(this.config.url.replace(/\/$/,'')+path,{...init,signal,redirect:'error',headers:{
      'Content-Type':'application/json',...(this.config.token?{Authorization:'Bearer '+this.config.token}:{}),
      ...(this.config.functionKey?{'x-functions-key':this.config.functionKey}:{}),...(init.headers??{})}});
    const payload=await response.json().catch(()=>({}));
    if(!response.ok){const error=object(payload,'오류');throw new EngagementHttpError(response.status,String(error.code??'request_failed'),String(error.message??'요청에 실패했습니다.'));}
    return payload;
  }
  async loadDashboard(week?:string,signal?:AbortSignal):Promise<EngagementDashboard>{
    const query=week?`?week=${encodeURIComponent(week)}`:'';
    const separator=week?'&':'?';
    const [missions,reward,individual,department]=await Promise.all([
      this.call('/users/me/missions'+query,{},signal),this.call('/users/me/rewards'+query,{},signal),
      this.call('/rankings'+query+separator+'scope=individual',{},signal),this.call('/rankings'+query+separator+'scope=department',{},signal),
    ]);
    return {source:'api',missions:parseMissionBundle(missions),reward:parseReward(reward),rankings:{
      individual:parseRanking(individual,'individual'),department:parseRanking(department,'department')}};
  }
  async recordMissionEvent(assignmentId:string,eventType:MissionEventType){
    await this.call('/users/me/missions/events',{method:'POST',body:JSON.stringify({request_id:this.uuid(),assignment_id:assignmentId,event_type:eventType})});
  }
}
