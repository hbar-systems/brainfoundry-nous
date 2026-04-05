# Contributing

Thank you for your interest in brainfoundry-nous.

## Reporting bugs

Open an issue on GitHub. Include your stack version (`docker compose exec api python -c "import api.main; print(api.main.BRAIN_VERSION)"`), your deployment environment (cloud/local), and a description of the problem.

## Submitting changes

1. Fork the repository and create a branch from `main`.
2. Make your changes. Keep PRs focused — one logical change per PR.
3. Do not commit `.env` files, secrets, or personal data.
4. Open a pull request with a clear description of what you changed and why.

## Protocol changes

The BrainFoundry node contract (`docs/brainfoundry/NODE_CONTRACT.md`) and the CognitiveOS governance model are versioned. Changes that break the wire protocol or command API require a version bump and a migration note.

## License

By submitting a contribution you agree that your changes will be licensed under the project's [AGPL-3.0 license](LICENSE).
