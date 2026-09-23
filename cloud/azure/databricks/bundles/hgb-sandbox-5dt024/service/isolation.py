"""Fail closed on any attempted access outside this sandbox's exact tables."""
CATALOG='dbw_canopy_trial'
SCHEMA='sandbox'
PREFIX='m5dt024_'
TABLES={role:f'{CATALOG}.{SCHEMA}.{PREFIX}{name}' for role,name in [('gps','silver_gps_observations'),('ended','silver_trip_ended_events'),('results','gold_hgb_results')]}
def require_table(value,role):
    if value!=TABLES[role]:raise ValueError('Only the dedicated 5dt024 sandbox table is allowed: '+role)
    return value
