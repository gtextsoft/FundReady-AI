/**
 * The onboarding store's load path.
 *
 * `loaded` gates the whole first step: the form waits on it before seeding the
 * company name, so anything that leaves it false freezes onboarding on an
 * empty form. That is not hypothetical — a founder who has just signed up is
 * `pending_verification`, and the server answers `/v1/startups/me` with 403
 * until they confirm their address, which is the *normal* state for the first
 * person to reach this screen.
 */

import { firstIncompleteStep, isAssessmentComplete, useFounder } from '@/store/founder';
import { ApiFailure } from '@/api/contract';
import { EMPTY_PROFILE, type FounderProfile } from '@/domain/types';

const mockGetProfile = jest.fn();
const mockSaveProfile = jest.fn();
const mockListAuditRuns = jest.fn();
const mockGetAuditReport = jest.fn();

jest.mock('@/api', () => ({
  ...jest.requireActual('@/api/contract'),
  api: {
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
    saveProfile: (...args: unknown[]) => mockSaveProfile(...args),
    submitAssessment: jest.fn(),
    listAuditRuns: (...args: unknown[]) => mockListAuditRuns(...args),
    getAuditReport: (...args: unknown[]) => mockGetAuditReport(...args),
  },
}));

const reset = () => useFounder.getState().reset();

describe('loading a stored profile', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockGetProfile.mockReset();
    mockSaveProfile.mockReset();
    reset();
  });

  afterEach(() => {
    reset();
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('finishes loading when the server refuses an unverified founder', async () => {
    // The regression this file exists for. A 403 here is the ordinary state of
    // a brand-new account, not a failure worth blocking the form over.
    mockGetProfile.mockRejectedValue(
      new ApiFailure('forbidden', 'Verify your email address to continue.'),
    );

    await useFounder.getState().load();

    expect(useFounder.getState().loaded).toBe(true);
    expect(useFounder.getState().profile.company).toBe('');
  });

  it('finishes loading when the endpoint does not exist', async () => {
    mockGetProfile.mockRejectedValue(new ApiFailure('not_implemented', 'Not built.'));
    await useFounder.getState().load();
    expect(useFounder.getState().loaded).toBe(true);
  });

  it('finishes loading when the network is down', async () => {
    mockGetProfile.mockRejectedValue(new ApiFailure('network', 'Could not reach the API.'));
    await useFounder.getState().load();
    expect(useFounder.getState().loaded).toBe(true);
  });

  it('never rejects, whatever the transport does', async () => {
    mockGetProfile.mockRejectedValue(new Error('something nobody predicted'));
    await expect(useFounder.getState().load()).resolves.toBeUndefined();
    expect(useFounder.getState().loaded).toBe(true);
  });

  it('adopts a stored profile over an untouched form', async () => {
    const stored: FounderProfile = { ...EMPTY_PROFILE, company: 'Northwind Labs' };
    mockGetProfile.mockResolvedValue(stored);

    await useFounder.getState().load();

    expect(useFounder.getState().profile.company).toBe('Northwind Labs');
  });

  it('reopens on the first incomplete step', async () => {
    const stored: FounderProfile = {
      ...EMPTY_PROFILE,
      company: 'Northwind Labs',
      sector: 'Fintech',
      location: 'Nigeria',
      year: '2023',
      description: 'Reconciliation software.',
      businessModel: 'Subscription.',
      // Step 2 still empty — resume there, not at step 1.
    };
    mockGetProfile.mockResolvedValue(stored);

    await useFounder.getState().load();

    expect(useFounder.getState().step).toBe(2);
  });

  it('does not overwrite answers already being typed', async () => {
    // A slow request must not replace what someone is halfway through writing.
    useFounder.getState().setField('company', 'What I Am Typing');
    mockGetProfile.mockResolvedValue({ ...EMPTY_PROFILE, company: 'Stored Name' });

    await useFounder.getState().load();

    expect(useFounder.getState().profile.company).toBe('What I Am Typing');
    expect(useFounder.getState().loaded).toBe(true);
  });
});

