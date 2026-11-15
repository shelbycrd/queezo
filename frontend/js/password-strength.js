// Advisory estimate only: registration does not require a particular score.
export function passwordStrength(password, personal = []) {
  if (!password) return {score:0, level:'Not entered', tips:['Try 12 or more characters.']};
  const chars = [...password];
  const lower = password.toLowerCase();
  const tips = [];
  const types = [/[a-z]/.test(password), /[A-Z]/.test(password), /\d/.test(password), /[^\p{L}\p{N}\s]/u.test(password)].filter(Boolean).length;
  let score = Math.min(40,chars.length * 2) + types * 10 + Math.min(20,new Set(chars).size * 2);
  if (chars.length < 12) { score = Math.min(score,40); tips.push('Try at least 12 characters.'); }
  if (types < 3) tips.push('Mix upper/lowercase letters, numbers, and symbols, or use a long unpredictable passphrase.');
  const common = /password|passw[o0]rd|qwerty|letmein|welcome|admin|iloveyou|123456/.test(lower);
  const repeated = /(.)\1{2,}|(.{2,6})\2{2,}/u.test(lower);
  if (common) { score = Math.min(score,25); tips.push('Avoid common words such as password and common keyboard patterns.'); }
  if (repeated) { score -= 30; tips.push('Avoid repeated letters, numbers, or repeated patterns.'); }
  if (['abcdefghijklmnopqrstuvwxyz','zyxwvutsrqponmlkjihgfedcba','0123456789','9876543210','qwertyuiop','asdfghjkl'].some(sequence => [...Array(Math.max(0,sequence.length-3))].some((_,i)=>lower.includes(sequence.slice(i,i+4))))) {
    score = Math.min(score,55); tips.push('Avoid consecutive sequences such as abcd or 1234.');
  }
  if (personal.some(value => String(value).toLowerCase().split(/[@\s._-]+/).some(part => part.length >= 3 && lower.includes(part)))) {
    score = Math.min(score - 15,55); tips.push('Avoid your display name, username, or email in the password.');
  }
  if (new Set(chars).size <= 2) score = Math.min(score,15);
  score = Math.max(0,Math.min(100,score));
  return {score, level:score < 45 ? 'Low' : score < 75 ? 'Moderate' : 'Strong', tips:tips.length ? tips : ['Use a unique password you do not use on another website.']};
}
