/**
 * The transport in `api/http.ts`.
 *
 * This is the file worth testing hardest: it holds the token pair, decides
 * when to refresh, and translates the server's error envelope into the codes
 * every screen branches on. The single-flight refresh in particular is a
 * *security* property — the server treats a replayed refresh token as theft and
 * revokes the whole family — and it is invisible to the type checker.
 *
 * The module keeps its token state at module scope, so every test re-imports it
 * through a reset registry rather than sharing one instance.
 */

import type { FundReadyApi } from '@/api/contract';
import { EMPTY_PROFILE as EMPTY_FORM } from '@/domain/types';

type Json = Record<string, unknown>;

/** Minimal `Response`: only the members `request()` actually touches. */
function res(status: number, body?: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => {
      if (body === undefined) throw new Error('no body');
      return body;
    },
  } as unknown as Response;
}

const TOKENS = { access_token: 'access-1', refresh_token: 'refresh-1', expires_in: 900 };
const TOKENS_2 = { access_token: 'access-2', refresh_token: 'refresh-2', expires_in: 900 };

const ME = {
  id: 'user-1',
  email: 'ada@northwind-labs.com',
  first_name: 'Ada',
  last_name: 'Nwosu',
  role: 'founder',
  status: 'active',
  email_verified: true,
  kyc_status: 'none',
  subscription_status: 'none',
  created_at: '2026-07-01T00:00:00Z',
};

type Call = { url: string; method: string; body: Json | null; auth: string | null };

