# Approved logo replacement — October 7, 2026

Marcus requested replacing the plain wordmark in the October 7–9 queued graphics
with the supplied official Cloud2e logo. Post text is unchanged. Original attachment
metadata is retained in operator/logo-original-media for guarded comparison.

Changing repository attachment metadata does not overwrite the immutable Azure
queue automatically. The queue importer may report an attachment conflict until
the operator applies this explicitly authorized replacement.

From the repository with its virtual environment active:

```bash
python -m app.replace_logo_images --apply
```

The command uses the signed-in Azure CLI Entra identity. Shared-key authentication
remains disabled. The operator needs Storage Blob Data Contributor on the queue
and state containers; no role assignments are changed by the helper.
It validates local assets, checks the existing attachment and post delivery state,
briefly pauses publishing, waits for active executions to finish, uploads and
verifies assets, holds post-state leases, and replaces known attachment versions
using ETag conditions. It restores the previous PUBLISH_ENABLED value after success.
It never resets a delivery record or publishes to LinkedIn. A partial failure leaves
publishing paused; resolve the reported error before restoring it. Dates with an
existing delivery record require separate review and cannot be replaced by this command.

Rerun the Validate and import post queue workflow after the replacement to confirm
all repository and Azure files match. Already-updated assets and attachments are
verified without repeating the replacement.
