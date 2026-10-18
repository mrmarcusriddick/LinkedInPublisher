# Cloud2e personal avatar video pilot

Prepared October 18, 2026 at Marcus's request. Planning and script only: no avatar
created, paid plan purchased, personal footage uploaded, or video scheduled.

## Pilot

Produce one 30–45 second LinkedIn video using Marcus's consented likeness and
voice. Begin with one video per week alongside the existing image posts; expand
only after reviewing quality and audience response. Proposed provider: HeyGen,
subject to Marcus's selection and confirmation of current plan/API entitlements.
Its official documentation describes reusable digital twins and scripted video
generation. Account and identity/voice consent must be completed by Marcus.

## First script (approximately 90 words; time against generated audio)

Before choosing a CMMC preparation provider, ask what happens after the findings
report arrives.

Who implements the changes? What does your team still own? And what records will
explain the work afterward?

At Cloud2e, our preparation services include gap assessment, technical remediation,
and documentation support.

A useful proposal should make responsibilities and deliverables clear. Ask about
ongoing support, too. No preparation provider should promise the assessor's decision.

Our Insights guide has practical questions you can use with any prospective
provider, including us. Read it through the link in this post.

Article:
https://www.cloud2e.com/insights/how-to-choose-cmmc-compliance-company/

Service claim source:
https://www.cloud2e.com/services/cmmc-compliance/

Claims checked against these public descriptions on October 16–18. Recheck before
rendering; omit certification status, pricing, deadlines, customer results and
invented first-person experience.

## Creative specification

- Start with Marcus's avatar on screen immediately; conversational delivery.
- Portrait master, 1080 by 1920, with captions positioned away from interface edges.
- Navy #05070D, blue #29A9F5, purple #7C6BFF, light gray #E2E8F0.
- Official brand/cloud2e-logo.png in a light footer; preserve proportions.
- Opening headline: “Who implements the changes?”
- Three short overlays: “Implementation”, “Responsibilities”, “Evidence”.
- End card: “Read the Cloud2e Insights guide”.
- Captioned MP4 and separate caption file; accurate spoken-word transcription.
- Clearly disclose “AI-generated avatar of Marcus Riddick” in accompanying copy.
- Review pronunciation of Cloud2e, CMMC and technical terms before approval.

## Marcus's setup step

Create/select the avatar-platform account. Follow its current in-app recording and
consent instructions for both face and voice; record consent personally. Review
its biometric-data and voice terms. Do not place footage, consent recordings,
voice samples, provider credentials or identity assets in this public repository.
Do not paste an API key into chat. Verify that the selected avatar and voice are
usable through the intended API before buying an automation plan.

Official references:
- https://help.heygen.com/en/articles/12092609-recording-your-consent-video
- https://www.heygen.com/en-gb/academy/avatars/how-to-create-a-digital-twin
- https://developers.heygen.com/
- https://www.heygen.com/api-pricing
- https://www.heygen.com/biometric-privacy-notice

## Implementation after the pilot

The existing app/media.py schema accepts PNG images only. Do not insert video
into an images manifest or change existing immutable dated content.

Proposed separate video queue: script, source URL, consented avatar reference,
render status, MP4 checksum, captions and explicit approval bound to the final
script and MP4 hash. Store identity assets and videos privately in Azure; keep
provider secrets in Key Vault. Limit render attempts and costs; report failures.
Review provider callbacks/polling and current LinkedIn Videos API documentation
before implementation. Upload, processing confirmation, duplicate prevention and
ambiguous-delivery handling must be verified before enabling video publishing.

Sequence: consented avatar setup → pilot render → Marcus reviews final video →
implement and test private video queue/publisher → enable approved video only.
Any script or render change invalidates its approval. Keep existing Azure
publishing settings and daily image-post workflow unchanged during the pilot.
