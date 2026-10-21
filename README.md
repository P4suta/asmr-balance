# asmr-balance

Check ASMR audio balance, loudness, and playback issues before listening.
The web interface accepts audio and video files and suggests suitable playback settings.

## Quick start

Install Docker with Compose, then run:

```sh
git clone https://github.com/P4suta/asmr-balance.git
cd asmr-balance
docker compose up -d --build web
```

Open <http://127.0.0.1:8000> and drop a file into the page.

See the [getting started guide](docs/guide/getting-started.md) for library scanning and CLI usage.
The [documentation](docs/index.md) links to development checks and architecture decisions.

## License

[MIT](LICENSE).
