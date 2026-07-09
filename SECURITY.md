# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security reports.

Use GitHub Private Vulnerability Reporting on this repository, or email **yupeng@cookiy.com** with:

- Affected version / commit
- Reproduction steps
- Impact assessment

We aim to acknowledge reports within 14 days.

## Scope notes

- Provider API keys must stay in environment variables; the project must never persist or upload secrets.
- Do not use this project to scan or probe repositories/systems you do not own.
