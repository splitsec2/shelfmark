import { describe, it, expect } from 'vitest';

import { ownedFormats } from '../components/shared/LibraryBadges';

describe('LibraryBadges.ownedFormats', () => {
  it('returns nothing when the library check is off or nothing is owned', () => {
    expect(ownedFormats(undefined)).toEqual([]);
    expect(ownedFormats(null)).toEqual([]);
    expect(ownedFormats({})).toEqual([]);
    expect(ownedFormats({ ebook: false, audiobook: false })).toEqual([]);
  });

  it('lists owned formats in display order, ignoring unknown keys', () => {
    expect(ownedFormats({ audiobook: true, ebook: true })).toEqual(['ebook', 'audiobook']);
    expect(ownedFormats({ audiobook: true })).toEqual(['audiobook']);
    expect(ownedFormats({ ebook: true, audiobook: undefined })).toEqual(['ebook']);
  });
});
