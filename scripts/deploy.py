"""Bootstrap a NEW Azure deployment. Run locally after az login. Never enables posting."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
def az(*args):
    result = subprocess.run(['az', *args, '--only-show-errors', '-o', 'json'], check=True, capture_output=True, text=True, cwd=ROOT)
    return json.loads(result.stdout) if result.stdout.strip() else {}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--subscription', required=True)
    parser.add_argument('--resource-group', required=True)
    parser.add_argument('--location', default='eastus2')
    parser.add_argument('--suffix', required=True, help='Globally unique lowercase alphanumeric suffix, 6-10 characters')
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9]{6,10}', args.suffix):
        raise ValueError('Suffix must have 6-10 lowercase letters/digits')
    az('account', 'set', '--subscription', args.subscription)
    account = az('account', 'show')
    if account['environmentName'] != 'AzureCloud':
        raise ValueError('This deployment targets Azure commercial')
    az('extension', 'add', '--name', 'containerapp', '--upgrade')
    for provider in ['Microsoft.App', 'Microsoft.Storage', 'Microsoft.KeyVault', 'Microsoft.ManagedIdentity', 'Microsoft.ContainerRegistry']:
        az('provider', 'register', '--namespace', provider, '--wait')
    rg, region = args.resource_group, args.location
    az('group', 'create', '--name', rg, '--location', region)
    name = 'c2e' + args.suffix
    storage = az('storage', 'account', 'create', '--name', name, '--resource-group', rg, '--location', region,
        '--sku', 'Standard_LRS', '--kind', 'StorageV2', '--min-tls-version', 'TLS1_2',
        '--allow-blob-public-access', 'false', '--allow-shared-key-access', 'false')
    for container in ['queue', 'state']:
        az('storage', 'container-rm', 'create', '--storage-account', name, '--resource-group', rg, '--name', container)
    vault = az('keyvault', 'create', '--name', name, '--resource-group', rg, '--location', region, '--enable-rbac-authorization', 'true')
    identity = az('identity', 'create', '--name', name, '--resource-group', rg, '--location', region)
    registry = az('acr', 'create', '--name', name, '--resource-group', rg, '--location', region, '--sku', 'Basic', '--admin-enabled', 'false')
    def grant(role, scope):
        az('role', 'assignment', 'create', '--assignee-object-id', identity['principalId'], '--assignee-principal-type', 'ServicePrincipal', '--role', role, '--scope', scope)
    grant('Storage Blob Data Reader', storage['id'] + '/blobServices/default/containers/queue')
    grant('Storage Blob Data Contributor', storage['id'] + '/blobServices/default/containers/state')
    grant('Key Vault Secrets User', vault['id'])
    grant('AcrPull', registry['id'])
    az('containerapp', 'env', 'create', '--name', name, '--resource-group', rg, '--location', region, '--logs-destination', 'none')
    h = hashlib.sha256()
    for path in sorted([*ROOT.joinpath('app').glob('*.py'), ROOT/'Dockerfile', ROOT/'requirements.txt']):
        h.update(path.name.encode()); h.update(path.read_bytes())
    tag = 'publisher:' + h.hexdigest()[:16]
    # Build context contains no tokens; .dockerignore only includes runtime sources.
    subprocess.run(['az', 'acr', 'build', '--registry', name, '--image', tag, str(ROOT)], check=True)
    job = az('containerapp', 'job', 'create', '--name', name, '--resource-group', rg, '--environment', name,
        '--trigger-type', 'Schedule', '--cron-expression', '*/5 13,14 * * *', '--replica-timeout', '180',
        '--replica-retry-limit', '0', '--replica-completion-count', '1', '--parallelism', '1',
        '--image', registry['loginServer'] + '/' + tag, '--cpu', '0.25', '--memory', '0.5Gi',
        '--mi-user-assigned', identity['id'], '--registry-identity', identity['id'], '--registry-server', registry['loginServer'],
        '--env-vars', 'PUBLISH_ENABLED=false', 'AZURE_CLIENT_ID=' + identity['clientId'],
        'STORAGE_ACCOUNT=' + name, 'KEY_VAULT_URL=' + vault['properties']['vaultUri'],
        'LINKEDIN_API_VERSION=202609', 'LINKEDIN_PERSON_URN=UNCONFIGURED', 'LINKEDIN_ORG_URN=UNCONFIGURED')
    output = {'subscription': account['id'], 'tenant': account['tenantId'], 'resource_group': rg,
        'job': name, 'storage_account': name, 'storage_id': storage['id'], 'key_vault': name,
        'key_vault_id': vault['id'], 'registry': name, 'job_id': job['id']}
    (ROOT/'deployment.json').write_text(json.dumps(output, indent=2))
    print('Deployment created with publishing PAUSED. See deployment.json and README.md for connection steps.')

if __name__=='__main__':
    try:
        main()
    except subprocess.CalledProcessError as e:
        # No credentials are in these commands. Azure diagnostic errors are useful for bootstrap.
        print(e.stderr or 'Azure command failed. Inspect the preceding command output.')
        raise SystemExit(1)
