import { test, expect } from '@playwright/test';
import { verifyDraftStream } from './helpers/draft-stream-fixture.mjs';
test('draft chunks accumulate without duplicating expanded deltas or Pi snapshots', async ({page}) => {
    await verifyDraftStream(page, expect);
});
