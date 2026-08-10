# FundReady AI — mobile frontend

Expo SDK 57 / React Native 0.86 / expo-router / NativeWind 4. Two sides of one
marketplace, kept strictly apart: **founder** (dashboard, assessment, company
verification, paywall, AI mentor) and **investor** (dealflow, deep dive,
watchlist, scheduling).

The backend lives in [`../backend`](../backend) and this app talks to it through
one seam only — `src/api/`. **Read [`AGENTS.md`](AGENTS.md) before changing
anything**: it documents the traps that compile, typecheck and serve HTTP 200
while rendering wrong.

## Running it

```bash
npm install

# Web preview. The larger heap is required — Metro OOMs at the default.
NODE_OPTIONS="--max-old-space-size=4096" npx expo start --web --port 8097
```

Port 8081 is often taken by another project's Metro, hence `--port`. For a
physical phone, use Expo Go from the same command.

### Pointing it at the API

Copy `.env.example` to `.env`. `EXPO_PUBLIC_API_URL` is the only setting, and it
is optional: with it unset the app takes the host that served the bundle and
substitutes port 8000, so a phone follows your machine around the network
without a rebuild.

> `EXPO_PUBLIC_*` values are inlined into the bundle at build time and are
> readable by anyone who has the app. Never put a secret in one.

Run the backend alongside it:

```bash
cd ../backend && uvicorn app.main:app --reload --host 0.0.0.0
```

`--host 0.0.0.0` matters for a phone, and the device's origin has to be in the
backend's `CORS_ALLOWED_ORIGINS`.

## Checks

```bash
npm run lint       # eslint
npm run typecheck  # tsc --noEmit
npm test           # jest
```

CI runs all three on every push. A green run does **not** mean the UI renders
correctly — there are no component rendering tests, deliberately (see
`jest.config.js`). For that, drive the real browser:

```bash
npm install playwright-core --no-save
node scripts/verify-ui.js   # needs the dev server on :8097
```

That harness is currently stale — it was written against a mock that has since
been deleted. Repairing it is task F0.5 in [`TASKS.md`](TASKS.md).

## What is built

[`TASKS.md`](TASKS.md) is the queue, phased to line up with
`../backend/TASKS.md`. Authentication, email verification, password reset, MFA
and the Startup Profile are live against the real API. Everything else rejects
with `not_implemented` and renders as an explicit **NOT BUILT YET** panel rather
than showing invented data.
