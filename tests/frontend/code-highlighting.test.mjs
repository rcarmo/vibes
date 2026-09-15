import { test, expect } from 'bun:test';
import { highlightCodeToHtml } from '../../src/vibes/static/js/code-highlighting.js';

test('highlight fenced languages with escaped fallback and bounded input', () => {
    const js = highlightCodeToHtml('const ready = true;\n', 'js');
    expect(js).toContain('<span class="tok-keyword">const</span>');
    expect(js).toContain('<span class="tok-bool">true</span>');
    expect(js.replace(/<[^>]+>/g, '')).toBe('const ready = true;\n');
    expect(highlightCodeToHtml('<img onerror="alert(1)">', 'unknown')).toBe('&lt;img onerror=&quot;alert(1)&quot;&gt;');
    const huge = 'x'.repeat(96 * 1024 + 1);
    expect(highlightCodeToHtml(huge, 'js')).toBe(huge);
    expect(highlightCodeToHtml('print("hello")', 'python')).toContain('tok-string');
});
