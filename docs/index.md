# asmr-balance

Check ASMR audio balance, loudness, and playback issues before listening.
Use the web interface to inspect a file or browse a mounted library.

- [Getting started](guide/getting-started.md)
- [Development and verification](ci.md)
- [Architecture decisions](adr/index.md)

The analysis separates streaming signal processing, typed metrics, rules, and listener-facing diagnostics.
The architecture records describe the measurement semantics, reference comparisons, and web boundaries.

Run `mise x -- just docs` to generate the API reference and documentation site.
