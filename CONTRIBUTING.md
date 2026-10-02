# Contributing

## Scope

Prefer bounded parsers, explicit format hypotheses, synthetic fixtures, and evidence-backed documentation. Keep unrecognized payloads raw and label uncertainty; never silently claim an export succeeded when validation failed.

## Data handling

Do not commit firmware packages, unit exports, extracted firmware trees, production credentials, or vehicle-identifying data. Before staging, review `git status` and the complete diff; `.gitignore` is only a safeguard.

## Tests

Run `python -m unittest discover -s tests -v` before opening a pull request. Include small synthetic tests for new file-format behavior and malformed-input boundaries.

## License

Project-authored contributions are offered under GPL-3.0-only. Retain third-party notices and identify any external source, pin, and license before copying code or distributing a combined environment.