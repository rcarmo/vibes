export const POPUP_TYPEAHEAD_RESET_MS = 700;

export interface PopupTypeaheadBuffer {
  value: string;
  updatedAt: number;
}

interface PopupTypeaheadKeyLike {
  key?: string;
  isComposing?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
}

function normalize(value: unknown): string {
  return String(value || '')
    .toLowerCase()
    .replace(/^@/, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function labelMatchesQuery(label: unknown, query: unknown): boolean {
  const normalizedLabel = normalize(label);
  const normalizedQuery = normalize(query);
  if (!normalizedQuery) return false;
  return normalizedLabel.startsWith(normalizedQuery) || normalizedLabel.includes(normalizedQuery);
}

export function isPopupTypeaheadKey(event: PopupTypeaheadKeyLike | null | undefined): boolean {
  if (!event) return false;
  if (event.isComposing) return false;
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  return typeof event.key === 'string' && event.key.length === 1 && /\S/.test(event.key);
}

export function updatePopupTypeaheadBuffer(
  previous: Partial<PopupTypeaheadBuffer> | null | undefined,
  key: unknown,
  now = Date.now(),
  resetMs = POPUP_TYPEAHEAD_RESET_MS,
): PopupTypeaheadBuffer {
  const prior = previous && typeof previous === 'object' ? previous : { value: '', updatedAt: 0 };
  const char = String(key || '').trim().toLowerCase();
  if (!char) return { value: '', updatedAt: now };
  const shouldReset = !prior.value || !Number.isFinite(prior.updatedAt) || (now - Number(prior.updatedAt)) > resetMs;
  return {
    value: shouldReset ? char : `${prior.value}${char}`,
    updatedAt: now,
  };
}

function rotatedIndices(length: unknown, startIndex: unknown): number[] {
  const size = Math.max(0, Number(length) || 0);
  if (size <= 0) return [];
  const start = Number.isInteger(startIndex) ? Number(startIndex) : 0;
  const normalizedStart = ((start % size) + size) % size;
  const out: number[] = [];
  for (let i = 0; i < size; i += 1) {
    out.push((normalizedStart + i) % size);
  }
  return out;
}

export function findPopupTypeaheadMatch<T>(
  items: T[] | null | undefined,
  query: unknown,
  startIndex = 0,
  getLabel: (item: T) => unknown = (item) => item,
): number {
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

export function resolvePopupTypeaheadMatch<T>(
  items: T[] | null | undefined,
  query: unknown,
  currentIndex = -1,
  getLabel: (item: T) => unknown = (item) => item,
): number {
  const list = Array.isArray(items) ? items : [];
  if (currentIndex >= 0 && currentIndex < list.length) {
    const currentLabel = getLabel(list[currentIndex]);
    if (labelMatchesQuery(currentLabel, query)) {
      return currentIndex;
    }
  }
  return findPopupTypeaheadMatch(list, query, 0, getLabel);
}
