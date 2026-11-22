import {ref} from 'vue';

export const friendsOpen = ref(false);
export const friendCount = ref(null);
export function openFriends() { friendsOpen.value = true; }
export function closeFriends() { friendsOpen.value = false; }
