# Getting started

Install Docker with Compose.
Python, uv, FFmpeg, and the project dependencies run inside the container.

## Inspect a file

```sh
git clone https://github.com/P4suta/asmr-balance.git
cd asmr-balance
docker compose up -d --build web
```

Open <http://127.0.0.1:8000> and drop an audio or video file into the page.
Review its channel balance, loudness, clipping risk, and playback suggestions.
Stop the interface with `docker compose stop web`.

## Scan a library

Copy `.env.example` to `.env` and set `ASMR_LIBRARY_PATH` to an existing directory.
Recreate the service with `docker compose up -d web`.
The directory appears at `/library` inside the container and is mounted read-only.
Select files through the library view to start a scan.

## Use the CLI

Mount a directory containing audio files at `/library`:

```sh
docker compose run --rm -v "$PWD/samples:/library:ro" app \
  uv run --frozen asmr-balance inspect /library/example.wav
```

Replace `example.wav` with a file in that directory.
Use `uv run --frozen asmr-balance --help` inside the app service for all commands and options.

See [verification](../ci.md) for development commands and [architecture decisions](../adr/index.md) for the analysis contracts.
