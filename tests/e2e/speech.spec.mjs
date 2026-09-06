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
