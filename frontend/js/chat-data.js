export const recentChats = chats => [...chats].sort((a,b) => b.updatedAt - a.updatedAt);
export function validChats(value) {
  if (!Array.isArray(value)) return [];
  return value.slice(0,100).filter(chat => chat && typeof chat.id === 'string' && typeof chat.name === 'string' && chat.name.trim() && chat.name.length <= 80 && Number.isFinite(chat.updatedAt) && Array.isArray(chat.messages)).map(chat => ({id:chat.id, name:chat.name, updatedAt:chat.updatedAt, messages:chat.messages.filter(message => message && typeof message.text === 'string' && message.text.length <= 2000 && Number.isFinite(message.at)).slice(-500)}));
}
