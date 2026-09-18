import Constants from 'expo-constants';
import type {AccountConfig} from './accountClient';
export function accountConfig():AccountConfig {
  const extra=Constants.expoConfig?.extra;
  if(!extra?.tripApiUrl)throw Error('로그인 서버 주소가 없습니다. 새 QR 코드로 앱을 열어주세요.');
  return {url:extra.tripApiUrl,functionKey:extra.tripFunctionKey||extra.gpsFunctionKey,allowLocalHttp:__DEV__&&extra.tripAllowLocalHttp===true};
}
