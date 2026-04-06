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

## Contributor License Agreement (CLA)

Before your first pull request can be merged, you must sign the project's
Contributor License Agreement. The CLA grants the project maintainer the
right to relicense your contribution (e.g. under a commercial license)
while you retain copyright over your own code.

This is standard practice for AGPL projects that may offer dual licensing
in the future. It does not restrict your right to use your own code however
you wish.

The CLA is at [CLA.md](CLA.md). Sign by adding your name and date to the
file in your first PR, or by commenting "I have read and agree to the CLA"
on your pull request.

## License

By submitting a contribution you agree that your changes will be licensed
under the project's [AGPL-3.0 license](LICENSE) and that you have signed
the Contributor License Agreement.
