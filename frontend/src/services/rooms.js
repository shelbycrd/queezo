export const roomPath = id => '/rooms/' + encodeURIComponent(id);
export const roomApi = id => '/rooms/' + encodeURIComponent(id);
export const roomModes = {collaborative:'Collaborative',challenge:'Challenge'};

export function remainingSeconds(deadline, serverNow) {
  const time = Date.parse(deadline);
  return Number.isFinite(time) ? Math.max(0, Math.ceil((time - serverNow) / 1000)) : null;
}

export function roomSocketUrl(id, origin) {
  const url = new URL('/api' + roomApi(id) + '/live',origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.href;
}

export function accuracy(result) {
  return result.questions ? Math.round(100 * result.correct / result.questions) : 0;
}

// Invitations present now that were not in the previously seen set, newest first.
export function arrivedInvites(seen, invites) {
  return invites.filter(invite => !seen.has(invite.room_id));
}
