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
    engagementApiUrl: process.env.CANOPY_ENGAGEMENT_API_URL || process.env.CANOPY_TRIP_API_URL || '',
    engagementAccessToken: process.env.CANOPY_ENGAGEMENT_ACCESS_TOKEN || process.env.CANOPY_TRIP_ACCESS_TOKEN || '',
    engagementFunctionKey: process.env.CANOPY_ENGAGEMENT_FUNCTION_KEY || process.env.CANOPY_TRIP_FUNCTION_KEY || '',
    engagementAllowLocalHttp: process.env.CANOPY_ENGAGEMENT_ALLOW_LOCAL_HTTP === 'true',
    engagementUseMock: process.env.CANOPY_ENGAGEMENT_USE_MOCK === 'true',
  },
});
