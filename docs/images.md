# Original images for LinkedIn

ChatGPT generates original square PNG visuals related to each day's topic using
its built-in image generation tool. No AI endpoint runs inside Azure. Use the
Cloud2e palette: navy #05070D, blue #29A9F5, purple #7C6BFF and gray #E2E8F0.
Use concise legible headlines and a CLOUD2E text wordmark. Do not invent logos,
certification badges, customer identities, screenshots or performance claims.
Inspect the generated image for text accuracy and relevance. Generate separate
personal/company images when the topics differ; one relevant image can serve both.

## Queue format and transfer

Keep existing posts/YYYY-MM-DD.json unchanged. Add a separate immutable
media/YYYY-MM-DD.json containing date and images, with personal and/or company:

```json
{"date":"2026-10-06","images":{"personal":{"path":"assets/<sha256>.png","sha256":"<64 lowercase hex characters>","alt":"Describe the visual and its headline."}}}
```

Compute SHA-256 from the exact PNG bytes. Maximum 8 MiB and fewer than 36,152,320
pixels. Supply meaningful alt text, preferably under 120 characters. Never use
arbitrary external URLs in place of an asset.

GitHub transfer can store the PNG directly at assets/<sha256>.png. When large
connector arguments are unreliable, split the unchanged bytes into 196608-byte
parts at image-parts/<sha256>/000.part, 001.part, etc. Upload each with the GitHub
create_blob tool using base64 encoding, then reference the returned blob SHA in
the tree. Base64 encodes the bytes for the API; the repository contains binary
parts, not base64 text. The importer reassembles all parts in order, validates
PNG dimensions and the complete SHA-256, and uploads the original PNG into the
private queue container. No changes to the image pixels are made.

Use `python scripts/prepare_image.py ORIGINAL.png --alt "Description"` to
produce transfer parts and image metadata without modifying the original.

Create post, media and all image/part tree entries in one commit to main, using
the freshly fetched branch head/tree and a non-force update. Never edit existing
posts or attachment manifests. Check the queue workflow logs for actual imports.
If image generation or transfer fails, report the blocker; do not claim an image
was queued or silently replace it with an unrelated graphic. Do not commit a new
post until its required images are present. Leave application and workflow code
unchanged during recurring content preparation.

## Runtime

The worker uploads images independently for each LinkedIn author. It prepares
media during the hour before posting, then publishes at 9 a.m. America/New_York
within the existing one-hour delivery window. Upload state is separate from
post delivery state. It requires LinkedIn to report AVAILABLE before posting.
Personal tokens use the legacy /v2/images status GET, because versioned
image reads do not support w_member_social alone. The /rest gateway requires
a Linkedin-Version header; removing that header does not select legacy routing.
The legacy path is inferred from LinkedIn's gateway conventions and its Images
API legacy-permission note; it still needs verification with the live token.
Organization reads retain /rest/images and the version header. A read failure is
reported, with no speculative text-only fallback. This API behavior must be
verified with the live token before enabling image publishing.

REQUIRE_IMAGES=true blocks a target if its attachment is missing. Existing
text-only behavior remains available with REQUIRE_IMAGES=false. The post state
fingerprint includes image metadata; ambiguous POST outcomes are never retried.

## Existing Azure deployment update

From Azure Cloud Shell in ~/LinkedInPublisher with the existing venv active:

```bash
git pull --ff-only
python -m app.check_image
```

The check uploads and verifies the October 6 personal image but does not create a
public post. It uses the already granted Key Vault and state-container access.
If image_processing is returned, run again shortly. Do not proceed on an API error.
To explicitly publish one additional public test instead, use
`python -m app.check_image --publish`. The fixed test state prevents duplicates.

After image_ready, build and update the existing job:

```bash
publisher_tag="publisher:$(git rev-parse --short=16 HEAD)"
az acr build --registry c2ea2e23015 --image "$publisher_tag" .
az containerapp job update --resource-group rg-cloud2e-publisher \
  --name c2ea2e23015 --image "c2ea2e23015.azurecr.io/$publisher_tag" \
  --cron-expression '*/5 12,13,14 * * *' \
  --set-env-vars REQUIRE_IMAGES=true --output none
```

The UTC cron covers pre-upload and 9 a.m. Eastern across daylight saving changes.
The code enforces local hours. PUBLISH_ENABLED is preserved; this command does
not activate a paused publisher. Company publishing still requires its separate
approved LinkedIn app/token and organization URN. No additional storage resource
or role is needed by the deployed worker or existing queue-import identity.
