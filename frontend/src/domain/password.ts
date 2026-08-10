/**
 * The one password rule, shared by sign-up and password reset.
 *
 * The minimum mirrors the server's (`Password = Field(min_length=12)` in the
 * backend's identity schemas). It lives here rather than in a screen because
 * two screens now mint passwords, and a client that lets through something the
 * server refuses turns a typo into an unexplained `422`.
 *
 * There is deliberately **no** complexity rule — no "one uppercase, one digit,
 * one symbol". Length is what makes a password hard to guess; composition rules
 * mostly produce `Password1!` and a note on a monitor. The server hashes with
 * Argon2id and the account is protected by a failed-login counter and MFA,
 * which is where the real defence sits.
 */

export const MIN_PASSWORD = 12;

export type PasswordIssue = 'empty' | 'tooShort' | 'mismatch' | null;

export type PasswordCheck = { ok: boolean; issue: PasswordIssue; message: string | null };

const OK: PasswordCheck = { ok: true, issue: null, message: null };

/**
 * Validates a new password, and its confirmation when one is supplied.
 *
 * Pass `confirmation` for the two-field form; omit it where there is only one
 * field. An empty confirmation is not treated as a mismatch — that would flash
 * an error at someone who has simply not finished typing yet.
 */
export function checkPassword(password: string, confirmation?: string): PasswordCheck {
  if (!password) {
    return { ok: false, issue: 'empty', message: 'Choose a password.' };
  }
  if (password.length < MIN_PASSWORD) {
    return {
      ok: false,
      issue: 'tooShort',
      message: `Use at least ${MIN_PASSWORD} characters.`,
    };
  }
  if (confirmation !== undefined && confirmation !== '' && confirmation !== password) {
    return { ok: false, issue: 'mismatch', message: 'Both passwords must match.' };
  }
  return OK;
}

/** Hint text for the password field, so the rule is stated before it is broken. */
export const PASSWORD_HINT = `At least ${MIN_PASSWORD} characters.`;
