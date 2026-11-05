# Contributing to Scam Shield

Thanks for your interest in improving Scam Shield, a research prototype for detecting coordinated scam campaigns in YouTube live chat. This document covers setup, conventions, and pull-request expectations.

## Code of Conduct

By participating, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Report unacceptable behavior to ishan.vaidya01@gmail.com.

## Getting Started

1. Fork the repository and clone your fork.
2. Follow the setup instructions in [README.md](README.md).
3. Create a branch from `main`:

   ```bash
   git checkout -b feat/timing-synchrony-signal
   # or
   git checkout -b fix/eval-metric-bug
   ```

## Development Checks

Run these before opening a pull request:

- Python: verify imports/compile (`python -m compileall .` from the relevant package roots) and run the evaluation suite your change touches.
- Extension/demo: load the extension locally and run a capture against the demo harness.
- Keep experimental notebooks and scratch files out of version control.

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

```text
feat: add inter-arrival time synchrony feature
fix: correct false-positive rate calculation in eval
refactor: extract campaign scoring into a service
docs: expand evaluation methodology section
chore: update detector dependencies
```

The subject should be in the imperative mood and under ~72 characters.

## Coding Guidelines

- Preserve the separation between data capture (extension), feature computation (backend/ml), and evaluation (eval/).
- Detector changes should document precision/recall impact when measurable.
- Commit evaluated metrics alongside code changes so results are reproducible.
- Annotate heuristics and thresholds with the reasoning behind their values.
- Never commit `.env`, API keys, chat dumps with personal data, or large raw datasets.

## Pull Request Checklist

- [ ] The change is focused on one problem.
- [ ] Python code compiles and relevant evaluation runs.
- [ ] New features, thresholds, or metrics are documented in the README/eval notes.
- [ ] No secrets, personal data, or raw chat dumps are included.
- [ ] The PR description explains the change, motivation, and measured effect.

## Reporting Bugs and Requesting Features

Use the GitHub issue templates. Include steps to reproduce, sample chat data (scrubbed of personal information), and environment details.

## Security

Do not open public issues for security problems. Follow [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the project's [MIT License](LICENSE).
