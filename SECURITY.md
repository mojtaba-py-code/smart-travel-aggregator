# Security Policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

Security fixes are applied to `main` and released from there.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's
[Report a vulnerability](https://github.com/mojtaba-py-code/smart-travel-aggregator/security/advisories/new)
form, or by email to **mojtaba.python@gmail.com**.

Include what you can:

- the affected version, tag or commit,
- what the issue is and what an attacker gains from it,
- steps or a minimal proof of concept that reproduces it.

## What to expect

- Acknowledgement within **72 hours**.
- An initial assessment within **7 days**.
- A fix and a published advisory once a patch is ready.
- Credit in the advisory, if you want it.

## Scope

In scope: the code in this repository — the API surface, the authentication and
authorization layer, the provider adapters, and anything that handles a request
or a secret.

Out of scope:

- Vulnerabilities in third-party dependencies — report those upstream; if this
  project's use of a dependency is what makes it exploitable, that *is* in scope.
- The demo deployment on Render's free tier. It exists to show the API working,
  runs with throwaway credentials and non-production settings, and is not a
  target — report issues against the code, not that host.
- Findings that require an attacker to already control the host or the process.

## Notes for operators

`SECRET_KEY` must be a real random value in any deployment — generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never reuse the
value from `.env.example`. Provider API keys belong in the environment, never in
the repository.
