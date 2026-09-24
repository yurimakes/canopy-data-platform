import type {FinalSegment} from './tripApi';

export type DisplaySegment = FinalSegment & {recordedSeconds:number; gapSeconds:number};

// Presentation only: preserve the server's segments and quality/reward decisions.
export function displaySegments(segments:readonly FinalSegment[]):DisplaySegment[]{
  const groups:DisplaySegment[]=[];
  for(const segment of segments){
    const start=Date.parse(segment.start_time),end=Date.parse(segment.end_time);
    const duration=Number.isFinite(end-start)?Math.max(0,(end-start)/1000):0;
    const mode=segment.confirmed_mode??segment.mode;
    const previous=groups[groups.length-1];
    const gap=previous?(start-Date.parse(previous.end_time))/1000:NaN;
    if(previous&&(previous.confirmed_mode??previous.mode)===mode&&Number.isFinite(gap)&&gap>=0){
      previous.end_time=segment.end_time;
      previous.distance_m+=segment.distance_m;
      previous.recordedSeconds+=duration;
      previous.gapSeconds+=gap;
      previous.carbon_kg=previous.carbon_kg!=null&&segment.carbon_kg!=null?previous.carbon_kg+segment.carbon_kg:undefined;
    }else groups.push({...segment,recordedSeconds:duration,gapSeconds:0});
  }
  return groups;
}

export function recordedDuration(seconds:number){
  const rounded=Math.max(0,Math.round(seconds));
  return `${Math.floor(rounded/60)}분 ${rounded%60}초`;
}
