# Cloud2e LinkedIn publisher — Azure deployment package

A working Python publishing worker and Azure bootstrap scripts. ChatGPT supplies
text through this GitHub repository; Azure publishes queued text to the
personal profile and Cloud2e page daily at **9:00 a.m. America/New_York**.
No OpenAI/Azure OpenAI key or Metricool subscription is used by this code.

**Current status:** source prepared and core tests run locally. No Azure resources,
LinkedIn posts or ChatGPT schedules have been created by preparing this package.
Azure deployment and live LinkedIn delivery still require integration testing.
This first version is a queue/worker with GitHub as the editing surface, not a
web dashboard. The destinations use separate LinkedIn applications and Key Vault secrets:
`linkedin-token-personal` and `linkedin-token-company`. Each token must carry its
own publishing permission. No shared-token fallback is used.

## Flow

1. A ChatGPT Work scheduled task prepares upcoming posts at 8 a.m. Eastern and
   creates `posts/YYYY-MM-DD.json` in the connected GitHub repository.
2. GitHub Actions validates and imports the immutable daily pair into Azure Blob
   Storage, using federated Azure login rather than a client secret.
3. An Azure Container Apps Job wakes every five minutes during 13:00-14:55 UTC.
   The worker calculates local Eastern time and only publishes from 9-10 a.m.
   This handles US daylight saving transitions. Target is 9 a.m.; cold starts,
   service outages and rate limits can delay delivery. Posts are skipped after
   the one-hour window, not unexpectedly published later in the day.
4. One leased state record per destination/date prevents overlapping executions
   from sending twice. A success on one destination does not cause a repeat when
   the other fails. Ambiguous timeouts/5xx/crashes stop for manual reconciliation.

No external publisher offers absolute exactly-once delivery without a server-side
idempotency key. This implementation favors avoiding duplicates over automatic
retries of uncertain requests. Never delete state records to retry blindly.

## Prerequisites

- Azure commercial subscription and Azure CLI with permission to create resources
  and role assignments. Choose your own region and globally unique suffix.
- Python 3.12; Docker is built remotely using Azure Container Registry.
- A GitHub repository you authorize ChatGPT to read/write. This repository is
  currently public: queued marketing posts will be visible before publication.
  Make it private before using it if you want unpublished drafts kept private.
- LinkedIn developer app: `w_member_social` plus `w_organization_social` with
  approved product access and an eligible role on the Cloud2e page.
- Verified personal and company author URNs. Do not derive a person URN from
  the public profile slug. Use the authenticated LinkedIn identity/API output.
- A supported LinkedIn API version. Bootstrap defaults to `202609`; update it
  as LinkedIn versions retire. Do not assume versions work forever.

## 1. Deploy (creates billable Azure resources)

Source repository: https://github.com/mrmarcusriddick/LinkedInPublisher

Clone this repository and keep the default branch `main`.
From the folder, after `az login`:

```bash
python scripts/deploy.py --subscription YOUR_SUBSCRIPTION_ID --resource-group rg-cloud2e-publisher --location eastus2 --suffix YOURUNIQUE
```

The script creates Storage, Key Vault, a user-assigned managed identity, a Basic
container registry, a Container Apps environment and a paused publishing job.
`deployment.json` contains resource identifiers, not credentials, and is ignored
by Git. Bootstrap is for a NEW installation, not the software update mechanism.
If interrupted, inspect existing resources before rerunning. RBAC propagation
may delay the first image pull; retry only that failed operation once roles apply.

Costs are NOT guaranteed to be zero: ACR Basic has a standing charge; Azure job
compute, storage, Key Vault and builds can incur charges. GitHub Actions and
ChatGPT usage are subject to your plan. No Log Analytics workspace is created;
publication state persists in Blob Storage, but long-term console log retention
and proactive notifications are not configured. Set an Azure budget in your
subscription before enabling regular operation if desired.

## 2. Connect GitHub to Azure

```bash
python scripts/setup_github.py --repo mrmarcusriddick/LinkedInPublisher
```

Run once; it creates a dedicated Entra application/service principal and an OIDC
federated credential. It grants Blob Data Contributor only on the queue container,
not on the state ledger or Key Vault. Creating this app requires directory rights.
In GitHub, create environment `production`, restrict deployment branches to `main`,
and add the four environment variables printed by this script. Do not put a
required human approval gate on the queue-import environment if you want unattended
posting. Restrict repository writes to trusted maintainers; protect workflow changes.
The runtime managed identity can read queue, write state, pull the image and read
secrets. It has no GitHub token.

## 3. Connect LinkedIn

Create/verify a LinkedIn developer app associated with Cloud2e. Request Share on
LinkedIn and the appropriate organization publishing product access. Complete
LinkedIn's OAuth authorization-code flow with the authorized member, using a
registered redirect URI. LinkedIn's official OAuth token tooling/Postman flow may
be used during initial setup; follow the primary documentation linked below.
Record the returned token's actual expiry (`expires_in` relative to issuance),
not an assumed lifetime. Renewal may require reauthorization; this version does
not assume refresh tokens are available to your app.