describe('autosave', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockSaveProfile.mockReset();
    mockSaveProfile.mockImplementation(async (profile: FounderProfile) => ({
      profile,
      unmapped: [],
      missingFields: [],
    }));
    reset();
  });

  afterEach(() => {
    reset();
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('writes the profile after typing settles', async () => {
    useFounder.getState().setField('company', 'Northwind');
    expect(mockSaveProfile).not.toHaveBeenCalled();

    await jest.advanceTimersByTimeAsync(900);

    expect(mockSaveProfile).toHaveBeenCalledTimes(1);
    expect(useFounder.getState().dirty).toBe(false);
  });

  it('coalesces keystrokes into one write', async () => {
    useFounder.getState().setField('company', 'N');
    useFounder.getState().setField('company', 'No');
    useFounder.getState().setField('company', 'Northwind');

    await jest.advanceTimersByTimeAsync(900);

    expect(mockSaveProfile).toHaveBeenCalledTimes(1);
    expect(mockSaveProfile.mock.calls[0][0].company).toBe('Northwind');
  });

  it('keeps dirty when a newer edit lands during save', async () => {
    let release!: (value: {
      profile: FounderProfile;
      unmapped: never[];
      missingFields: never[];
    }) => void;
    mockSaveProfile.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );

    useFounder.getState().setField('company', 'First');
    // Flush immediately so the hanging request is the explicit save, not the
    // debounced one — otherwise fake timers and the save queue deadlock.
    const pending = useFounder.getState().save();
    await Promise.resolve();
    expect(mockSaveProfile).toHaveBeenCalledTimes(1);

    useFounder.getState().setField('company', 'Second');
    release({
      profile: { ...EMPTY_PROFILE, company: 'First' },
      unmapped: [],
      missingFields: [],
    });
    await pending;

    expect(useFounder.getState().profile.company).toBe('Second');
    expect(useFounder.getState().dirty).toBe(true);
  });
});

describe('firstIncompleteStep', () => {
  it('points at the earliest step still missing a required answer', () => {
    expect(firstIncompleteStep(EMPTY_PROFILE)).toBe(1);
    expect(
      firstIncompleteStep({
        ...EMPTY_PROFILE,
        company: 'A',
        sector: 'Fintech',
        location: 'Nigeria',
        year: '2023',
        description: 'Does a thing.',
        businessModel: 'SaaS',
      }),
    ).toBe(2);
  });
});

describe('isAssessmentComplete', () => {
  const full: FounderProfile = {
    ...EMPTY_PROFILE,
    company: 'Northwind Labs',
    sector: 'Fintech',
    location: 'Lagos, Nigeria',
    year: '2023',
    description: 'Reconciliation software.',
    businessModel: 'Subscription.',
    stage: 'Seed',
    revenue: '48000',
    costs: '62000',
    cash: '410000',
    founders: '2',
    teamSize: '7',
  };

  it('is true only once every step has what the audit needs', () => {
    expect(isAssessmentComplete(full)).toBe(true);
    expect(isAssessmentComplete(EMPTY_PROFILE)).toBe(false);
  });

  it('is false when one required answer is missing', () => {
    // This is what decides whether the dashboard offers a score or an
    // invitation, so a half-filled form must not read as "assessed".
    for (const missing of ['description', 'cash', 'teamSize'] as const) {
      expect(isAssessmentComplete({ ...full, [missing]: '' })).toBe(false);
    }
  });
});

describe('loadLatestAudit', () => {
  beforeEach(() => {
    mockListAuditRuns.mockReset();
    mockGetAuditReport.mockReset();
    reset();
  });

  const run = (status: string) => ({
    id: 'run-1',
    startupId: 'p1',
    status,
    rubricVersion: 'v1',
    attempts: 0,
    errorCode: null,
    errorMessage: null,
    createdAt: '2026-08-09T00:00:00Z',
    startedAt: null,
    completedAt: null,
  });

  it('reads the report when the newest run succeeded', async () => {
    mockListAuditRuns.mockResolvedValue([run('succeeded')]);
    mockGetAuditReport.mockResolvedValue({ rubricVersion: 'v1' });

    await useFounder.getState().loadLatestAudit();

    expect(useFounder.getState().run?.status).toBe('succeeded');
    expect(useFounder.getState().report).toEqual({ rubricVersion: 'v1' });
  });

  it('does not poll an unfinished run', async () => {
    // The dashboard only shows the latest state. Polling from a tab someone
    // may sit on would keep firing requests for as long as they leave it open.
    mockListAuditRuns.mockResolvedValue([run('queued')]);

    await useFounder.getState().loadLatestAudit();

    expect(useFounder.getState().run?.status).toBe('queued');
    expect(useFounder.getState().report).toBeNull();
    expect(mockGetAuditReport).not.toHaveBeenCalled();
  });

  it('stays silent when the server refuses an unverified account', async () => {
    // A 403 here is the normal state of a new account, and the dashboard must
    // not throw an error panel at somebody who did not ask for an audit.
    mockListAuditRuns.mockRejectedValue(
      new ApiFailure('forbidden', 'Verify your email address to continue.'),
    );

    await expect(useFounder.getState().loadLatestAudit()).resolves.toBeUndefined();
    expect(useFounder.getState().auditError).toBeNull();
  });

  it('does nothing when there has never been a run', async () => {
    mockListAuditRuns.mockResolvedValue([]);
    await useFounder.getState().loadLatestAudit();
    expect(useFounder.getState().run).toBeNull();
  });
});
