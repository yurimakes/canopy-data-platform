"""고정 버전의 KTDB 코드·참조자료·가중치 준비. Azure 접근 없음."""
from pathlib import Path
import subprocess
import hashlib

ROOT=Path(__file__).resolve().parents[2]
REPO='https://github.com/Hayden-Shin-Dev/canopy-data-platform.git'
CODE='1ec4e99d396886fe23502a6254888fb8df127128'
WEIGHTS='c72d26762697756cf3464d2a0285acf0e818a0c0'
SHA='790a9177f5dff5bcada6330fac7d65a2b2e2da3294e2e70351c36a78e08f523b'


def main():
    target=ROOT/'.local-data/reference-model'
    if not (target/'.git').exists():
        subprocess.run(['git','clone',REPO,str(target)],check=True)
    def git(*args):return subprocess.check_output(['git','-C',str(target),*args])
    for commit in (CODE,WEIGHTS):
        if subprocess.run(['git','-C',str(target),'cat-file','-e',commit],capture_output=True).returncode:
            subprocess.run(['git','-C',str(target),'fetch','origin',commit],check=True)
    # 참조 코드가 임의로 달라진 상태에서는 자동 덮어쓰기 금지
    if git('rev-parse','HEAD').decode().strip()!=CODE:
        if git('status','--porcelain').strip():raise RuntimeError('참조 저장소의 수정사항 확인 필요')
        subprocess.run(['git','-C',str(target),'checkout','--detach',CODE],check=True)
    artifact=git('show',WEIGHTS+':models/expected_behaviour/ktdb_population_baseline.pkl')
    if hashlib.sha256(artifact).hexdigest()!=SHA:raise RuntimeError('KTDB 모델 무결성 오류')
    model=ROOT/'.local-data/models/ktdb_population_baseline.pkl'
    model.parent.mkdir(parents=True,exist_ok=True)
    model.write_bytes(artifact)
    print('KTDB model ready:',model)


if __name__=='__main__':main()
