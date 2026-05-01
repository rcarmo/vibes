export const POPUP_TYPEAHEAD_RESET_MS = 700;

function normalize(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/^@/, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function labelMatchesQuery(label, query) {
  const normalizedLabel = normalize(label);
  const normalizedQuery = normalize(query);
  if (!normalizedQuery) return false;
  return normalizedLabel.startsWith(normalizedQuery) || normalizedLabel.includes(normalizedQuery);
}

export function isPopupTypeaheadKey(event) {
  if (!event) return false;
  if (event.isComposing) return false;
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  return typeof event.key === 'string' && event.key.length === 1 && /\S/.test(event.key);
}

export function updatePopupTypeaheadBuffer(
  previous,
  key,
  now = Date.now(),
  resetMs = POPUP_TYPEAHEAD_RESET_MS,
) {
  const prior = previous && typeof previous === 'object' ? previous : { value: '', updatedAt: 0 };
  const char = String(key || '').trim().toLowerCase();
  if (!char) return { value: '', updatedAt: now };
  const shouldReset = !prior.value || !Number.isFinite(prior.updatedAt) || (now - prior.updatedAt) > resetMs;
  return {
    value: shouldReset ? char : `${prior.value}${char}`,
    updatedAt: now,
  };
}

function rotatedIndices(length, startIndex) {
  const size = Math.max(0, Number(length) || 0);
  if (size <= 0) return [];
  const start = Number.isInteger(startIndex) ? startIndex : 0;
  const normalizedStart = ((start % size) + size) % size;
  const out = [];
  for (let i = 0; i < size; i += 1) {
    out.push((normalizedStart + i) % size);
  }
  return out;
}

export function findPopupTypeaheadMatch(
  items,
  query,
  startIndex = 0,
  getLabel = (item) => item,
) {
  const normalizedQuery = normalize(query);
  if (!normalizedQuery) return -1;
  const list = Array.isArray(items) ? items : [];
  const indices = rotatedIndices(list.length, startIndex);
  const labels = list.map((item) => normalize(getLabel(item)));

  for (const idx of indices) {
    if (labels[idx].startsWith(normalizedQuery)) return idx;
  }
  for (const idx of indices) {
    if (labels[idx].includes(normalizedQuery)) return idx;
  }
  return -1;
}

export function resolvePopupTypeaheadMatch(
  items,
  query,
  currentIndex = -1,
  getLabel = (item) => item,
) {
  const list = Array.isArray(items) ? items : [];
  if (currentIndex >= 0 && currentIndex < list.length) {
    const currentLabel = getLabel(list[currentIndex]);
    if (labelMatchesQuery(currentLabel, query)) {
      return currentIndex;
    }
  }
  return findPopupTypeaheadMatch(list, query, 0, getLabel);
}
