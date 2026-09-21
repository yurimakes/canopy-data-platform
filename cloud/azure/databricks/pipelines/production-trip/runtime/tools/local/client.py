"""로컬 서버 상태 조회, 입력 내보내기, 확정 ML 결과 입력."""
import argparse
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['status','export','import-result'])
    parser.add_argument('--file',type=Path)
    parser.add_argument('--port',type=int,default=8010)
    args=parser.parse_args()
    base=f'http://127.0.0.1:{args.port}/api/'
    def call(path,body=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(base+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(request,timeout=15) as response:return json.loads(response.read())
    if args.action=='status':
        print(json.dumps(call('local/status'),ensure_ascii=False,indent=2));return
    settings=json.loads((ROOT/'.local-data/local-settings.json').read_text())
    session=call('auth/login',{'email':'canopydev','password':settings['developer_password']})
    token=session['access_token']
    try:
        if args.action=='export':print(call('local/export',{},token))
        else:
            if not args.file:parser.error('--file is required')
            print(call('local/ml-result',json.loads(args.file.read_text(encoding='utf-8-sig')),token))
    finally:call('auth/logout',{},token)


if __name__=='__main__':main()
