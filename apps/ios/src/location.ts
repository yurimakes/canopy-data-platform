import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import * as Crypto from 'expo-crypto';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { LOCATION_TASK, getTripApi } from './backgroundLocationTask';
import type { CollectorPorts } from './collector';
const options: Location.LocationTaskOptions = {
  accuracy: Location.Accuracy.BestForNavigation, distanceInterval: 0,
  pausesUpdatesAutomatically: false, showsBackgroundLocationIndicator: true,
  deferredUpdatesDistance: 0, deferredUpdatesInterval: 0,
  activityType: Location.ActivityType.OtherNavigation,
};
let starting: Promise<void> | undefined;
export const foregroundOnly = Constants.appOwnership === 'expo';
export const ports: CollectorPorts = {
  async startTrip(identity) {return (await getTripApi()).start(identity);},
  async permission() {
    if (Platform.OS!=='ios' || (!foregroundOnly && !(await TaskManager.isAvailableAsync())))
      throw new Error('백그라운드 측정은 iPhone에 설치한 Canopy 앱에서 사용하세요. Expo Go에서는 지원하지 않습니다.');
    if (!(await Location.hasServicesEnabledAsync())) throw new Error('iPhone 설정에서 위치 서비스를 켜주세요.');
    const foreground=await Location.requestForegroundPermissionsAsync();
    if(!foreground.granted) throw new Error('iPhone 설정 → Canopy → 위치에서 접근을 허용해주세요.');
    if (!foregroundOnly) {
      const background=await Location.requestBackgroundPermissionsAsync();
      if(!background.granted) throw new Error('잠금 중 측정하려면 설정 → Canopy → 위치 → 항상을 선택하세요. 한 번 허용을 선택했다면 설정에서 변경해야 합니다.');
    }
    const permission=await Location.getForegroundPermissionsAsync();
    if(permission.ios?.accuracy==='reduced') throw new Error('데이터 수집을 위해 설정 → Canopy → 위치에서 정확한 위치를 켜주세요.');
  },
  watch: callback => Location.watchPositionAsync(options, callback),
  background: foregroundOnly ? undefined : {
    async start() {
      if(starting) return starting;
      starting=(async()=>{if(!(await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK))) await Location.startLocationUpdatesAsync(LOCATION_TASK,options);})();
      try {await starting;} finally {starting=undefined;}
    },
    async stop() {await starting; if(await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK)) await Location.stopLocationUpdatesAsync(LOCATION_TASK);},
    async isRunning() {return await TaskManager.isAvailableAsync() && await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK);},
  },
  awake: async()=>{}, uuid: Crypto.randomUUID, now: ()=>new Date().toISOString(),
  settings:{...options,accuracy_name:'BestForNavigation',ios_fixed_cadence_guaranteed:false},
  environment:{app_version:Constants.expoConfig?.version??null,expo_sdk:Constants.expoConfig?.sdkVersion??null,
    platform:Platform.OS,os_version:Platform.Version,execution_environment:Constants.executionEnvironment},
};
