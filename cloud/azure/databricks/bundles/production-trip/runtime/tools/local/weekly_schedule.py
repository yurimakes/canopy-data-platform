"""KST rollover decision, reusable by a local loop or a hosted timer."""
from datetime import datetime
from zoneinfo import ZoneInfo

def due(report,now=None):
    now=now or datetime.now(ZoneInfo('Asia/Seoul'))
    completed=report.get('completed_at')
    if not completed:return True
    at=datetime.fromisoformat(completed.replace('Z','+00:00'))
    return at.astimezone(ZoneInfo('Asia/Seoul')).strftime('%G-W%V')<now.astimezone(ZoneInfo('Asia/Seoul')).strftime('%G-W%V')

def run_loop(data,run,export):
    import os,time,logging
    from business import read_rows
    if os.getenv('CANOPY_LOCAL_WEEKLY_AUTO','true').lower()!='true':return
    retry_at=0
    while True:
        try:
            if time.monotonic()>=retry_at and due(read_rows(data/'weekly/run.json') or {}):
                from reward_baselines import week_of
                if any(t.get('status')=='ready' and not t.get('is_mock') and week_of(t['started_at'])<week_of() for t in export()):
                    run(True)
                    retry_at=time.monotonic()+3600
        except Exception:
            logging.exception('weekly_schedule_failed')
            retry_at=time.monotonic()+3600
        time.sleep(60)
