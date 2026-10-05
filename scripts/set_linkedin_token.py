"""Prompt securely; store token only in Azure Key Vault, never in source or stdout."""
import argparse
import getpass
import json
from datetime import datetime, timezone
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True, choices=['personal', 'company'])
    args = parser.parse_args()
    d=json.loads((Path(__file__).resolve().parents[1]/'deployment.json').read_text())
    token=getpass.getpass('LinkedIn access token (hidden): ').strip()
    expiry=input('Token expiry in ISO 8601 with timezone, e.g. 2026-11-01T12:00:00+00:00: ').strip()
    parsed=datetime.fromisoformat(expiry)
    if not token or parsed.tzinfo is None or parsed<=datetime.now(timezone.utc):
        raise ValueError('A nonempty token and future timezone-aware expiry are required')
    SecretClient(vault_url=f"https://{d['key_vault']}.vault.azure.net",credential=DefaultAzureCredential()).set_secret(
        'linkedin-token-' + args.target,json.dumps({'access_token':token,'expires_at':parsed.isoformat()}))
    print(f'{args.target} token saved to Key Vault. Publishing was not enabled.')

if __name__=='__main__': main()
