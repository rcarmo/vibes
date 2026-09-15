import { test, expect } from '@playwright/test';

async function fixture(page, supported = true) {
    await page.addInitScript(supported => {
        window.fixtureSpeech = { spoken: [], cancels: 0 };
        Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: supported ? {
            cancel() { window.fixtureSpeech.cancels++; },
            speak(utterance) { window.fixtureSpeech.spoken.push(utterance); },
        } : undefined });
        window.SpeechSynthesisUtterance = supported ? class { constructor(text) { this.text = text; } } : undefined;
    }, supported);
    await page.route('**/timeline?*', route => route.fulfill({ json: { posts: [
        { id: 501, data: { type: 'user_message', content: 'User text', session_id: 'default' } },
        { id: 502, data: { type: 'agent_response', content: '## First message\n\nReadable text.', agent_id: 'default', session_id: 'default' } },
        { id: 503, data: { type: 'agent_response', content: 'Second message', agent_id: 'default', session_id: 'default' } },
    ], has_more: false } }));
    await page.goto('/');
    await expect(page.locator('#post-503')).toBeVisible();
}

test('assistant speech uses reference controls, transfers ownership and ignores stale completion', async ({ page }) => {
    await fixture(page);
    await expect(page.locator('#post-501 .post-speak-btn')).toHaveCount(0);
    const first = page.locator('#post-502'), second = page.locator('#post-503');
    await first.hover(); await first.getByRole('button', { name: 'Read aloud', exact: true }).click();
    await expect(first.getByRole('button', { name: 'Stop reading aloud', exact: true })).toBeVisible();
    expect(await page.evaluate(() => window.fixtureSpeech.spoken[0].text)).toBe('First message. Readable text.');
    await second.hover(); await second.getByRole('button', { name: 'Read aloud', exact: true }).click();
    await page.evaluate(() => window.fixtureSpeech.spoken[0].onend());
    await expect(second.getByRole('button', { name: 'Stop reading aloud', exact: true })).toBeVisible();
    await expect(first.getByRole('button', { name: 'Read aloud', exact: true })).toHaveCount(1);
    await second.getByRole('button', { name: 'Stop reading aloud', exact: true }).click();
    await expect(second.getByRole('button', { name: 'Read aloud', exact: true })).toBeVisible();
    expect(await page.evaluate(() => window.fixtureSpeech.cancels)).toBe(3);
});

test('unmounting an old same-ID session post cannot stop the newer playback owner', async ({ page }) => {
    await fixture(page);
    // Isolate module lifecycle from the app's body-root reconciliation.
    await page.route('**/speech-lifecycle', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><head></head><body></body></html>' }));
    await page.goto('/speech-lifecycle');
    await page.evaluate(async () => {
        const { html, render } = await import('/static/js/vendor/preact-htm.js');
        const { Timeline } = await import('/static/js/components/timeline.js');
        const hosts = ['a', 'b'].map(session => {
            const host = document.createElement('div'); host.id = 'speech-host-' + session; document.body.appendChild(host);
            render(html`<${Timeline} posts=${[{ id: 900, data: { type: 'agent_response', content: session, session_id: session } }]} />`, host);
            return host;
        });
        window.removeSpeechHost = index => render(null, hosts[index]);
    });
    expect(await page.locator('#speech-host-a').innerHTML()).toContain('post-speak-btn');
    const a = page.locator('#speech-host-a'), b = page.locator('#speech-host-b');
    // These isolated hosts sit outside the app layout; exercise lifecycle directly.
    // Real pointer reachability is covered by the mounted timeline test above.
    await a.locator('.post-speak-btn').evaluate(button => button.click());
    await b.locator('.post-speak-btn').evaluate(button => button.click());
    await page.evaluate(() => window.removeSpeechHost(0));
    await expect(b.locator('.post-speak-btn')).toHaveAttribute('aria-label', 'Stop reading aloud');
    expect(await page.evaluate(() => window.fixtureSpeech.cancels)).toBe(2);
    await page.evaluate(() => window.removeSpeechHost(1));
    await expect.poll(() => page.evaluate(() => window.fixtureSpeech.cancels)).toBe(3);
});

test('unsupported browsers do not offer a nonfunctional speech control', async ({ page }) => {
    await fixture(page, false);
    await expect(page.locator('.post-speak-btn')).toHaveCount(0);
});
