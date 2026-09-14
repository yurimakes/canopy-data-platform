// Build-time configuration. A mobile binary cannot conceal a shared API key.
module.exports = ({config}) => ({
  ...config,
  ios: {...config.ios, bundleIdentifier: process.env.CANOPY_IOS_BUNDLE_IDENTIFIER || config.ios.bundleIdentifier},
  extra: {...config.extra,
    gpsApiUrl: process.env.CANOPY_GPS_API_URL || '',
    gpsFunctionKey: process.env.CANOPY_GPS_FUNCTION_KEY || '',
    tripApiUrl: process.env.CANOPY_TRIP_API_URL || '',
    tripAccessToken: process.env.CANOPY_TRIP_ACCESS_TOKEN || '',
    tripFunctionKey: process.env.CANOPY_TRIP_FUNCTION_KEY || '',
    tripAllowLocalHttp: process.env.CANOPY_TRIP_ALLOW_LOCAL_HTTP === 'true',
  },
});
