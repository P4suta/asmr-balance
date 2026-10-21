---
date: 2026-10-21
---

# Manual distribution verification

## Status

Proposed.
Partly supersedes [release automation](0010-release-automation.md).

## Context

An ordinary main merge must complete without publishing a new version.
Distribution verification needs the same dependency environment and behavioral checks as development, with an identifiable source revision.

## Decision

The [distribution workflow](https://github.com/P4suta/asmr-balance/blob/main/.github/workflows/release.yml) runs only on explicit dispatch from the default branch.
It uses read-only repository access, runs the project checks, and uploads unpublished distributions associated with the workflow's source SHA.
Artifacts expire after seven days.
The workflow has no version-writing, signing, tag creation, GitHub Release, or registry publication step.

Automatic publication on a main push couples maintenance merges to an independently sensitive operation.
A manual trigger on the former publisher would still mix verification and publication in one credential-bearing job.
Both alternatives are rejected.

## Consequences

Maintenance merges no longer publish versions.
Distribution checks remain available without publication credentials.
A future publisher needs a separate design that binds the verified bytes and version to explicit production approval.
