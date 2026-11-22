export const avatars = ['dog','cat','chicken'];
export const visibility = {
  public:'Public · Anyone with the link can view your profile, and it can appear in profile search.',
  unlisted:'Unlisted · Anyone with the link can view your profile. It stays out of profile search.',
  private:'Private · Only you can view your profile.',
};
export const reportReasons = {
  inappropriate_bio:'Inappropriate bio', impersonation:'Impersonation', spam:'Spam', other:'Other',
};
export const avatarUrl = avatar => '/assets/profile/' + (avatars.includes(avatar) ? avatar : 'cat') + '.svg';
export const profilePath = username => '/u/' + encodeURIComponent(username);
export const profileApi = username => '/profiles/users/' + encodeURIComponent(username);
export function deckPagePath(username, {q = '', sort = 'newest', page = 1} = {}) {
  return profileApi(username) + '/decks?' + new URLSearchParams({q:q.trim(),sort,page});
}
export function profileDraft(profile) {
  return {
    display_name:profile.display_name, bio:profile.bio, interest_tags:[...profile.interest_tags],
    avatar:profile.avatar, visibility:profile.visibility, featured_deck_id:profile.featured_deck_id,
  };
}
export const dateTime = value => new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});
