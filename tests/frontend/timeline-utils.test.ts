import { describe, expect, test } from 'bun:test';
import {
  extractAttachmentRefs,
  extractFileRefs,
  extractMessageRefs,
  fallbackAvatarInfo,
  formatFileSize,
  getDisplayContent,
  getMimeIcon,
  sanitizeUrl,
} from '../../static/js/features/timeline/timeline-utils.ts';

describe('timeline utilities', () => {
  test('sanitizes URLs', () => {
    expect(sanitizeUrl(' https://example.test ')).toBe('https://example.test');
    expect(sanitizeUrl('mailto:test@example.test')).toBe('mailto:test@example.test');
    expect(sanitizeUrl('javascript:alert(1)')).toBe('');
  });

  test('extracts file and message reference blocks', () => {
    expect(extractFileRefs('hello\n\nFiles:\n- a.md\n- b.ts\n\nbye')).toEqual({ content: 'hello\n\nbye', fileRefs: ['a.md', 'b.ts'] });
    expect(extractMessageRefs('Messages:\n- msg-1\nbody')).toEqual({ content: 'body', messageRefs: ['msg-1'] });
  });

  test('extracts attachment refs', () => {
    expect(extractAttachmentRefs('x\nImages:\n- attachment:abc (Photo)\n- loose label\ny')).toEqual({
      content: 'x\ny',
      attachments: [
        { id: 'abc', label: 'Photo', raw: 'attachment:abc (Photo)' },
        { id: null, label: 'loose label', raw: 'loose label' },
      ],
    });
  });

  test('formats display helpers', () => {
    expect(formatFileSize(512)).toBe('512 B');
    expect(formatFileSize(2048)).toBe('2.0 KB');
    expect(getMimeIcon('image/png')).toBe('🖼️');
    expect(getMimeIcon('application/pdf')).toBe('📄');
    expect(getDisplayContent('hello')).toBe('hello');
    expect(fallbackAvatarInfo('Rui')).toMatchObject({ letter: 'R', image: null });
  });
});
