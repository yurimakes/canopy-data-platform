"""Deploy only the integrated API to main Azure; never changes Databricks resources.

Private settings/package backups stay in ignored .local-data/main-review/main-api.
Default prepares and validates locally. --apply updates only specified app settings
and the Function package, preserving unrelated settings and existing functions.
"""
import argparse
import hashlib
import json
import subprocess
import zipfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from package_trip_api import package

ROOT = Path(__file__).resolve().parents[2]
SUB = '27db5ec6-d206-4028-b5e1-6004dca5eeef'
GROUP = '5dt-2nd-team1'
APP = 'func-canopy-dev'
HOST = 'func-canopy-dev-dxb0bgdgd6gghpd3.koreacentral-01.azurewebsites.net'
AZ = r'C:/Program Files/Microsoft SDKs/Azure/CLI2/wbin/az.cmd'


def az(*args):
    result = subprocess.run([AZ, *args, '--subscription', SUB,
                             '--only-show-errors', '-o', 'json'], capture_output=True,
                            encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Azure command failed: ' + ' '.join(args[:2]) +
                           ' (output withheld; may contain credentials)')
    if not result.stdout.strip():
        return {}
    # ARM long-running CLI responses can contain multiple JSON documents.
    remaining = result.stdout.strip()
    values = []
    while remaining.startswith(('{', '[')):
        value, end = json.JSONDecoder().raw_decode(remaining)
        values.append(value)
        remaining = remaining[end:].strip()
    return values[-1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    out = ROOT / '.local-data/main-review/main-api'
    out.mkdir(parents=True, exist_ok=True)
    app = az('functionapp', 'show', '-g', GROUP, '-n', APP)
    properties = app.get('properties', app)
    if properties.get('defaultHostName') != HOST:
        raise ValueError('Unexpected destination')
    old = az('functionapp', 'config', 'appsettings', 'list', '-g', GROUP, '-n', APP)
    settings = {r['name']: r['value'] for r in old}
    if settings.get('COSMOS_TRIPS_DATABASE') != 'canopy-db':
        raise ValueError('Unexpected existing Trip database')
    if not (out / 'settings-before.json').exists():
        (out / 'settings-before.json').write_text(json.dumps(old), encoding='utf-8')
    # Preserve the current executable package for rollback before changing anything.
    from azure.storage.blob import BlobServiceClient
    container_name = properties['functionAppConfig']['deployment']['storage']['value'].rsplit('/', 1)[1]
    blobs = BlobServiceClient.from_connection_string(settings['DEPLOYMENT_STORAGE_CONNECTION_STRING']).get_container_client(container_name)
    for blob in blobs.list_blobs():
        if blob.name.endswith('.zip'):
            dest = out / ('before-' + hashlib.sha256(blob.name.encode()).hexdigest()[:12] + '.zip')
            if not dest.exists():
                dest.write_bytes(blobs.download_blob(blob.name).readall())
    target = package(ROOT, include_runtime=True)
    source_hash = hashlib.sha256()
    for file in sorted(target.rglob('*')):
        if file.is_file() and '__pycache__' not in file.parts:
            source_hash.update(file.relative_to(target).as_posix().encode())
            source_hash.update(file.read_bytes())
    release_id = source_hash.hexdigest()
    (target / 'release-id.txt').write_text(release_id)
    expected = set(json.loads((target / 'function-manifest.json').read_text())['functions'])
    live = az('functionapp', 'function', 'list', '-g', GROUP, '-n', APP)
    missing = {r['name'].rsplit('/', 1)[-1] for r in live} - expected
    if missing:
        raise ValueError('Package omits existing functions: ' + str(sorted(missing)))
    archive = out / 'functions.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for file in target.rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts:
                z.write(file, file.relative_to(target).as_posix())
    updates = {
        'APP_ENV': 'production', 'TRIP_AUTH_MODE': 'jwt',
        'CANOPY_ACCOUNT_AUTH_ENABLED': 'true', 'CANOPY_ALLOW_DEV_USER_HEADER': 'false',
        'CANOPY_COMMUNITY_ENABLED': 'true', 'CANOPY_FEATURE_CONTAINERS': 'true',
        'CANOPY_LOCAL_ONLY': 'false', 'TRIP_PROCESS_ON_STOP': 'false',
        'TRIP_RESULT_OWNER': 'databricks', 'TRIP_END_EVENTS_ENABLED': 'true',
        'TRIP_DATABRICKS_ENABLED': 'true', 'TRIP_DATABRICKS_DISPATCH_MODE': 'resident',
        'TRIP_DATABRICKS_HOST': 'https://adb-7405612422597045.5.azuredatabricks.net',
        'TRIP_DATABRICKS_JOB_ID': settings.get('TRIP_DATABRICKS_JOB_ID', '421770332247848'),
    }
    (out / 'settings-update.json').write_text(json.dumps(updates), encoding='utf-8')
    receipt = {'subscription': SUB, 'app': APP, 'functions': sorted(expected),
               'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
               'release_id': release_id, 'databricks_resources_changed': False, 'deployed': False}
    (out / 'prepared.json').write_text(json.dumps(receipt, indent=2))
    print(json.dumps(receipt), flush=True)
    if args.apply:
        az('functionapp', 'config', 'appsettings', 'set', '-g', GROUP, '-n', APP,
           '--settings', '@' + str(out / 'settings-update.json'))
        print('Deploying main API package with remote build...', flush=True)
        # Flex OneDeploy through ARM also works when the SCM endpoint denies ZIP upload.
        # The source SAS is read-only and short lived; no URL/key is logged.
        from azure.storage.blob import generate_blob_sas, BlobSasPermissions
        connection = dict(part.split('=', 1) for part in settings['DEPLOYMENT_STORAGE_CONNECTION_STRING'].split(';') if '=' in part)
        name = 'releases/' + receipt['sha256'] + '.zip'
        blobs.upload_blob(name, archive.read_bytes(), overwrite=True)
        sas = generate_blob_sas(connection['AccountName'], container_name, name,
            account_key=connection['AccountKey'], permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=1))
        import requests
        token = az('account', 'get-access-token')['accessToken']
        result = requests.put(
            f'https://management.azure.com/subscriptions/{SUB}/resourceGroups/{GROUP}/providers/Microsoft.Web/sites/{APP}/extensions/onedeploy?api-version=2022-09-01',
            headers={'Authorization': 'Bearer ' + token}, timeout=120,
            json={'properties': {'packageUri': blobs.url + '/' + name + '?' + sas, 'remoteBuild': True}})
        if not result.ok:
            raise RuntimeError('OneDeploy rejected request: HTTP ' + str(result.status_code))
        # The ARM response can append HTML after JSON; do not treat submission as completion.
        deadline = time.monotonic() + 900
        function_key = az('functionapp', 'keys', 'list', '-g', GROUP, '-n', APP)['functionKeys']['default']
        while time.monotonic() < deadline:
            try:
                health = requests.get('https://' + HOST + '/api/health',
                    headers={'x-functions-key': function_key}, timeout=30)
                if health.ok and health.json().get('release') == release_id:
                    break
            except (requests.RequestException, ValueError):
                pass
            time.sleep(10)
        else:
            raise RuntimeError('Function registration timeout; inspect OneDeploy status')
        receipt['deployed'] = True
        (out / 'deployed.json').write_text(json.dumps(receipt, indent=2))
        print('Package deployment completed; HTTP acceptance checks required.', flush=True)


if __name__ == '__main__':
    main()
