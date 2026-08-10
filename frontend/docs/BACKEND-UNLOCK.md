# Backend unlock — do not fake liveness

Phase D of the UX roadmap. Screens for these features already exist and show
honest “not live” / `NOT BUILT YET` states. Light them up only when the named
backend work ships — never invent success on the client.

| Surface | Client route / API | Wait for |
| --- | --- | --- |
| Paywall / unlock | `/founder/paywall`, `purchaseUnlock` | T3.3 / T3.4 Stripe |
| Programmes enrol | `/founder/programmes`, `enrol` | T3.2 catalogue |
| AI mentor | `/founder/ai-mentor`, `chatMentor` / `askMentor` | T3.7 |
| Notifications | Alerts tabs, `listNotifications` | T5.3 |
| Introductions / calls | schedule sheet, `requestIntroduction` / `requestCall` | T4.5 (+ admin middle) |
| Investor Identity | `/investor/verify` | T4.1 Stripe Identity |
| Audits completing | results poll | Deploy `fundready-worker` |
| HTTPS email → app | deep links | F5.5 App Links + `APP_LINK_BASE_URL` |

Display name is **FundReady AI**. URL scheme `sacifundme://` and package
`com.sacifundme.app` stay until a coordinated migration.
