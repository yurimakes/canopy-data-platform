// Build-time configuration. A mobile binary cannot conceal a shared API key.
const preview = process.env.CANOPY_UI_PREVIEW === 'true';
module.exports = ({config}) => ({
  ...config,
  ios: {...config.ios, bundleIdentifier: process.env.CANOPY_IOS_BUNDLE_IDENTIFIER || config.ios.bundleIdentifier},
  extra: {...config.extra,
    routeApiUrl: preview ? '' : process.env.CANOPY_ROUTE_API_URL || '',
    gpsApiUrl: preview ? '' : process.env.CANOPY_GPS_API_URL || '',
    gpsFunctionKey: preview ? '' : process.env.CANOPY_GPS_FUNCTION_KEY || '',
    tripApiUrl: preview ? '' : process.env.CANOPY_TRIP_API_URL || '',
    tripAccessToken: preview ? '' : process.env.CANOPY_TRIP_ACCESS_TOKEN || '',
    tripFunctionKey: preview ? '' : process.env.CANOPY_TRIP_FUNCTION_KEY || '',
    tripAllowLocalHttp: process.env.CANOPY_TRIP_ALLOW_LOCAL_HTTP === 'true',
  },
});
