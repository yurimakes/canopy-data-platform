import Constants from 'expo-constants';
import {HttpEngagementApi,type EngagementClient} from './engagementApi';
import {MockEngagementApi} from './engagementMock';

let singleton:EngagementClient|undefined;
export function getEngagementApi():EngagementClient {
  if(singleton)return singleton;
  const extra=Constants.expoConfig?.extra??{};
  const useMock=extra.engagementUseMock===true||(__DEV__&&!extra.engagementApiUrl);
  if(useMock)return singleton=new MockEngagementApi();
  if(!extra.engagementApiUrl)return singleton={
    async loadDashboard(){throw Error('미션·랭킹 API 설정이 필요합니다.');},
  };
  return singleton=new HttpEngagementApi({url:extra.engagementApiUrl,token:extra.engagementAccessToken||'',
    functionKey:extra.engagementFunctionKey||extra.tripFunctionKey||extra.gpsFunctionKey,
    allowLocalHttp:__DEV__&&extra.engagementAllowLocalHttp===true});
}
