import type {FinalSegment} from './tripApi';

export type DisplaySegment = FinalSegment & {recordedSeconds:number; gapSeconds:number};

// Presentation only: preserve the server's segments and quality/reward decisions.
export function displaySegments(segments:readonly FinalSegment[]):DisplaySegment[]{
  return segments.map((segment,index)=>{
    const start=Date.parse(segment.start_time),end=Date.parse(segment.end_time);
    const previous=index?Date.parse(segments[index-1].end_time):start;
    return {...segment,recordedSeconds:Number.isFinite(end-start)?Math.max(0,(end-start)/1000):0,
      gapSeconds:Number.isFinite(start-previous)?Math.max(0,(start-previous)/1000):0};
  });
}

export function recordedDuration(seconds:number){
  const rounded=Math.max(0,Math.round(seconds));
  return `${Math.floor(rounded/60)}분 ${rounded%60}초`;
}