Grant your setup identity Key Vault Secrets Officer on THIS vault, then run:

```bash
python -m venv .venv
# Activate .venv for your shell, then:
pip install -r requirements.txt
python scripts/set_linkedin_token.py --target personal
# Once company access is approved:
python scripts/set_linkedin_token.py --target company
```

The helper reads the token without echo and writes it directly to Key Vault.
Never paste LinkedIn tokens into ChatGPT, GitHub issues, source files or workflow logs.
Using your verified URNs and the names in deployment.json, configure the job:

```bash
az containerapp job update --resource-group YOUR_RG --name YOUR_JOB --set-env-vars LINKEDIN_PERSON_URN=urn:li:person:YOUR_MEMBER_ID LINKEDIN_ORG_URN=urn:li:organization:YOUR_PAGE_ID
```

The URNs are identifiers, not secrets. Verify both destinations and scopes before
activation. Token expiry causes a failed execution with `reauthorization_required`.
A seven-day warning is emitted to stdout; no email/SMS integration is configured.

## 4. Activate only after the connections are verified

Give ChatGPT the exact OWNER/REPO and verify a harmless GitHub read. Use the
specification in `docs/agent-prompt.md` to create the 8 a.m. daily preparation task.
It maintains a three-day buffer; two posts per day still publish at 9 a.m.
The preparation task cannot be activated as part of this offline package.

Before enabling, create the first real content file and confirm the queue workflow
succeeds and its blob exists. No sample posts are in the live queue. Example shape:

```json
{
  "date": "YYYY-MM-DD",
  "posts": {
    "personal": "Your personal post text",
    "company": "Cloud2e company post text"
  },
  "sources": ["https://www.cloud2e.com/services/"]
}
```

Then enable the Azure worker:

```bash
az containerapp job update --resource-group YOUR_RG --name YOUR_JOB --set-env-vars PUBLISH_ENABLED=true
```

A manual execution outside the 9-10 a.m. window will not publish. Verify a live
publication on each destination during the first scheduled run, then inspect
`state/YYYY-MM-DD-personal.json` and `state/YYYY-MM-DD-company.json` for the returned
LinkedIn post IDs. GitHub queue import success alone does NOT mean published.

## Pause, errors and edits

Pause: set `PUBLISH_ENABLED=false` using the same update command. An execution
already running may finish; stop it separately if necessary. Resume with true.
Stop the ChatGPT task separately if you also want content generation paused.

- `blocked`: rejected request (e.g. 401/403). Fix authorization/content first.
- `unknown`: possible successful delivery. Check LinkedIn manually before any reset.
- `published`: final, never automatically retried.
- `queued` with retry_at: explicit 429; retry no sooner than Retry-After.
- `missing_content`: no item for today; no fabricated or fallback post is sent.
- `configuration_or_storage_failure`: fix the named service/configuration problem.

To amend an already imported future post: pause, ensure no worker is running,
edit the repository file, and deliberately replace its queue blob with the exact
canonical JSON from `app.core.canonical`. The ordinary importer refuses to overwrite
existing content. Do not change a published or uncertain date. A changed content
hash after an attempt is blocked by the ledger. State resets are operator-only
recovery actions after verifying whether a post exists; preserve a copy for audit.

## Software updates and validation

Run the tests; build a NEW image tag with `az acr build`; update only the job image
with `az containerapp job update --image ...`. Do not rerun the bootstrap to update
code, because that initializes publishing to paused and author URNs to unconfigured.

```bash
python -m unittest discover -s tests -v
python -m app.import_queue --validate-only
```

Tests cover DST, time windows, persist-before-send, duplicate suppression, partial
success, uncertain delivery, rate limits and content conflicts. Azure Blob leases,
RBAC, OAuth, API-version compatibility and LinkedIn access need live validation in
your environment. No live LinkedIn call is made by the tests.

## Sources

- Company brief: https://www.cloud2e.com/ and https://www.cloud2e.com/services/
- LinkedIn posts: https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
- LinkedIn OAuth: https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow
- LinkedIn access: https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access
- Azure jobs: https://learn.microsoft.com/en-us/azure/container-apps/jobs
- Azure billing: https://learn.microsoft.com/en-us/azure/container-apps/billing
- ChatGPT scheduled tasks/plugins: https://learn.chatgpt.com/docs/automations

## Separate-token update (October 5, 2026)

The repository now supports separate apps and tokens. The originally deployed
image still uses a shared token until rebuilt and updated; do not activate that
older image. A missing/expired token or unconfigured author skips that destination
without sending its content under the other account. The job reports a failure
until both destinations are configured, even if one succeeds. Existing successful
state records still prevent duplicate posts. No posting was enabled by this update.

## Original post images

Image upload, readiness checks, alt text, and immutable media attachments are now
supported. See [image setup and content workflow](docs/images.md). For the
existing Cloud2e deployment, run `bash scripts/update_images.sh` after pulling
this update. It verifies a personal image before updating the job and preserves
the current publishing enabled/paused setting.
