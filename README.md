# kiosk-lite
A lightweight, configuration-driven web kiosk for Linux. Display multiple web pages with custom layouts, automatic refresh, and no desktop environment required.

Phase 1 signed off the graphics path on Raspberry Pi OS Lite. The example layout is [config/kiosk.example.yaml](config/kiosk.example.yaml). Each machine keeps its own URLs in `~/.config/kiosk-lite/kiosk.yaml`. Setup and the pass/fail check are in [poc/README.md](poc/README.md). Design choices are in [docs/architecture.md](docs/architecture.md).
