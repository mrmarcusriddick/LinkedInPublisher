"""Create a dedicated federated GitHub uploader identity (no client secret)."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from deploy import az, ROOT

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, help='OWNER/REPO')
    args=parser.parse_args()
    if args.repo.count('/')!=1 or any(c.isspace() for c in args.repo): raise ValueError('Use OWNER/REPO')
    d=json.loads((ROOT/'deployment.json').read_text())
    az('account','set','--subscription',d['subscription'])
    app=az('ad','app','create','--display-name','Cloud2e queue '+args.repo)
    sp=az('ad','sp','create','--id',app['appId'])
    # Environment binding: create the production environment in GitHub and restrict it to main.
    fed={'name':'github-production','issuer':'https://token.actions.githubusercontent.com',
         'subject':f'repo:{args.repo}:environment:production','audiences':['api://AzureADTokenExchange']}
    with tempfile.TemporaryDirectory() as temp:
        path=Path(temp)/'federation.json';path.write_text(json.dumps(fed))
        az('ad','app','federated-credential','create','--id',app['id'],'--parameters',str(path))
    az('role','assignment','create','--assignee-object-id',sp['id'],'--assignee-principal-type','ServicePrincipal',
       '--role','Storage Blob Data Contributor','--scope',d['storage_id']+'/blobServices/default/containers/queue')
    print(json.dumps({'AZURE_CLIENT_ID':app['appId'],'AZURE_TENANT_ID':d['tenant'],
        'AZURE_SUBSCRIPTION_ID':d['subscription'],'STORAGE_ACCOUNT':d['storage_account']},indent=2))

if __name__=='__main__': main()
