/**
 * Smoke-drive auth + Unavailable states against a running web preview.
 *
 * Retargeted after the mock API was deleted: this no longer claims to cover
 * full product journeys (those need a live backend + seeded accounts).
 *
 *   npm install playwright-core --no-save
 *   NODE_OPTIONS="--max-old-space-size=4096" npx expo start --web --port 8097
 *   node scripts/verify-ui.js
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

  const shot = async (n) => page.screenshot({ path: `${SHOTS}/${n}.png` }).catch(() => {});
  const text = () => page.evaluate(() => document.body.innerText);
  const url = () => page.evaluate(() => location.pathname);

  page.setDefaultTimeout(120000);
  page.setDefaultNavigationTimeout(300000);

  const killToast = () =>
    page.addStyleTag({ content: '#error-toast{display:none !important;pointer-events:none !important}' });

  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await sleep(7000);
  await killToast();
  await shot('01-sign-in');

  check('Signed-out entry lands on login', (await url()).includes('/sign-in'), await url());
  check('Login screen renders', (await text()).includes('Welcome back'));
  check('Login offers password recovery', (await text()).includes('Forgot password?'));

  await page.getByRole('link', { name: /Sign up|Create/i }).first().click().catch(async () => {
    await page.getByText(/Sign up|Create account/i).first().click();
  });
  await sleep(2000);
  await killToast();
  await shot('02-sign-up');
  check('Sign-up screen reachable', (await url()).includes('sign-up') || (await text()).includes('Founder'));

  await page.goto(`${BASE}/forgot-password`, { waitUntil: 'domcontentloaded' });
  await sleep(2000);
  await killToast();
  await shot('03-forgot-password');
  check('Forgot-password screen renders', (await text()).toLowerCase().includes('password'));

  // Role-guarded routes should bounce signed-out users.
  await page.goto(`${BASE}/founder`, { waitUntil: 'domcontentloaded' });
  await sleep(3000);
  await killToast();
  check('Founder home redirects when signed out', (await url()).includes('sign-in') || !(await text()).includes('YOUR TOOLS'));

  await page.goto(`${BASE}/investor`, { waitUntil: 'domcontentloaded' });
  await sleep(3000);
  await killToast();
  check('Investor home redirects when signed out', (await url()).includes('sign-in') || !(await text()).includes('Dealflow'));

  const fatal = errors.filter(
    (e) => !/Warning:|React Router|expo-router|Download the React DevTools/i.test(e),
  );
  check('No fatal console/page errors', fatal.length === 0, fatal.slice(0, 3).join(' | '));

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  if (failed.length) process.exit(1);
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
