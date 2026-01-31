# Vibes

![Vibes](docs/icon-256.png)

A single-user, mobile-friendly SPA for Slack-like interactions with coding agents via the ACP protocol.

![Screenshot](docs/screenshot.png)

## Features

- Post text, links, images, and files
- Threaded conversations with ACP agents
- Rich media previews (downscaled and stored in database)
- Live updates via Server-Sent Events (SSE)
- Responsive design for mobile, tablet, and desktop
- Dark/light mode toggle

## Installation

```bash
# Install directly from GitHub
pip install git+https://github.com/rcarmo/vibes.git

# Install a specific tag
pip install "vibes @ git+https://github.com/rcarmo/vibes.git@v0.1.0"
```

Or for development:

```bash
git clone https://github.com/rcarmo/vibes.git
cd vibes
pip install -e ".[dev]"
```

## Usage

```bash
# Run the server
vibes

# Or with custom options
VIBES_HOST=127.0.0.1 VIBES_PORT=3000 vibes
```

## Configuration

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## API Endpoints

See [docs/API.md](docs/API.md).

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run frontend linting (requires bun)
make lint-frontend

# Run with make
make serve
```

## License

MIT
