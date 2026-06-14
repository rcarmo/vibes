import { describe, expect, test } from 'bun:test';
import { getStandaloneTabUrl } from '../../static/js/components/tab-strip.ts';

describe('tab strip standalone URL resolution', () => {
  test('routes known file types to viewers', () => {
    expect(getStandaloneTabUrl('docs/report.pdf')).toBe('/pdf-viewer/?path=docs%2Freport.pdf');
    expect(getStandaloneTabUrl('data/table.csv')).toBe('/csv-viewer/?path=data%2Ftable.csv');
    expect(getStandaloneTabUrl('web/index.html')).toBe('/html-viewer/?path=web%2Findex.html');
    expect(getStandaloneTabUrl('video/demo.mp4')).toBe('/video-viewer/?path=video%2Fdemo.mp4');
    expect(getStandaloneTabUrl('images/photo.jpg')).toBe('/image-viewer/?path=images%2Fphoto.jpg');
  });

  test('routes office and drawio files specially', () => {
    expect(getStandaloneTabUrl('docs/a b.docx')).toBe('/office-viewer/?url=%2Fworkspace%2Fraw%3Fpath%3Ddocs%252Fa%2520b.docx&name=a%20b.docx');
    expect(getStandaloneTabUrl('diagram.drawio')).toBe('/drawio/edit?path=diagram.drawio');
    expect(getStandaloneTabUrl('diagram.drawio', { hasPopOutTab: true })).toBeNull();
  });

  test('ignores unknown or empty paths', () => {
    expect(getStandaloneTabUrl('notes.md')).toBeNull();
    expect(getStandaloneTabUrl('')).toBeNull();
    expect(getStandaloneTabUrl(null)).toBeNull();
  });
});
