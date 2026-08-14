# FundReady AI — web

Next.js App Router client for the FundReady FastAPI backend. Founder, investor, and SACI admin shells. The Expo app in `frontend/` is unchanged.

## Run

```bash
# API (from backend/)
uvicorn app.main:app --reload

# Web (from web/)
cp .env.example .env.local   # API_URL=http://localhost:8000
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The app calls same-origin `/v1/*`; Next rewrites those to the API, so the browser does not need CORS.

Stripe Checkout should return to:

- success: `http://localhost:3000/founder/billing?checkout=success`
- cancel: `http://localhost:3000/founder/billing?checkout=cancel`

Set those on `STRIPE_CHECKOUT_SUCCESS_URL` / `STRIPE_CHECKOUT_CANCEL_URL`.

## Deploy (Vercel)

Set the Vercel **Root Directory** to `web`. Production already points at the Render API (`https://fundready-ai.onrender.com`) via `.env.production`. Override with `API_URL` on Vercel only if that host changes.

After the first production URL exists, set these on the Render API:

- `STRIPE_CHECKOUT_SUCCESS_URL` = `https://<your-web-host>/founder/billing?checkout=success`
- `STRIPE_CHECKOUT_CANCEL_URL` = `https://<your-web-host>/founder/billing?checkout=cancel`
- `APP_LINK_BASE_URL` = `https://<your-web-host>` (email links)

You do **not** need `CORS_ALLOWED_ORIGINS` for this app — the browser never talks to Render directly.

## Auth

Login goes through `app/api/auth/*` (BFF). The rotating refresh token is an httpOnly cookie; the 15-minute access token stays in memory and is sent as `Authorization: Bearer` to `/v1`.

Admins cannot self-register. First admin: `backend/scripts/create_admin.py`, then enrol MFA at `/admin/mfa-setup`.
