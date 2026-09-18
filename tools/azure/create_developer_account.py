"""기존 users에 개발자 계정 최초 등록. 공개 회원가입으로 권한 지정 불가."""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps/api'))
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from services.accounts import Accounts, CampaignRegistry


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--database', default='canopy-db')
    parser.add_argument('--campaign-id', required=True)
    parser.add_argument('--login', default='canopydev')
    args = parser.parse_args()
    password = getpass.getpass('개발자 비밀번호 (12자 이상): ')
    if password != getpass.getpass('비밀번호 확인: '):
        raise ValueError('비밀번호가 일치하지 않습니다.')
    container = CosmosClient(args.endpoint, credential=DefaultAzureCredential()).get_database_client(args.database).get_container_client('users')
    if container.read()['partitionKey']['paths'] != ['/user_id']:
        raise RuntimeError('users partition key must be /user_id')
    api = Accounts(container, CampaignRegistry(args.campaign_id))
    result = api.signup({'email': args.login, 'password': password, 'nickname': '개발자', 'campaign_code': 'TEST'}, developer=True)
    api.logout(result['access_token'])
    print('개발자 계정 등록 완료:', result['profile']['id'])


if __name__ == '__main__':
    main()
