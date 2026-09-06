# Vendored uMCP

Source: https://github.com/rcarmo/umcp
Commit: 30cce7dfe08c6ee63de235f7d81754ba286dafbb
Version: 0.2.2
License: MIT (LICENSE included)

Files: aioumcp.py, umcp_shared.py.
Local patch: four `from umcp_shared import` statements changed to package-relative
imports. No protocol modifications. Package initializer added for Python imports.
Vibes overrides logging to avoid writes beside installed vendor files and uses
its bounded stdio reader around process_request_async. Network transports are
not exposed by the Vibes entry point.
