import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        window.SpeechRecognition = class {
            constructor() { window.recognition = this; }
            start() { this.onstart?.(); }
            stop() { this.stopped = true; this.onend?.(); }
            abort() { this.aborted = true; }
        };
    });
});

test('speech button transcribes and permission failure is visible', async ({ page }) => {
    await page.goto('/');
    const input = page.locator('.compose-input-main textarea');
    await input.fill('Existing');
    await page.getByRole('button', { name: 'Start speech input' }).click();
    await expect(page.locator('.compose-speech-status')).toContainText('Listening');
    await page.evaluate(() => window.recognition.onresult({ results: [[{ transcript: 'hello' }]] }));
    await expect(input).toHaveValue('Existing hello');
    await page.evaluate(() => window.recognition.onerror({ error: 'not-allowed' }));
    await expect(page.locator('.compose-speech-status')).toContainText('Microphone permission denied');
    expect(await page.evaluate(() => window.recognition.aborted)).toBe(true);
});

test('Space push-to-talk stops on release and blur aborts recognition', async ({ page }) => {
    await page.goto('/');
    const input = page.locator('.compose-input-main textarea');
    await input.focus();
    await page.keyboard.down('Space');
    await expect(page.locator('.compose-speech-status')).toContainText('Listening');
    await page.keyboard.up('Space');
    await expect(page.locator('.compose-speech-status')).toHaveCount(0);
    expect(await page.evaluate(() => window.recognition.stopped)).toBe(true);
    await expect(input).toHaveValue('');
    await page.getByRole('button', { name: 'Start speech input' }).click();
    await page.evaluate(() => window.dispatchEvent(new Event('blur')));
    await expect(page.locator('.compose-speech-status')).toHaveCount(0);
    expect(await page.evaluate(() => window.recognition.aborted)).toBe(true);
});

test('touch hold releases without restarting from compatibility click', async ({ page }) => {
    await page.goto('/');
    const button = page.locator('.compose-mic-btn');
    // Synthetic pointer events cannot own capture; exercise handlers without capture.
    await button.evaluate(el => { el.setPointerCapture = () => {}; });
    await button.dispatchEvent('pointerdown', { pointerType: 'touch', pointerId: 7, isPrimary: true, button: 0 });
    await expect(page.locator('.compose-speech-status')).toContainText('Listening');
    await button.dispatchEvent('pointerup', { pointerType: 'touch', pointerId: 7, isPrimary: true, button: 0 });
    await button.dispatchEvent('click', { detail: 1 });
    await expect(page.locator('.compose-speech-status')).toHaveCount(0);
    expect(await page.evaluate(() => window.recognition.stopped)).toBe(true);
    await button.dispatchEvent('click', { detail: 0 });
    await expect(page.locator('.compose-speech-status')).toContainText('Listening');
});

test('touch cancellation aborts and unsupported browsers hide speech', async ({ page }) => {
    await page.goto('/');
    const button = page.locator('.compose-mic-btn');
    await button.evaluate(el => { el.setPointerCapture = () => {}; });
    await button.dispatchEvent('pointerdown', { pointerType: 'pen', pointerId: 9, isPrimary: true, button: 0 });
    await expect(page.locator('.compose-speech-status')).toContainText('Listening');
    await button.dispatchEvent('pointercancel', { pointerType: 'pen', pointerId: 9 });
    expect(await page.evaluate(() => window.recognition.aborted)).toBe(true);
    await expect(page.locator('.compose-speech-status')).toHaveCount(0);
    await page.addInitScript(() => { window.SpeechRecognition = undefined; window.webkitSpeechRecognition = undefined; });
    await page.reload();
    await expect(page.locator('.compose-input-main textarea')).toBeVisible();
    await expect(button).toHaveCount(0);
});

test('session switch aborts speech and late transcripts cannot overwrite the new draft', async ({ page }) => {
    await page.goto('/');
    const created = await page.request.post('/sessions', { data: { name: 'Speech isolation' } });
    const id = (await created.json()).session.id;
    const input = page.locator('.compose-input-main textarea');
    await input.fill('Old draft');
    await page.getByRole('button', { name: 'Start speech input' }).click();
    await page.evaluate(() => { window.oldRecognition = window.recognition; window.lateResult = window.recognition.onresult; });
    await page.getByTestId('session-switcher').click();
    await page.locator('#session-option-' + id).click();
    await expect(input).toHaveValue('');
    await expect(page.locator('.compose-speech-status')).toHaveCount(0);
    expect(await page.evaluate(() => window.oldRecognition.aborted)).toBe(true);
    await input.fill('New draft');
    await page.evaluate(() => window.lateResult({ results: [[{ transcript: 'late old speech' }]] }));
    await expect(input).toHaveValue('New draft');
});

test('manual edit aborts recognition and protects edited text from late results', async ({ page }) => {
    await page.goto('/');
    const input = page.locator('.compose-input-main textarea');
    await page.getByRole('button', { name: 'Start speech input' }).click();
    await page.evaluate(() => { window.lateResult = window.recognition.onresult; });
    await input.fill('Typed instead');
    expect(await page.evaluate(() => window.recognition.aborted)).toBe(true);
    await page.evaluate(() => window.lateResult({ results: [[{ transcript: 'late speech' }]] }));
    await expect(input).toHaveValue('Typed instead');
    await expect(page.locator('.compose-speech-status')).toHaveCount(0);
});

test('releasing Space during permission wait stops delayed recognition start', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => {
        window.SpeechRecognition.prototype.start = function () {};
        window.SpeechRecognition.prototype.stop = function () {
            if (!this.ready) throw new Error('not started');
            this.stopped = true; this.onend?.();
        };
    });
    await page.locator('.compose-input-main textarea').focus();
    await page.keyboard.down('Space');
    await expect(page.locator('.compose-speech-status')).toContainText('Requesting microphone permission');
    await page.keyboard.up('Space');
    await page.evaluate(() => { window.recognition.ready = true; window.recognition.onstart(); });
    await expect(page.locator('.compose-speech-status')).toHaveCount(0);
    expect(await page.evaluate(() => window.recognition.stopped)).toBe(true);
});

test('hidden page aborts speech and invalidates delayed transcript', async ({ page }) => {
    await page.goto('/');
    const input = page.locator('.compose-input-main textarea');
    await input.fill('Keep draft');
    await page.getByRole('button', { name: 'Start speech input' }).click();
    await page.evaluate(() => {
        const late = window.recognition.onresult;
        Object.defineProperty(document, 'hidden', { configurable: true, value: true });
        document.dispatchEvent(new Event('visibilitychange'));
        late({ results: [[{ transcript: 'background speech' }]] });
    });
    expect(await page.evaluate(() => window.recognition.aborted)).toBe(true);
    await expect(input).toHaveValue('Keep draft');
    await expect(page.locator('.compose-speech-status')).toHaveCount(0);
});
