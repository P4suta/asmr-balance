# Verification

Install Docker with Compose and the tools pinned in `mise.toml`.
All Python commands run inside the project container.

```sh
mise install just lefthook actionlint typos gitleaks ubi:crate-ci/committed ripgrep
mise x -- just docker-build ci
```

`ci` runs workflow lint, spelling, secret scanning, Python formatting and lint, type checks, security and unused-code checks, the defensive gates, coverage, and dependency auditing.
Coverage runs the complete suite once with two workers and fixed Hypothesis and test-order seeds.
It includes the property, reference, regression, and end-to-end tests and retains the branch coverage requirement.

## Change selection

Every pull request and merge queue change runs `lint-text`.
App source, tests, dependency manifests, container inputs, and verification configuration also select `verify-app`.
The [path filter](https://github.com/P4suta/asmr-balance/blob/main/.github/filters/ci.yml) and [local hooks](https://github.com/P4suta/asmr-balance/blob/main/lefthook.yml) select the same app inputs.
The required check rejects invalid selection values and any selected check that fails or is skipped.

Documentation changes do not build the app or run its tests.
Run `mise x -- just docs` when changing documentation navigation or generated API pages.

## Explicit checks

Use `prop` for the larger property profile, `mutate` for mutation testing, and `bench` for timing observations.
These commands run only when requested.
The focused `regression` and `e2e` commands remain available for development.

The manually dispatched distribution workflow runs the ordinary checks, builds a wheel and source archive, and retains the files and dependency inventory for seven days.
It does not create commits, tags, GitHub Releases, or registry uploads.
Publication remains a separate operation.
