/**
 * The shared password rule.
 *
 * The minimum has to match the server's exactly: one character shorter here
 * and the client sends something the API answers with a bare `422`, which the
 * user reads as "the app is broken".
 */

import { checkPassword, MIN_PASSWORD, PASSWORD_HINT } from '@/domain/password';

describe('checkPassword', () => {
  it('matches the server minimum', () => {
    // `Password = Annotated[str, Field(min_length=12)]` in the backend's
    // identity schemas.
    expect(MIN_PASSWORD).toBe(12);
    expect(PASSWORD_HINT).toContain('12');
  });

  it('accepts a long enough password', () => {
    expect(checkPassword('correct-horse-battery')).toEqual({
      ok: true,
      issue: null,
      message: null,
    });
  });

  it('rejects one character short', () => {
    expect(checkPassword('a'.repeat(MIN_PASSWORD - 1)).issue).toBe('tooShort');
    expect(checkPassword('a'.repeat(MIN_PASSWORD)).ok).toBe(true);
  });

  it('distinguishes empty from too short', () => {
    expect(checkPassword('').issue).toBe('empty');
  });

  it('catches a mismatched confirmation', () => {
    expect(checkPassword('correct-horse-battery', 'correct-horse-bettery').issue).toBe('mismatch');
    expect(checkPassword('correct-horse-battery', 'correct-horse-battery').ok).toBe(true);
  });

  it('does not call an unfinished confirmation a mismatch', () => {
    // Flashing "both passwords must match" at someone mid-keystroke is noise.
    expect(checkPassword('correct-horse-battery', '').ok).toBe(true);
  });

  it('applies the length rule before the mismatch rule', () => {
    // Otherwise a short password with a typo reports the typo, the user fixes
    // it, and only then learns about the length.
    expect(checkPassword('short', 'different').issue).toBe('tooShort');
  });

  it('imposes no composition rule', () => {
    // Length is the defence; `Password1!` is not a security improvement.
    expect(checkPassword('aaaaaaaaaaaaaaaa').ok).toBe(true);
  });
});
