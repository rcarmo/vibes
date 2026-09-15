// Shared classic disclosure geometry, instead of platform-dependent text glyphs.
import { html } from '../vendor/preact-htm.js';
const points = { right: '3,1.5 8,5 3,8.5', down: '1.5,3 8.5,3 5,8', up: '1.5,7 8.5,7 5,2', left: '7,1.5 2,5 7,8.5' };
export const disclosureTriangle = direction => html`<svg class=${`ui-disclosure-triangle ui-disclosure-triangle-${direction}`} viewBox="0 0 10 10" aria-hidden="true" focusable="false"><polygon points=${points[direction] || points.right}></polygon></svg>`;
