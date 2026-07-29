# SACI FundMe — mobile frontend

Expo SDK 57 / React Native 0.86 / expo-router / NativeWind 4. Two sides of one
marketplace, kept strictly apart: **founder** (dashboard, assessment, company
verification, paywall, AI mentor) and **investor** (dealflow, deep dive,
watchlist, scheduling). Backend is owned by a partner; this repo talks to it
through one seam only.

Expo has changed a lot — read the versioned docs at
https://docs.expo.dev/versions/v57.0.0/ before writing new integration code.

## Where things live

- `src/app/` — routes.
  - `sign-in` (login), `sign-up`, `forgot-password` are the signed-out screens.
  - `(onboarding)/` — the 4-step assessment, full-screen, founders only.
  - `founder/` and `investor/` are **real path segments, not groups**, so the
    two sides can never collide on a route name and the guard has something to
    bounce to. Each has a `(tabs)` group inside it plus full-screen pushes
    (`founder/verify`, `founder/paywall`, `investor/company/[id]`).
- `src/api/` — **the only seam to the backend.** `contract.ts` is the interface,
  `mock.ts` implements it from local seed data, `index.ts` picks one. To go
  live, add `http.ts` implementing `FundMeApi` and flip the export in
  `index.ts` — no screen changes.
- `src/domain/` — types, the 24-company seed dataset, the Fundability scoring
  model (ported verbatim from the design prototype), `access.ts` (trial /
  payment / verification gates) and `pricing.ts` (the one-off unlock price).
- `src/store/` — Zustand: `session` (auth, role, account state),
  `founder` (onboarding form + assessment), `investor` (filters + watchlist),
  `notifications` (alerts + call requests).
- `src/components/ui/` — primitives. `src/theme/tokens.ts` mirrors
  `tailwind.config.js` for the values Tailwind cannot reach (SVG strokes,
  gradients, data-driven colours).

## Sign-up identity rules

There is **no consumer social login** — Google and LinkedIn were removed
deliberately, so do not reintroduce them.

- **Founders must sign up on a company domain.** `src/domain/email.ts` rejects
  consumer mailbox providers and disposable services. It works by blocklist,
  not by trying to prove a domain is corporate: a false reject turns a real
  founder away, which costs far more than letting an unusual domain through,
  and the company is verified properly later anyway.
- **Investors are exempt from that rule** — angels legitimately operate from
  personal addresses. Only the address shape is checked.
- The rule is enforced in **both** the client (instant feedback, no round trip)
  and `signUp` in the API layer. The client check is a convenience; the server
  is the control.
- **Login is part of the same rule.** Blocking sign-up is pointless if signing
  in on a consumer domain lands you on the founder side — a founder account
  cannot exist on such a domain, so `roleForSignIn` in the mock resolves any
  personal address to the investor side. The real backend gets this for free by
  reading the role off the stored account; keep the invariant if you replace
  the mock.
- **Corporate SSO is home-realm discovery, not social login.** On blur, the
  founder's domain goes to `lookupEmailDomain`; if the company runs an identity
  provider, the password field is replaced by a hand-off button. The mock wires
  exactly one domain (`acmecorp.com` → Okta) so the path is demonstrable. A
  real implementation needs the backend to hold the per-domain IdP config and
  do the OIDC/SAML exchange.

## Access model

Two independent gates sit in front of the founder product, both resolved by
`gate(account, capability)` in `src/domain/access.ts`:

- **payment** — 14 days of full access from signup, then a one-off unlock
  payment. Checked first: an expired trial locks everything, so telling
  someone to verify would be the wrong instruction.
- **verification** — the company must be shown to be registered in its own
  country before it can appear in dealflow or use the AI mentor. Applies during
  the trial too.

Investors have one light gate: verified before they can request an introduction
or schedule a call. Locked features are always **shown and explained**, never
hidden, and route to whatever would unlock them.

## Traps that do not fail the build

Every one of these compiles, typechecks and serves HTTP 200 while being wrong.
Check rendered output in a browser, not just a green build.

1. **`src/global.css` must stay imported from `src/app/_layout.tsx`.** It is
   what puts the Tailwind output in the bundle. If the last module importing it
   becomes unreachable, every `className` in the app silently becomes a dead
   string.
2. **Non-core components drop `className`.** NativeWind only teaches core RN
   components. Reanimated's `Animated.*` and `LinearGradient` are registered in
   `src/lib/css-interop.ts`; add any new third-party view there or its classes
   vanish (a `flex-row` will lay out as a column).
3. **Never put two colour utilities on one element.** Tailwind resolves
   conflicts by stylesheet order, not class-string order, so a baked-in
   `text-ink` beats a caller's `text-ground` and paints white-on-white. The
   `Txt*` components in `components/ui/text.tsx` drop their default when the
   caller supplies a colour — keep that behaviour.
4. **Weight comes from the font family, not `fontWeight`.** Geist ships one file
   per weight. `font-semibold` does nothing; use `font-sans` / `font-med` /
   `font-semi` / `font-mono*` (see `tailwind.config.js`).
5. **No nested `Pressable`.** Both render as `<button>` on web; a nested button
   is invalid HTML that React refuses to hydrate. See `company-card.tsx` for the
   sibling-with-absolute-position pattern.
6. **React Navigation paints its own theme background.** The dark theme in
   `src/app/_layout.tsx` is load-bearing; without it `#f2f2f2` flashes through
   on navigation.
7. **The React Compiler is on (`app.json` → `experiments.reactCompiler`), so a
   store method that reads state internally gets memoised and never
   recomputes.** A `can(capability)` helper on the session store looked pure to
   the compiler, so gated tiles stayed locked after verification cleared even
   though the banner beside them had updated. Derive entitlements with the pure
   `gate(account, capability)` and pass `account` in, so the dependency is
   visible. Applies to any store getter that closes over `get()`.

## Running it

This machine cannot run the Android emulator (see the notes in the session
memory) — preview on the web or a physical phone via Expo Go.

```bash
# web preview; the larger heap is required, Metro OOMs at the default
NODE_OPTIONS="--max-old-space-size=4096" npx expo start --web --port 8097
npx tsc --noEmit
```

Port 8081 is often taken by another project's Metro; pass `--port`.

## Verifying UI changes

HTTP 200 proves nothing — the web build is a client-rendered SPA where every
route returns identical HTML, and deep links bounce off the entry gate. Drive
the real UI instead:

```bash
npm install playwright-core --no-save   # uses installed Edge, no browser download
node scripts/verify-ui.js               # dev server must be running on :8097
```

It drives both sides end to end — sign-up, assessment, verification (including
a real file upload through `expo-document-picker`), the paywall, the role
guards, and the full investor-requests-a-call → founder-accepts →
investor-is-notified loop — asserting on computed styles and rendered text and
dropping screenshots in `.ui-shots/`. It catches exactly the traps above, which
a green build does not.

Two things to know when editing it:

- **`page.goto` restarts the SPA and wipes the mock backend's module state.**
  Anything that depends on earlier state (verification, call requests) must
  happen before the first reload; the direct-URL guard checks run last for
  this reason.
- **Assertions on `document.body.innerText` are not scoped to the visible
  screen** — inactive tab screens stay mounted, so text from another tab is
  still in the DOM. Assert on something the target screen alone renders.
