import type {Place} from './service';

type Fix={timestamp:number;coords:{latitude:number;longitude:number;accuracy:number|null}};
export async function currentOrigin(provider:{permission():Promise<boolean>;position():Promise<Fix>},timeoutMs=18000,now=Date.now):Promise<Place>{
 if(!await provider.permission())throw Error('현재 위치를 사용하려면 위치 접근을 허용해주세요.');
 let timer:ReturnType<typeof setTimeout>|undefined;
 try{
  const fix=await Promise.race([provider.position(),new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(Error('위치를 찾지 못했어요. 창가나 실외에서 다시 시도해주세요.')),timeoutMs);})]);
  const {latitude,longitude,accuracy}=fix.coords;
  if(!Number.isFinite(latitude)||!Number.isFinite(longitude)||Math.abs(latitude)>90||Math.abs(longitude)>180||accuracy==null||!Number.isFinite(accuracy)||accuracy<0||accuracy>100||!Number.isFinite(fix.timestamp)||Math.abs(now()-fix.timestamp)>30000)throw Error('정확한 현재 위치를 확인하지 못했어요. 다시 시도해주세요.');
  return {name:'현재 위치',latitude,longitude};
 }finally{if(timer)clearTimeout(timer);}
}
