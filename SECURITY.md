# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `main` / `master` (latest commit) | Yes |
| Older commits / tags | No |

Scam Shield is a research prototype maintained on a best-effort basis.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Use one of the following private channels:

1. **GitHub Security Advisories** — open a private report from the repository's *Security* tab.
2. **Email** — [ishan.vaidya01@gmail.com](mailto:ishan.vaidya01@gmail.com) with the subject `[Scam Shield Security]`.

Please include a description, reproduction steps or proof of concept, and the affected component (extension, backend, evaluation harness).

## Scope

In scope:

- Extension permission model or data-harvesting concerns (what the extension reads and transmits).
- Injection or unsafe handling of live-chat content (which contains untrusted third-party text).
- Authentication/authorization flaws in the backend API.
- Leakage of API keys through the application or repository.

Out of scope:

- Accuracy limitations of the detector (report via a normal issue).
- Denial of service through extreme traffic.
- Issues in third-party dependencies that are already publicly known.

## Disclosure Policy

Once a fix is available, the maintainer will publish a patched version and credit the reporter unless anonymity is requested.
