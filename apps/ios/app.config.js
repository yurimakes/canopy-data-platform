// Build-time configuration. A mobile binary cannot conceal a shared API key.
const preview = process.env.CANOPY_UI_PREVIEW === 'true';
const local = process.env.CANOPY_LOCAL_ONLY === 'true';
const release = process.env.CANOPY_RELEASE_BUILD === 'true';
if(release){
  if(local||preview||process.env.CANOPY_TRIP_ALLOW_LOCAL_HTTP==='true')throw Error('배포 빌드에는 로컬/미리보기 모드를 사용할 수 없습니다.');
  for(const name of ['CANOPY_TRIP_API_URL','CANOPY_GPS_API_URL','CANOPY_TRIP_FUNCTION_KEY','CANOPY_GPS_FUNCTION_KEY'])
    if(!process.env[name]?.trim())throw Error('배포 빌드 필수 설정 누락: '+name);
  const trip=new URL(process.env.CANOPY_TRIP_API_URL),gps=new URL(process.env.CANOPY_GPS_API_URL);
  for(const url of [trip,gps])if(url.protocol!=='https:'||url.username||url.password||url.search||url.hash)throw Error('배포 API는 인증정보 없는 HTTPS 주소여야 합니다.');
  if(trip.pathname.replace(/\/$/,'')!=='/api'||gps.href!==trip.href.replace(/\/$/,'')+'/gps')throw Error('Trip/GPS API 주소가 같은 서버를 가리켜야 합니다.');
}
if(local){
  const api=new URL(process.env.CANOPY_TRIP_API_URL||'http://127.0.0.1:8000/api');
  if(api.protocol!=='http:'||!/^(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(api.hostname))throw Error('로컬 API 주소만 허용됩니다.');
  process.env.CANOPY_TRIP_API_URL=api.toString().replace(/\/$/,'');
  process.env.CANOPY_GPS_API_URL=process.env.CANOPY_TRIP_API_URL+'/gps';
  process.env.CANOPY_ROUTE_API_URL='';
  process.env.CANOPY_TRIP_ALLOW_LOCAL_HTTP='true';
}
module.exports = ({config}) => ({
  ...config,
  plugins: [...(config.plugins || []).filter(p => p !== 'expo-font'), 'expo-font'],
  ios: {...config.ios, bundleIdentifier: process.env.CANOPY_IOS_BUNDLE_IDENTIFIER || config.ios.bundleIdentifier},
  extra: {...config.extra,
    localOnly:local,
    routeApiUrl: preview ? '' : process.env.CANOPY_ROUTE_API_URL || '',
    gpsApiUrl: preview ? '' : process.env.CANOPY_GPS_API_URL || '',
    gpsFunctionKey: preview ? '' : process.env.CANOPY_GPS_FUNCTION_KEY || '',
    tripApiUrl: preview ? '' : process.env.CANOPY_TRIP_API_URL || '',
    tripFunctionKey: preview ? '' : process.env.CANOPY_TRIP_FUNCTION_KEY || '',
    tripAllowLocalHttp: process.env.CANOPY_TRIP_ALLOW_LOCAL_HTTP === 'true',
  },
});
