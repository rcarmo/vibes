import { describe, expect, test } from 'bun:test';
import {
  findPopupTypeaheadMatch,
  isPopupTypeaheadKey,
  resolvePopupTypeaheadMatch,
  updatePopupTypeaheadBuffer,
} from '../../static/js/ui/popup-typeahead.ts';

describe('popup typeahead utilities', () => {
  test('recognizes printable unmodified keys', () => {
    expect(isPopupTypeaheadKey({ key: 'a' })).toBe(true);
    expect(isPopupTypeaheadKey({ key: ' ', ctrlKey: false })).toBe(false);
    expect(isPopupTypeaheadKey({ key: 'a', metaKey: true })).toBe(false);
    expect(isPopupTypeaheadKey({ key: 'a', isComposing: true })).toBe(false);
  });

  test('updates and resets buffer', () => {
    expect(updatePopupTypeaheadBuffer(null, 'A', 1000)).toEqual({ value: 'a', updatedAt: 1000 });
    expect(updatePopupTypeaheadBuffer({ value: 'a', updatedAt: 1000 }, 'b', 1200)).toEqual({ value: 'ab', updatedAt: 1200 });
    expect(updatePopupTypeaheadBuffer({ value: 'ab', updatedAt: 1200 }, 'c', 2500)).toEqual({ value: 'c', updatedAt: 2500 });
  });

  test('finds matches from labels', () => {
    const items = [{ label: 'Alpha' }, { label: 'Beta' }, { label: 'Gamma' }];
    const getLabel = (item: { label: string }) => item.label;
    expect(findPopupTypeaheadMatch(items, 'ga', 0, getLabel)).toBe(2);
    expect(findPopupTypeaheadMatch(items, 'ta', 0, getLabel)).toBe(1);
    expect(resolvePopupTypeaheadMatch(items, 'alp', 0, getLabel)).toBe(0);
  });
});
