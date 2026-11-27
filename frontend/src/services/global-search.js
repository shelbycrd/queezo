export const SEARCH_TABS = [
  {value:'all', label:'All'},
  {value:'public', label:'Public Decks'},
  {value:'mine', label:'My Decks'},
  {value:'users', label:'Users'},
];
export const MAX_QUERY = 80;

export const normalizeQuery = value => String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, MAX_QUERY);
export const normalizeTab = value => SEARCH_TABS.some(tab => tab.value === value) ? value : 'all';
export const normalizePage = value => { const page = Number.parseInt(value, 10); return page >= 1 && page <= 1000 ? page : 1; };

// The in-app address for a search; the tab and page are only written when they differ from the defaults.
export function searchLocation(query, tab = 'all', page = 1) {
  const q = normalizeQuery(query);
  const params = new URLSearchParams({q});
  if (normalizeTab(tab) !== 'all') params.set('tab', tab);
  if (page > 1) params.set('page', String(page));
  return '/search?' + params.toString();
}

export const searchRequestPath = (query, tab, page) =>
  `/search?${new URLSearchParams({q:normalizeQuery(query), type:normalizeTab(tab), page:String(normalizePage(page))})}`;

export const recentRequestPath = refs => '/search/recent?' + refs.map(ref => 'ref=' + encodeURIComponent(ref)).join('&');
