import type {GpsEvent} from './types';

// Expo reports metres/second. Never turn a missing or stale fix into zero speed.
export function liveSpeedKmh(events:GpsEvent[],now=Date.now()):number|null {
  const latest=events.at(-1);
  if(!latest)return null;
  const age=now-Date.parse(latest.event_time);
  if(!Number.isFinite(age)||age>15000||age< -5000||latest.accuracy==null||!Number.isFinite(latest.accuracy)||latest.accuracy<0||latest.accuracy>50)return null;
  const speed=latest.speed;
  return speed!=null&&Number.isFinite(speed)&&speed>=0?speed*3.6:null;
}
