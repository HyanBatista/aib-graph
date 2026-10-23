# AIB Graph — desktop app

Electron + React + TypeScript client for the AIB Graph server (`../server`).

## Develop

```sh
npm install
npm run dev          # Electron with hot reload; the login screen has a "Demo accounts" picker
```

The server must be running (see `../server`), seeded with `uv run python manage.py seed_demo`.
Demo accounts all use the password `demo1234`.

## Checks

```sh
npm run typecheck
npm test             # vitest: websocket event reducer, API client (token refresh)
npm run e2e          # builds, then drives the real app with Playwright against a running seeded server
```

The second e2e test creates the "Hash Tables" node in the Live class; run `seed_demo --reset` to repeat it.

## Build installers

```sh
npm run dist         # electron-builder: .dmg (macOS), NSIS .exe (Windows), .AppImage (Linux) in dist/
```

## Environment

| Variable | Effect |
| --- | --- |
| `AIB_SERVER_URL` | Server URL (default `http://localhost:8000`; can also be changed on the login screen, which persists it) |
| `AIB_USER_DATA` | Alternative profile directory, e.g. to run two users side by side |
| `E2E_SCREENSHOT_DIR` | Where the e2e test writes screenshots (default `test-results/`) |

Tokens are stored encrypted with Electron `safeStorage` in the profile directory.
