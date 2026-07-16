# Security policy

## Supported version

Only latest commit on default branch receives security fixes during prototype stage.

## Reporting vulnerability

Do not open public issue containing exploit details, credentials, personal data, or infrastructure information.

Use GitHub private vulnerability reporting when available. Otherwise contact repository owner through
an established private channel.

Include:

- affected component and revision;
- reproduction steps or proof of concept;
- realistic impact;
- whether secret or personal data may be exposed;
- suggested remediation, if known.

Never include live API keys. Revoke exposed credential before sending report.

## Security boundaries

- Demo must never connect to RF equipment, public cellular network, or production controller.
- `.env` files and runtime outputs must remain untracked.
- External API credentials stay in backend only.
- Production proxy endpoints require HTTPS.
- Local mutable controller refuses production environment.

## Out of scope

This prototype is not security certification, penetration-test report, carrier approval, or regulatory attestation.
