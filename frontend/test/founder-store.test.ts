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

import { useFounder } from '@/store/founder';
import { ApiFailure } from '@/api/contract';
import { EMPTY_PROFILE, type FounderProfile } from '@/domain/types';

const mockGetProfile = jest.fn();

jest.mock('@/api', () => ({
  ...jest.requireActual('@/api/contract'),
  api: {
    getProfile: (...args: unknown[]) => mockGetProfile(...args),
    saveProfile: jest.fn(),
    submitAssessment: jest.fn(),
  },
}));

const reset = () => useFounder.getState().reset();

describe('loading a stored profile', () => {
  beforeEach(() => {
    mockGetProfile.mockReset();
    reset();
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

  it('does not overwrite answers already being typed', async () => {
    // A slow request must not replace what someone is halfway through writing.
    useFounder.getState().setField('company', 'What I Am Typing');
    mockGetProfile.mockResolvedValue({ ...EMPTY_PROFILE, company: 'Stored Name' });

    await useFounder.getState().load();

    expect(useFounder.getState().profile.company).toBe('What I Am Typing');
    expect(useFounder.getState().loaded).toBe(true);
  });
});
