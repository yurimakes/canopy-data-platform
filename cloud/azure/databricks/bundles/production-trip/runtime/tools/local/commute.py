"""Verify commute endpoints against the profile captured when the Trip started."""
from model import distance,stamp
from rewards import extension_policy


def verify(trip,points):
    context=trip.get('start_context') or {}
    home,work=context.get('home'),context.get('work')
    if trip.get('is_mock') or not home or not work:return False
    if any('행정동 중심점' in p.get('address','') for p in (home,work)):return False
    if (trip.get('data_quality') or {}).get('status')=='partial':return False
    if trip.get('status')!='ready' or not trip.get('ended_at'):return False
    valid=sorted([p for p in points if stamp(trip['started_at'])<=stamp(p['event_time'])<=stamp(trip['ended_at'])
                  and p.get('accuracy') is not None and 0<=p['accuracy']<=100],key=lambda p:p['event_time'])
    if len(valid)<2:return False
    if (stamp(valid[0]['event_time'])-stamp(trip['started_at'])).total_seconds()>120:return False
    if (stamp(trip['ended_at'])-stamp(valid[-1]['event_time'])).total_seconds()>120:return False
    def point(p):return {'lat':p['latitude'],'lon':p['longitude']}
    radius=extension_policy()['endpoint_radius_m']
    # Overlapping home/work zones cannot establish a directional commute.
    if distance(point(home),point(work))<=2*radius:return False
    return any(distance(valid[0],point(a))<=radius and distance(valid[-1],point(b))<=radius for a,b in ((home,work),(work,home)))
