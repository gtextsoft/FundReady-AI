/**
 * Reading the single-use token off an emailed link.
 *
 * Small surface, but every one of these cases has burned somebody: a wrapped
 * URL leaving a newline on the end, a duplicated query parameter arriving as an
 * array, and the empty-string case that would otherwise send `?token=` to the
 * server and get back a generic "this link is invalid".
 */

import { tokenFromParams } from '@/lib/deep-link';

describe('tokenFromParams', () => {
  it('reads a plain token', () => {
    expect(tokenFromParams({ token: 'abc123' })).toBe('abc123');
  });

  it('trims whitespace a mail client wrapped in', () => {
    expect(tokenFromParams({ token: ' abc123\n' })).toBe('abc123');
  });

  it('takes the first of a repeated parameter', () => {
    expect(tokenFromParams({ token: ['first', 'second'] })).toBe('first');
  });

  it('returns null rather than an empty token', () => {
    // `?token=` must not be posted: the server would answer with the same
    // "invalid or expired" message as a genuinely bad token, and the screen
    // would blame the link instead of showing the paste box.
    expect(tokenFromParams({ token: '' })).toBeNull();
    expect(tokenFromParams({ token: '   ' })).toBeNull();
    expect(tokenFromParams({ token: [] })).toBeNull();
  });

  it('returns null when the parameter is absent', () => {
    expect(tokenFromParams({})).toBeNull();
    expect(tokenFromParams({ other: 'x' })).toBeNull();
    expect(tokenFromParams({ token: undefined })).toBeNull();
  });

  it('reads a differently named parameter when asked', () => {
    expect(tokenFromParams({ code: 'xyz' }, 'code')).toBe('xyz');
  });
});
