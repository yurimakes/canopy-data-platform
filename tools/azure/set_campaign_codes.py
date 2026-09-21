"""Replace the main API signup allowlist. No database migration or pipeline changes."""
import argparse,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
AZ='C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd'
BASE=['--subscription','27db5ec6-d206-4028-b5e1-6004dca5eeef','-g','5dt-2nd-team1','-n','func-canopy-dev']
def run(args):
    p=subprocess.run([AZ,*args,*BASE,'--only-show-errors','-o','json'],capture_output=True,encoding='utf-8')
    if p.returncode:raise RuntimeError('Campaign setting update failed; inspect Azure configuration')
    return json.loads(p.stdout)
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--registry',default=str(ROOT/'config/campaigns.main.json'));parser.add_argument('--apply',action='store_true');a=parser.parse_args()
    registry=json.loads(Path(a.registry).read_text(encoding='utf-8-sig'))
    if not isinstance(registry,dict):raise ValueError('Registry must be an object')
    for code,entry in registry.items():
        if not code or len(code)>20 or code!=code.strip().upper():raise ValueError('Use uppercase codes of 1-20 characters')
        if not isinstance(entry,dict) or not isinstance(entry.get('campaign_id'),str) or not entry['campaign_id'].strip() or not isinstance(entry.get('accepting_signups'),bool):raise ValueError('Invalid campaign entry')
    print(json.dumps({'signup_codes':registry,'apply':a.apply},ensure_ascii=False))
    if not a.apply:return
    folder=ROOT/'.local-data/campaign-config';folder.mkdir(parents=True,exist_ok=True)
    old=run(['functionapp','config','appsettings','list'])
    (folder/'before.json').write_text(json.dumps({r['name']:r['value'] for r in old if r['name']=='CANOPY_CAMPAIGNS_JSON'}),encoding='utf-8')
    target=folder/'update.json';target.write_text(json.dumps({'CANOPY_CAMPAIGNS_JSON':json.dumps(registry)}),encoding='utf-8')
    run(['functionapp','config','appsettings','set','--settings','@'+str(target)])
    actual={r['name']:r['value'] for r in run(['functionapp','config','appsettings','list'])}
    assert json.loads(actual['CANOPY_CAMPAIGNS_JSON'])==registry
    print('Verified main API campaign allowlist.')
if __name__=='__main__':main()
