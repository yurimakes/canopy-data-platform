import type {GpsEvent,Summary} from './types';
export type WebJourney={trip:Summary;points:GpsEvent[];ack:number;stop?:{ended_at:string;expected_last_sequence:number}};
export function webJourneyStore(storage:Pick<Storage,'getItem'|'setItem'|'removeItem'>,url:string,user:string){
  const key='canopy.web.journey:'+encodeURIComponent(url.replace(/\/+$/,''))+':'+encodeURIComponent(user);
  return {
    read():WebJourney|null {const raw=storage.getItem(key);if(!raw)return null;
      try{const value=JSON.parse(raw) as WebJourney;
        if(value.trip.user_id!==user||!Array.isArray(value.points)||!Number.isInteger(value.ack)||value.ack<0||value.ack>value.points.length||
          value.points.some((point,index)=>point.user_id!==user||point.trip_id!==value.trip.trip_id||point.sequence!==index+1)||
          (value.stop&&(value.stop.expected_last_sequence!==value.points.length||!Number.isFinite(Date.parse(value.stop.ended_at)))))throw Error('invalid');return value;
      }catch{throw Error('저장된 여정 복구에 실패했습니다. 기록을 삭제하지 말고 지원을 요청해주세요.');}},
    write(value:WebJourney){storage.setItem(key,JSON.stringify(value));},
    clear(){storage.removeItem(key);},
    startId(create:()=>string){let id=storage.getItem(key+':start');if(!id){id=create();storage.setItem(key+':start',id);}return id;},
    started(){storage.removeItem(key+':start');},
  };
}
