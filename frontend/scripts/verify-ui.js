/**
 * Drives every FundReady screen in a real browser.
 *
 * The web build is a client-rendered SPA, so HTTP 200 proves nothing and deep
 * links bounce off the entry gate — the only honest check is to click through.
 *
 *   npm install playwright-core --no-save
 *   node scripts/verify-ui.js          # dev server must be running on :8097
 */
const { chromium } = require('playwright-core');

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const BASE = 'http://localhost:8097';
const SHOTS = __dirname + '/../.ui-shots';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

(async () => {
  const browser = await chromium.launch({ executablePath: EDGE, headless: true });
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

  const errors = [];
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

  // expo-document-picker opens a real file input on web; answer it with a
  // stub certificate so the upload path is genuinely exercised.
  page.on('filechooser', async (chooser) => {
    await chooser
      .setFiles({
        name: 'certificate-of-incorporation.pdf',
        mimeType: 'application/pdf',
        buffer: Buffer.from('%PDF-1.4\n% stub certificate for UI verification\n'),
      })
      .catch(() => {});
  });

  const shot = async (n) => page.screenshot({ path: `${SHOTS}/${n}.png` });
  const text = () => page.evaluate(() => document.body.innerText);
  const url = () => page.evaluate(() => location.pathname);

  // Metro's first bundle of ~1800 modules takes minutes on a cold cache.
  page.setDefaultTimeout(120000);
  page.setDefaultNavigationTimeout(300000);

  // Expo's dev-only error toast is a fixed div that swallows clicks on the
  // sticky footers even when empty. Not part of the app.
  // Tab presses skip Playwright's stability wait: under Metro load the bar
  // can jitter for longer than the timeout even though it is perfectly usable.
  const clickTab = (name) => page.getByRole('tab', { name }).click({ force: true });

  const killToast = () =>
    page.addStyleTag({ content: '#error-toast{display:none !important;pointer-events:none !important}' });

  // ── 01 login is the entry point ───────────────────────────
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(7000);
  await killToast();
  await shot('01-sign-in');

  check('Signed-out entry lands on login', (await url()).includes('/sign-in'), await url());
  check('Login screen renders', (await text()).includes('Welcome back'));
  check('Login offers password recovery', (await text()).includes('Forgot password?'));

  // The company-domain rule is worthless if login is a way around it: a
  // founder account cannot exist on a consumer domain, so signing in with one
  // must never land on the founder side.
  await page.getByPlaceholder('you@company.com').fill('someone@gmail.com');
  await page.getByPlaceholder('••••••••••').fill('supersecret');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await sleep(5000);
  await killToast();
  check('Login with a personal email never reaches the founder side', !(await url()).includes('/founder'), await url());
  await shot('01b-personal-login');

  await clickTab('Profile');
  await sleep(2200);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await sleep(3200);
  await killToast();

  const lightAncestor = await page.evaluate(() => {
    let el = document.elementFromPoint(195, 300);
    while (el) {
      const bg = getComputedStyle(el).backgroundColor;
      if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
        const [r, g, b] = bg.match(/\d+/g).map(Number);
        if (r + g + b > 200) return `${el.tagName} ${bg}`;
      }
      el = el.parentElement;
    }
    return null;
  });
  check('No light ancestor behind the app', lightAncestor === null, lightAncestor ?? 'all dark');

  // ── 02 sign-up ────────────────────────────────────────────
  await page.getByText('New to FundReady? Create an account').click();
  await sleep(2500);
  await killToast();
  await shot('02-sign-up');

  const signUp = await text();
  check('Sign-up screen renders', signUp.includes('Get funded on evidence, not vibes.'));
  check('Subhead removed from sign-up', !signUp.includes('Answer 4 short steps'), 'no paragraph under the headline');

  check(
    'Social sign-in is gone',
    !/Continue with (Google|LinkedIn)/.test(signUp) && !/^OR$/m.test(signUp),
    'no Google/LinkedIn buttons, no OR divider',
  );

  await page.getByRole('button', { name: "I'm investing" }).click();
  await sleep(700);
  check('Headline adapts to the investor role', (await text()).includes('Back companies on evidence'));

  // Investors may legitimately use a personal address — angels do.
  await page.getByPlaceholder('you@fund.com').fill('angel@gmail.com');
  await page.getByText('Back companies on evidence, not vibes.').click();
  await sleep(1500);
  check('Investor personal email is allowed', !(await text()).includes('Use your company email'));

  await page.getByRole('button', { name: "I'm raising" }).click();
  await sleep(700);

  // ── 02b founder company-domain rule ───────────────────────
  check('Founder email field states the rule', (await text()).includes('not Gmail, Yahoo or similar'));

  await page.getByPlaceholder('you@yourcompany.com').fill('vic@gmail.com');
  await page.getByText('Get funded on evidence, not vibes.').click();
  await sleep(1500);
  await shot('02b-personal-email-rejected');
  check('Founder personal email is rejected on blur', (await text()).includes('Use your company email'));

  await page.getByPlaceholder('you@yourcompany.com').fill('vic@yahoo.co.uk');
  await page.getByText('Get funded on evidence, not vibes.').click();
  await sleep(1500);
  check('Regional consumer domains are rejected too', (await text()).includes('Use your company email'));

  // A company domain with SSO configured hands off instead of taking a password.
  await page.getByPlaceholder('you@yourcompany.com').fill('vic@acmecorp.com');
  await page.getByText('Get funded on evidence, not vibes.').click();
  await sleep(2500);
  await shot('02c-company-sso');
  const ssoState = await text();
  check('Company SSO is discovered from the domain', ssoState.includes('SINGLE SIGN-ON'));
  check('SSO replaces the password field', ssoState.includes('Continue with Okta') && !ssoState.includes('PASSWORD'));

  // ── 03 founder sign-up → onboarding ───────────────────────
  await page.getByPlaceholder('you@yourcompany.com').fill('vic@northwind.io');
  await page.getByText('Get funded on evidence, not vibes.').click();
  await sleep(1800);
  check('Company domain without SSO keeps the password form', (await text()).includes('PASSWORD'));
  await page.getByPlaceholder('••••••••••').fill('supersecret');
  await page.getByRole('button', { name: 'Create founder account' }).click();
  await sleep(3500);
  await killToast();
  check('Founder sign-up enters onboarding', (await text()).includes('Tell us who you are'), await url());

  await page.getByPlaceholder('Northwind Labs').fill('Northwind Labs');
  await page.getByRole('button', { name: 'Industry sector' }).click();
  await sleep(900);
  await page.getByRole('button', { name: 'Fintech', exact: true }).click();
  await sleep(700);
  await page.getByPlaceholder('Lagos, Nigeria').fill('Lagos, Nigeria');
  await page.getByPlaceholder('2023').fill('2023');
  await page.getByRole('button', { name: 'Continue' }).click();
  await sleep(1200);

  await page.getByRole('button', { name: 'Seed', exact: true }).click();
  await page.getByPlaceholder('48000').fill('48000');
  await page.getByPlaceholder('14').fill('14');
  await sleep(400);
  await page.getByRole('button', { name: 'Continue' }).click();
  await sleep(1200);

  await page.getByPlaceholder('12').fill('12');
  await page.getByPlaceholder('78').fill('78');
  await page.getByPlaceholder('320').fill('320');
  await page.getByPlaceholder('1450').fill('1450');
  await sleep(600);
  check('Live LTV:CAC ratio computes', (await text()).includes('4.5 : 1'));
  await page.getByRole('button', { name: 'Continue' }).click();
  await sleep(1200);

  await page.getByPlaceholder('2').fill('2');
  await page.getByRole('button', { name: 'Yes', exact: true }).click();
  await sleep(400);
  await page.getByRole('button', { name: 'Run AI assessment' }).click();
  await sleep(8000);
  await killToast();
  await shot('03-results');
  check('Assessment produces results', (await text()).includes('Assessment complete'));

  // ── 04 founder dashboard ──────────────────────────────────
  await page.getByRole('button', { name: /Go to your dashboard/ }).click();
  await sleep(3000);
  await killToast();
  await shot('04-founder-dashboard');

  const dash = await text();
  check('Founder dashboard renders', (await url()).includes('/founder'), await url());
  check('Dashboard shows the trial countdown', /TRIAL · \d+ DAYS? LEFT/.test(dash));
  check('Dashboard prompts company verification', dash.includes('Verify your company to be seen by investors'));
  check('Score card carries the assessment', dash.includes('Strong') || dash.includes('Promising'));
  check('Gated modules render as locked', dash.includes('AI mentor') && dash.includes('Verify to unlock'));

  await page.getByRole('button', { name: /AI mentor, locked/ }).click();
  await sleep(2500);
  await killToast();
  check('Locked module routes to verification', (await url()).includes('/founder/verify'), await url());
  await shot('05-verify-company');

  // ── 05 company verification ───────────────────────────────
  check('Verification asks for country registration', (await text()).includes('Prove your company is real'));

  await page.getByRole('button', { name: 'Country of registration' }).click();
  await sleep(900);
  await page.getByRole('button', { name: 'Nigeria', exact: true }).click();
  await sleep(900);
  const registrarValue = await page.evaluate(() => {
    const el = Array.from(document.querySelectorAll('input')).find((i) => i.placeholder === 'CAC');
    return el ? el.value : null;
  });
  check('Registrar prefills from country', registrarValue === 'CAC', registrarValue ?? 'field not found');

  await page.getByPlaceholder('Northwind Labs Limited').fill('Northwind Labs Limited');
  await page.getByPlaceholder('RC 1234567').fill('RC 1849302');
  await sleep(400);
  await page.getByRole('button', { name: 'Submit for verification' }).click();
  await sleep(1500);
  check('Verification requires the certificate', (await text()).includes('attach your certificate'));

  // Upload a certificate and submit for real.
  await page.getByRole('button', { name: /Upload certificate/ }).click();
  await sleep(1800);
  check('Certificate attaches', (await text()).includes('certificate-of-incorporation.pdf'));

  await page.getByRole('button', { name: 'Submit for verification' }).click();
  await sleep(3000);
  await killToast();
  await shot('05b-verification-submitted');
  check('Submitting moves verification into review', (await text()).includes('VERIFICATION IN REVIEW'));

  // The mock approves on a timer, so the waiting state is real. Leave and
  // return to force the dashboard's focus refresh.
  await sleep(7000);
  await clickTab('Profile');
  await sleep(1800);
  await clickTab('Home');
  await sleep(2500);
  await killToast();
  await shot('05c-verified');
  const verified = await text();
  check('Verification clears to verified', verified.includes("You're live in the investor dealflow"));
  check('Modules unlock once verified', !verified.includes('Verify to unlock'));

  // ── 05b AI mentor, now unlocked ───────────────────────────
  await page.getByRole('button', { name: 'AI mentor' }).click();
  await sleep(2800);
  await killToast();
  await shot('05d-ai-mentor');
  check('AI mentor opens once unlocked', (await url()).includes('/founder/ai-mentor'), await url());

  await page.getByText('Are my unit economics good enough?').click();
  await sleep(3000);
  await shot('05e-ai-mentor-answer');
  // The mock answers from the founder's own numbers — 1450/320 = 4.5:1.
  check('Mentor answers from the founder’s real metrics', (await text()).includes('4.5:1'));

  await page.getByRole('button', { name: 'Back' }).click();
  await sleep(2500);
  await killToast();

  // ── 06 paywall ────────────────────────────────────────────
  await page.getByRole('button', { name: /^Trial/ }).first().click();
  await sleep(2800);
  await killToast();
  await shot('06-paywall');
  const paywall = await text();
  check('Paywall shows the one-off price', paywall.includes('$149') && paywall.includes('once'));
  check('Paywall lists what unlocking gives', paywall.includes('Listed in the investor dealflow database'));

  await page.getByRole('button', { name: /Pay \$149 once/ }).click();
  await sleep(3500);
  await shot('07-paid');
  check('Payment confirms with a receipt', (await text()).includes('PAYMENT RECEIVED'));

  await page.getByRole('button', { name: 'Back to dashboard' }).click();
  await sleep(2800);
  await killToast();

  // ── 07 founder alerts + role separation ───────────────────
  await clickTab(/Alerts/);
  await sleep(2800);
  await killToast();
  await shot('08-founder-alerts');
  check('Founder alerts show the payment receipt', (await text()).includes('Payment received'));

  // ── 08 investor side ──────────────────────────────────────
  // NB: no page.goto until the very end — a reload restarts the SPA and wipes
  // the mock backend's module state, which would undo verification and the
  // call request. Direct-URL guard checks are therefore run last.
  await clickTab('Profile');
  await sleep(2200);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await sleep(3200);
  await killToast();
  check('Sign out returns to login', (await url()).includes('/sign-in'), await url());

  await page.getByText('New to FundReady? Create an account').click();
  await sleep(2200);
  await page.getByRole('button', { name: "I'm investing" }).click();
  await sleep(600);
  await page.getByPlaceholder('you@fund.com').fill('partner@northwindcapital.com');
  await page.getByPlaceholder('••••••••••').fill('supersecret');
  await page.getByRole('button', { name: 'Create investor account' }).click();
  await sleep(4500);
  await killToast();
  await shot('10-dealflow');
  check('Investor sign-up lands on dealflow', (await url()).includes('/investor'), await url());
  check('Dealflow lists companies', (await text()).includes('Halcyon Labs'));

  // ── 09 deep dive gated on investor verification ───────────
  await page.getByText('Halcyon Labs').first().click();
  await sleep(3000);
  await killToast();
  await shot('11-deep-dive');
  check('Deep dive opens', (await text()).includes('DEEP DIVE'));
  check('Unverified investor is prompted to verify', (await text()).includes('VERIFY TO CONTACT'));

  await page.getByRole('button', { name: 'Schedule' }).click();
  await sleep(2800);
  await killToast();
  check('Scheduling routes an unverified investor to verification', (await url()).includes('/investor/verify'), await url());

  // ── 10 investor verification ──────────────────────────────
  await page.getByRole('button', { name: 'Investor type' }).click();
  await sleep(900);
  await page.getByRole('button', { name: 'Venture capital', exact: true }).click();
  await sleep(800);
  await page.getByPlaceholder('Northwind Capital').fill('Northwind Capital');
  await page.getByRole('button', { name: 'Country' }).click();
  await sleep(900);
  await page.getByRole('button', { name: 'Nigeria', exact: true }).click();
  await sleep(800);
  await page.getByPlaceholder('linkedin.com/in/yourname').fill('linkedin.com/in/vic');
  await sleep(400);
  await shot('12-verify-investor');
  await page.getByRole('button', { name: 'Verify profile' }).click();
  await sleep(3500);
  await killToast();

  // ── 11 schedule a call ────────────────────────────────────
  check('Verification banner clears', !(await text()).includes('VERIFY TO CONTACT'));
  await page.getByRole('button', { name: 'Schedule' }).click();
  await sleep(2200);
  await killToast();
  await shot('13-schedule-call');
  const sheet = await text();
  check('Schedule sheet opens', sheet.includes('YOU ARE PROPOSING'));
  check('Schedule sheet offers slots and lengths', sheet.includes('11:00') && sheet.includes('30 min'));

  await page
    .getByPlaceholder('What you want to cover on the call…')
    .fill('Walk me through your inference caching benchmarks.');
  await sleep(400);
  await page.getByRole('button', { name: 'Send request' }).click();
  await sleep(3200);
  await killToast();
  await shot('14-call-sent');
  check('Call request is sent', (await text()).includes('Call request sent'));

  // ── 12 founder receives, accepts, investor is notified ────
  await page.getByRole('button', { name: 'Back' }).click();
  await sleep(3500);
  await killToast();
  await shot('14b-after-back');
  check('Back from the deep dive returns to the tabs', (await page.getByRole('tab').count()) === 4, `${await page.getByRole('tab').count()} tabs, url ${await url()}`);
  await clickTab('Profile');
  await sleep(2200);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await sleep(3200);
  await killToast();

  await page.getByPlaceholder('you@company.com').fill('vic@northwind.io');
  await page.getByPlaceholder('••••••••••').fill('supersecret');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await sleep(5000);
  await killToast();
  await shot('15-founder-home');
  check('Founder home reached by login', (await url()).includes('/founder'), await url());

  await clickTab(/Investors/);
  await sleep(3000);
  await killToast();
  await shot('16-call-request');
  const requests = await text();
  check('Founder sees the call request', requests.includes('Northwind Capital') && requests.includes('PROPOSED SLOT'));
  check('Call request carries the note', requests.includes('inference caching benchmarks'));

  await page.getByRole('button', { name: 'Accept call' }).click();
  await sleep(2800);
  await killToast();
  await shot('17-call-accepted');
  check('Accepting moves the request to answered', (await text()).includes('ACCEPTED'));

  // ── 13 investor sees the acceptance ───────────────────────
  await clickTab('Profile');
  await sleep(2200);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await sleep(3200);
  await killToast();
  await page.getByPlaceholder('you@company.com').fill('partner@northwindcapital.com');
  await page.getByPlaceholder('••••••••••').fill('supersecret');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await sleep(5000);
  await killToast();

  await clickTab(/Alerts/);
  await sleep(3000);
  await killToast();
  await shot('18-investor-notified');
  check('Investor is notified the call was accepted', (await text()).includes('accepted your call'));

  // ── 14 role separation by direct URL ──────────────────────
  // These reload the app (resetting the mock), so they run last. The session
  // itself survives in storage, which is all the guard needs.
  await page.goto(`${BASE}/founder`, { waitUntil: 'domcontentloaded' });
  await sleep(7000);
  await killToast();
  check('Investor is bounced off /founder', (await url()).includes('/investor'), await url());
  await shot('19-role-guard-investor');

  await clickTab('Profile');
  await sleep(2200);
  await page.getByRole('button', { name: 'Sign out' }).click();
  await sleep(3200);
  await killToast();
  await page.getByPlaceholder('you@company.com').fill('vic@northwind.io');
  await page.getByPlaceholder('••••••••••').fill('supersecret');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await sleep(5000);
  await killToast();

  await page.goto(`${BASE}/investor`, { waitUntil: 'domcontentloaded' });
  await sleep(7000);
  await killToast();
  check('Founder is bounced off /investor', (await url()).includes('/founder'), await url());
  await shot('20-role-guard-founder');

  // ── console hygiene ───────────────────────────────────────
  const realErrors = errors.filter(
    (e) =>
      !/favicon|Download the React DevTools|source map|\[Violation\]/i.test(e) &&
      // react-native-web forwards its own internal prop to the DOM node.
      !/collapsable/i.test(e),
  );
  check('No console errors', realErrors.length === 0, realErrors.slice(0, 3).join(' | '));

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  if (failed.length) {
    console.log('FAILURES:\n' + failed.map((f) => ` - ${f.name} ${f.detail}`).join('\n'));
    process.exit(1);
  }
})().catch((e) => {
  console.error('HARNESS ERROR:', e.message);
  process.exit(2);
});
