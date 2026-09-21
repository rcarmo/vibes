import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

export function compareImages(left, right) {
  if (left.width !== right.width || left.height !== right.height) {
    throw new Error('Image dimensions differ; resizing is not permitted');
  }
  const diff = new PNG({ width: left.width, height: left.height });
  let exactPixels = 0;
  for (let i = 0; i < left.data.length; i += 4) {
    if ([0, 1, 2, 3].some(channel => left.data[i + channel] !== right.data[i + channel])) exactPixels++;
  }
  const perceptualPixels = pixelmatch(left.data, right.data, diff.data, left.width, left.height,
    { threshold: 0.1, includeAA: false });
  return { diff, exactPixels, perceptualPixels, totalPixels: left.width * left.height,
    exactMatch: exactPixels === 0, masked: false };
}

export function overlayImages(left, right) {
  if (left.width !== right.width || left.height !== right.height) throw new Error('Image dimensions differ');
  const output = new PNG({ width: left.width, height: left.height });
  for (let i = 0; i < output.data.length; i++) output.data[i] = Math.round((left.data[i] + right.data[i]) / 2);
  return output;
}

export function assessRepeats(images) {
  if (images.length < 2) throw new Error('At least two fresh-context captures are required');
  const comparisons = images.slice(1).map(image => {
    const { diff, ...metrics } = compareImages(images[0], image);
    return metrics;
  });
  return { stable: comparisons.every(item => item.exactMatch), comparisons };
}
