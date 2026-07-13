# Security Policy

Space Adventures takes the security of user data (credentials, PII, location,
notification consent records) seriously. See `Architecture/10-security.md` for
the security controls and `Architecture/25-security-testing.md` for how they
are verified.

## Reporting a Vulnerability

Please report suspected vulnerabilities to **security@spaceadventures.app**.

Include, where possible:

- A description of the vulnerability and its potential impact.
- Steps to reproduce (a minimal PoC is ideal).
- The affected URL(s)/endpoint(s) or component.

Do not open a public GitHub issue for security reports.

## Disclosure Process

- We aim to acknowledge reports within **3 business days**.
- We follow a **90-day coordinated disclosure** timeline from acknowledgement:
  we will work to remediate the issue within that window and coordinate public
  disclosure with the reporter. If a fix needs more time, we will communicate
  progress and, where reasonable, request an extension rather than let the
  window lapse silently.
- Reporters acting in good faith and within this policy will not face legal
  action from us for their research.

## Scope

In scope: the production application at the app's public domain and its API.
Out of scope: third-party services we depend on (NASA/LL2/N2YO/NOAA/CelesTrak/
Horizons/DeepL/Twilio/email providers) — report those to the respective
vendor.

## Secret Rotation

See `Architecture/12-deployment.md` § Secret Rotation Runbook for the
per-secret rotation procedure and the compromised-dependency response.
