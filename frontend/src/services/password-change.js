// Immediate feedback for the Change Password form. The server repeats every check.
export const PASSWORD_MIN = 11;
export const PASSWORD_MAX = 1024;

export function passwordChangeProblem({current, replacement, confirm}) {
  if (!current) return 'Enter your current password.';
  if (!replacement) return 'Enter a new password.';
  const length = replacement.length;
  if (length < PASSWORD_MIN || length > PASSWORD_MAX) return `Passwords must contain ${PASSWORD_MIN}–${PASSWORD_MAX} characters.`;
  if (replacement !== confirm) return 'New password and confirmation do not match.';
  if (replacement === current) return 'Choose a password different from your current one.';
  return '';
}
