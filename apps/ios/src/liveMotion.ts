import type {GpsEvent} from './types';

// GPS speed is provisional: it cannot distinguish a bicycle, car, bus or train.
export function liveMotionLabel(events:GpsEvent[]):string {
  const latest=events.at(-1);
  if(!latest)return '위치 수신 중';
  const end=Date.parse(latest.event_time);
  const speeds=events.slice(-12).filter(e=>end-Date.parse(e.event_time)<=15000 && e.accuracy!=null && e.accuracy<=50)
    .map(e=>e.speed).filter((v):v is number=>v!=null && Number.isFinite(v) && v>=0).sort((a,b)=>a-b);
  if(!speeds.length)return '이동 감지 중';
  const speed=speeds[Math.floor(speeds.length/2)];
  return speed<0.5?'정지·저속 (추정)':speed<2.2?'걷기 (추정)':'이동 중 · 수단 분석 대기';
}