describe('api/http transport', () => {
  let httpApi: FundReadyApi;
  let MfaRequired: typeof import('@/api/http').MfaRequired;
  let ApiFailure: typeof import('@/api/contract').ApiFailure;
  let calls: Call[];
  let fetchMock: jest.Mock;

  /** Records every request, then defers to the handler under test. */
  function serve(handler: (call: Call) => Response) {
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      const headers = (init.headers ?? {}) as Record<string, string>;
      const call: Call = {
        url,
        method: init.method ?? 'GET',
        body: init.body ? (JSON.parse(init.body as string) as Json) : null,
        auth: headers.Authorization ?? null,
      };
      calls.push(call);
      return handler(call);
    });
  }

  /** The happy path everything else builds on: log in and hold a token pair. */
  async function signedIn() {
    serve((call) => {
      if (call.url.endsWith('/v1/auth/login')) {
        return res(200, { status: 'authenticated', tokens: TOKENS, mfa_token: null });
      }
      if (call.url.endsWith('/v1/users/me')) return res(200, ME);
      throw new Error(`unexpected call: ${call.url}`);
    });
    await httpApi.signIn({ email: 'ada@northwind-labs.com', password: 'correct-horse-battery' });
    calls.length = 0;
  }

  beforeEach(() => {
    jest.resetModules();
    calls = [];
    fetchMock = jest.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const http = require('@/api/http') as typeof import('@/api/http');
    const contract = require('@/api/contract') as typeof import('@/api/contract');
    httpApi = http.httpApi;
    MfaRequired = http.MfaRequired;
    ApiFailure = contract.ApiFailure;
  });

  describe('error envelope', () => {
    it('maps each status onto the code screens branch on', async () => {
      const cases: [number, string][] = [
        [401, 'unauthorized'],
        [403, 'forbidden'],
        [404, 'not_found'],
        [409, 'conflict'],
        [422, 'validation'],
        [429, 'rate_limited'],
        [500, 'server'],
      ];

      for (const [status, code] of cases) {
        serve(() => res(status, { error: { code: 'server_code', message: 'nope' } }));
        await expect(httpApi.requestPasswordReset('ada@northwind-labs.com')).rejects.toMatchObject({
          code,
          message: 'nope',
          serverCode: 'server_code',
        });
      }
    });

    it('falls back to a readable message when the body is not an envelope', async () => {
      serve(() => res(500));
      await expect(httpApi.requestPasswordReset('ada@x.com')).rejects.toThrow('The server returned 500.');
    });

    it('reports an unreachable server as network, not as an HTTP error', async () => {
      fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
      const error = await httpApi.requestPasswordReset('ada@x.com').catch((e: unknown) => e);
      expect(error).toBeInstanceOf(ApiFailure);
      expect((error as InstanceType<typeof ApiFailure>).code).toBe('network');
      // The base URL belongs in the message: on a phone, the usual cause is
      // that it is pointing at the wrong host.
      expect((error as Error).message).toContain('http://api.test');
    });
  });

  describe('sign-in', () => {
    it('stores the pair and resolves who it belongs to', async () => {
      await signedIn();
      serve(() => res(200, ME));
      const account = await httpApi.getFounderAccount();

      expect(account.emailVerified).toBe(true);
      expect(calls[0].auth).toBe('Bearer access-1');
    });

    it('raises MfaRequired instead of returning a session when a code is outstanding', async () => {
      serve(() => res(200, { status: 'mfa_required', tokens: null, mfa_token: 'challenge-1' }));

      const error = await httpApi
        .signIn({ email: 'ada@northwind-labs.com', password: 'pw' })
        .catch((e: unknown) => e);

      expect(error).toBeInstanceOf(MfaRequired);
      expect((error as InstanceType<typeof MfaRequired>).mfaToken).toBe('challenge-1');
      // No token pair was issued, so nothing may have been stored.
      expect(calls.some((c) => c.url.endsWith('/v1/users/me'))).toBe(false);
    });

    it('refuses an admin and does not leave the device holding tokens', async () => {
      serve((call) => {
        if (call.url.endsWith('/v1/auth/login')) {
          return res(200, { status: 'authenticated', tokens: TOKENS, mfa_token: null });
        }
        return res(200, { ...ME, role: 'admin' });
      });

      await expect(httpApi.signIn({ email: 'root@fundready.com', password: 'pw' })).rejects.toMatchObject({
        code: 'forbidden',
      });

      // The pair issued mid-flow must have been cleared: an authed call now
      // fails before it reaches the network.
      calls.length = 0;
      await expect(httpApi.getFounderAccount()).rejects.toMatchObject({ code: 'unauthorized' });
      expect(calls).toHaveLength(0);
    });
  });

  describe('registration', () => {
    it('sends the names the server requires', async () => {
      serve((call) => {
        if (call.url.endsWith('/v1/auth/register')) return res(202, { status: 'pending_verification' });
        if (call.url.endsWith('/v1/auth/login')) {
          return res(200, { status: 'authenticated', tokens: TOKENS, mfa_token: null });
        }
        return res(200, ME);
      });

      await httpApi.signUp({
        email: 'Ada@Northwind-Labs.com ',
        password: 'correct-horse-battery',
        role: 'founder',
        firstName: ' Ada ',
        lastName: ' Nwosu ',
      });

      // Regression: omitting these 422'd every mobile registration for a day.
      expect(calls[0].body).toEqual({
        email: 'ada@northwind-labs.com',
        password: 'correct-horse-battery',
        role: 'founder',
        first_name: 'Ada',
        last_name: 'Nwosu',
      });
    });

    it('refuses a founder on a consumer mailbox without calling the server', async () => {
      serve(() => res(202, {}));
      await expect(
        httpApi.signUp({
          email: 'ada@gmail.com',
          password: 'correct-horse-battery',
          role: 'founder',
          firstName: 'Ada',
          lastName: 'Nwosu',
        }),
      ).rejects.toMatchObject({ code: 'validation', message: 'personal_email_domain' });
      expect(calls).toHaveLength(0);
    });

    it('lets an investor register from a personal address', async () => {
      serve((call) => {
        if (call.url.endsWith('/v1/auth/register')) return res(202, {});
        if (call.url.endsWith('/v1/auth/login')) {
          return res(200, { status: 'authenticated', tokens: TOKENS, mfa_token: null });
        }
        return res(200, { ...ME, role: 'investor' });
      });

      const session = await httpApi.signUp({
        email: 'angel@gmail.com',
        password: 'correct-horse-battery',
        role: 'investor',
        firstName: 'Kemi',
        lastName: 'Ade',
      });
      expect(session.role).toBe('investor');
    });

    it('reads the login failure after a 202 as "already registered"', async () => {
      serve((call) => {
        if (call.url.endsWith('/v1/auth/register')) return res(202, {});
        return res(401, { error: { message: 'bad credentials' } });
      });

      await expect(
        httpApi.signUp({
          email: 'ada@northwind-labs.com',
          password: 'wrong-password-here',
          role: 'founder',
          firstName: 'Ada',
          lastName: 'Nwosu',
        }),
      ).rejects.toMatchObject({ code: 'conflict' });
    });
  });

  describe('refresh', () => {
    it('refreshes once on a 401 and retries the original call', async () => {
      await signedIn();

      let meCalls = 0;
      serve((call) => {
        if (call.url.endsWith('/v1/auth/refresh')) return res(200, TOKENS_2);
        meCalls += 1;
        return meCalls === 1 ? res(401, {}) : res(200, ME);
      });

      await expect(httpApi.getFounderAccount()).resolves.toBeDefined();

      const refreshes = calls.filter((c) => c.url.endsWith('/v1/auth/refresh'));
      expect(refreshes).toHaveLength(1);
      expect(refreshes[0].body).toEqual({ refresh_token: 'refresh-1' });
      // The retry must carry the *new* access token, not the stale one.
      expect(calls.at(-1)?.auth).toBe('Bearer access-2');
    });

    it('exchanges the refresh token exactly once when two calls 401 together', async () => {
      await signedIn();

      // Both in-flight requests 401 before either refresh completes. Two
      // exchanges would present the same rotated token twice, which the server
      // reads as theft and answers by revoking the entire session family.
      let refreshed = false;
      serve((call) => {
        if (call.url.endsWith('/v1/auth/refresh')) {
          refreshed = true;
          return res(200, TOKENS_2);
        }
        return refreshed ? res(200, ME) : res(401, {});
      });

      await Promise.all([httpApi.getFounderAccount(), httpApi.getInvestorAccount()]);

      expect(calls.filter((c) => c.url.endsWith('/v1/auth/refresh'))).toHaveLength(1);
    });

    it('signs the device out when the refresh itself is refused', async () => {
      await signedIn();

      serve((call) => (call.url.endsWith('/v1/auth/refresh') ? res(401, {}) : res(401, {})));

      await expect(httpApi.getFounderAccount()).rejects.toMatchObject({ code: 'unauthorized' });

      // Tokens cleared, so the next call does not even reach the network.
      calls.length = 0;
      await expect(httpApi.getFounderAccount()).rejects.toMatchObject({ code: 'unauthorized' });
      expect(calls).toHaveLength(0);
    });

    it('persists the rotated pair, so a reload does not lose the session', async () => {
      await signedIn();

      let meCalls = 0;
      serve((call) => {
        if (call.url.endsWith('/v1/auth/refresh')) return res(200, TOKENS_2);
        meCalls += 1;
        return meCalls === 1 ? res(401, {}) : res(200, ME);
      });
      await httpApi.getFounderAccount();

      // A fresh import is a fresh app launch: it must read the *rotated* pair
      // off storage, since the old refresh token is already spent.
      jest.resetModules();
      const relaunched = (require('@/api/http') as typeof import('@/api/http')).httpApi;
      calls.length = 0;
      serve(() => res(200, ME));
      await relaunched.getFounderAccount();
      expect(calls[0].auth).toBe('Bearer access-2');
    });
  });

  describe('email verification', () => {
    it('sends the address alongside the code', async () => {
      serve(() => res(204));
      await httpApi.confirmEmail('  Ada@Northwind-Labs.com ', '123456');

      // Both parts are required: a six-digit code is only checked against the
      // one account it belongs to. Without the address the server would have
      // to match it against whichever account happened to fit.
      expect(calls[0]).toMatchObject({
        url: 'http://api.test/v1/auth/verify-email',
        method: 'POST',
        body: { email: 'ada@northwind-labs.com', code: '123456' },
      });
    });

    it('strips the spacing a pasted code carries', async () => {
      serve(() => res(204));
      await httpApi.confirmEmail('ada@northwind-labs.com', ' 123 456 ');
      expect((calls[0].body as { code: string }).code).toBe('123456');

      calls.length = 0;
      await httpApi.confirmEmail('ada@northwind-labs.com', '123-456');
      expect((calls[0].body as { code: string }).code).toBe('123456');
    });

    it('reports a bad code as validation, not as something worse', async () => {
      // Wrong, expired, already used and attempts-exhausted are one failure by
      // design — the client must not try to tell them apart.
      serve(() => res(422, { error: { message: 'That code is invalid or has expired.' } }));
      await expect(
        httpApi.confirmEmail('ada@northwind-labs.com', '000000'),
      ).rejects.toMatchObject({ code: 'validation' });
    });

    it('is unauthenticated, so it works on a device that is signed out', async () => {
      serve(() => res(204));
      await httpApi.confirmEmail('ada@northwind-labs.com', '123456');
      expect(calls[0].auth).toBeNull();
    });

    describe('resend', () => {
      it('posts the address to the resend endpoint', async () => {
        serve(() => res(202, {}));
        await httpApi.resendVerificationEmail('  Ada@Northwind-Labs.com ');
        expect(calls[0]).toMatchObject({
          url: 'http://api.test/v1/auth/verify-email/resend',
          method: 'POST',
          body: { email: 'ada@northwind-labs.com' },
        });
        expect(calls[0].auth).toBeNull();
      });

      it('resolves on the uniform 202, which says nothing about delivery', async () => {
        // No account, already verified, and asked-again-too-soon are all 202.
        serve(() => res(202, {}));
        await expect(
          httpApi.resendVerificationEmail('nobody@northwind-labs.com'),
        ).resolves.toBeUndefined();
      });
    });
  });

  describe('password reset', () => {
    it('posts the token and drops the tokens this device is holding', async () => {
      await signedIn();
      serve(() => res(204));

      await httpApi.resetPassword('  reset-token\n', 'correct-horse-battery');

      expect(calls[0]).toMatchObject({
        url: 'http://api.test/v1/auth/password-reset/confirm',
        method: 'POST',
        body: { token: 'reset-token', password: 'correct-horse-battery' },
      });
      // The server has just revoked every refresh token, so the pair on this
      // device is dead — holding it would leave a live-looking session behind.
      calls.length = 0;
      await expect(httpApi.getFounderAccount()).rejects.toMatchObject({ code: 'unauthorized' });
      expect(calls).toHaveLength(0);
    });

    it('keeps the session when the token is refused', async () => {
      await signedIn();
      serve((call) =>
        call.url.endsWith('/password-reset/confirm')
          ? res(422, { error: { message: 'This link is invalid or has expired.' } })
          : res(200, ME),
      );

      await expect(httpApi.resetPassword('stale', 'correct-horse-battery')).rejects.toMatchObject({
        code: 'validation',
      });

      // Nothing changed server-side, so signing the device out would be wrong.
      calls.length = 0;
      await expect(httpApi.getFounderAccount()).resolves.toBeDefined();
      expect(calls[0].auth).toBe('Bearer access-1');
    });
  });

  describe('startup profile', () => {
    const STORED = {
      id: 'profile-1',
      owner_id: 'user-1',
      name: 'Northwind Labs',
      sector: 'Fintech',
      stage: 'seed',
      country: 'NG',
      currency: 'NGN',
      fields: {},
      missing_fields: ['business_model'],
      created_at: '2026-07-01T00:00:00Z',
      updated_at: '2026-07-01T00:00:00Z',
    };

    it('reads "no profile yet" as null, not as a failure', async () => {
      await signedIn();
      serve(() => res(404, { error: { message: 'Not found' } }));
      await expect(httpApi.getProfile()).resolves.toBeNull();
    });

    it('creates the profile on first save', async () => {
      await signedIn();
      serve((call) => {
        if (call.url.endsWith('/v1/startups/me')) return res(404, {});
        return res(201, STORED);
      });

      const result = await httpApi.saveProfile({
        ...EMPTY_FORM,
        company: 'Northwind Labs',
        location: 'Lagos, Nigeria',
      });

      const create = calls.find((c) => c.method === 'POST')!;
      expect(create.url).toBe('http://api.test/v1/startups');
      expect(create.body).toMatchObject({ name: 'Northwind Labs', country: 'NG' });
      expect(result.profile.company).toBe('Northwind Labs');
      expect(result.missingFields).toEqual(['business_model']);
    });

    it('updates the existing profile rather than creating a second', async () => {
      await signedIn();
      serve((call) => {
        if (call.url.endsWith('/v1/startups/me')) return res(200, STORED);
        return res(200, { ...STORED, name: 'Northwind' });
      });

      await httpApi.saveProfile({ ...EMPTY_FORM, company: 'Northwind' });

      const patch = calls.find((c) => c.method === 'PATCH')!;
      expect(patch.url).toBe('http://api.test/v1/startups/profile-1');
      expect(calls.some((c) => c.method === 'POST')).toBe(false);
    });

    it('recovers when two devices create a profile at once', async () => {
      await signedIn();
      // Both read "none yet", both POST; the loser gets a 409 and must update
      // the profile that now exists instead of reporting a failure.
      let seen = false;
      serve((call) => {
        if (call.url.endsWith('/v1/startups/me')) {
          const answer = seen ? res(200, STORED) : res(404, {});
          seen = true;
          return answer;
        }
        if (call.method === 'POST') return res(409, { error: { message: 'You already have one.' } });
        return res(200, STORED);
      });

      await expect(
        httpApi.saveProfile({ ...EMPTY_FORM, company: 'Northwind Labs' }),
      ).resolves.toMatchObject({ profile: { company: 'Northwind Labs' } });
      expect(calls.some((c) => c.method === 'PATCH')).toBe(true);
    });

    it('reports what it could not save', async () => {
      await signedIn();
      serve((call) => (call.url.endsWith('/v1/startups/me') ? res(404, {}) : res(201, STORED)));

      const result = await httpApi.saveProfile({
        ...EMPTY_FORM,
        location: 'Atlantis',
        stage: 'Bootstrapped',
      });

      expect(result.unmapped.map((u) => u.field).sort()).toEqual(['location', 'stage']);
    });

    it('prefers the stored company name over the guess from the email domain', async () => {
      await signedIn();
      serve((call) => (call.url.endsWith('/v1/startups/me') ? res(200, STORED) : res(200, ME)));

      const account = await httpApi.getFounderAccount();
      expect(account.companyName).toBe('Northwind Labs');
    });

    it('falls back to the domain guess when no profile exists', async () => {
      await signedIn();
      serve((call) => (call.url.endsWith('/v1/startups/me') ? res(404, {}) : res(200, ME)));

      const account = await httpApi.getFounderAccount();
      expect(account.companyName).toBe('Northwind Labs');
    });
  });

  describe('unbuilt endpoints', () => {
    it('names the missing backend task rather than inventing an answer', async () => {
      const error = await httpApi.askMentor('how am I doing?').catch((e: unknown) => e);
      expect((error as InstanceType<typeof ApiFailure>).code).toBe('not_implemented');
      expect((error as Error).message).toMatch(/T3\.7/);
    });

    it('refuses the prototype dealflow shape rather than inventing its numbers', async () => {
      // `/v1/discover` exists, but the summary tier carries no MRR, growth,
      // margin or runway — every number the prototype's card draws. Filling
      // them in is the one thing this must never do.
      const error = await httpApi.listCompanies({} as never, 1, 20).catch((e: unknown) => e);
      expect((error as InstanceType<typeof ApiFailure>).code).toBe('not_implemented');
      expect((error as Error).message).toMatch(/discoverStartups/);
    });
  });

  describe('audit', () => {
    const PROFILE = {
      id: 'profile-1',
      owner_id: 'user-1',
      name: 'Northwind Labs',
      sector: 'Fintech',
      stage: 'seed',
      country: 'NG',
      currency: 'NGN',
      fields: {},
      missing_fields: [],
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    };

    const RUN = {
      id: 'run-1',
      startup_id: 'profile-1',
      status: 'queued',
      rubric_version: 'v1',
      attempts: 0,
      error_code: null,
      error_message: null,
      created_at: '2026-08-01T00:00:00Z',
      started_at: null,
      completed_at: null,
    };

    it('queues an audit against the founder own startup id', async () => {
      await signedIn();
      serve((call) => {
        if (call.url.endsWith('/v1/startups/me')) return res(200, PROFILE);
        return res(202, RUN);
      });

      const run = await httpApi.requestAudit();
      expect(calls.some((c) => c.url === 'http://api.test/v1/startups/profile-1/audits')).toBe(true);
      expect(run).toMatchObject({ id: 'run-1', status: 'queued', rubricVersion: 'v1' });
    });

    it('refuses to audit before there is a profile', async () => {
      await signedIn();
      serve(() => res(404, {}));
      await expect(httpApi.requestAudit()).rejects.toMatchObject({ code: 'not_found' });
      // Never posts to /startups/null/audits, which would be a confusing 422.
      expect(calls.some((c) => c.method === 'POST')).toBe(false);
    });

    it('passes a null score through instead of scoring it zero', async () => {
      await signedIn();
      const report = {
        rubric_version: 'v1',
        data_integrity_score: 'moderate',
        fundability: {
          scope: 'fundability',
          level: 'insufficient_data',
          score: null,
          sufficiency: 'thin',
          rationale: 'Not enough evidence to reach a verdict.',
          evidenced_dimensions: [],
          unevidenced_dimensions: ['traction'],
        },
        saleability: {
          scope: 'saleability',
          level: 'not_yet',
          score: 41,
          sufficiency: 'partial',
          rationale: 'Owner dependency is high.',
          evidenced_dimensions: ['margins'],
          unevidenced_dimensions: [],
        },
        findings: [],
        action_plan: [],
      };
      serve((call) => (call.url.endsWith('/v1/startups/me') ? res(200, PROFILE) : res(200, report)));

      const result = await httpApi.getAuditReport('run-1');
      // A `?? 0` here would turn "could not tell" into a scored zero.
      expect(result.fundability.score).toBeNull();
      expect(result.saleability.score).toBe(41);
    });
  });
});
