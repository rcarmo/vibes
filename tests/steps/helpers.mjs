/**
 * Shared helpers for all Playwright BDD step definitions.
 */
export const BASE_URL = process.env.VIBES_TEST_URL || 'http://127.0.0.1:8765';

export async function waitForConnection(page, timeout = 15000) {
    await page.waitForFunction(() => {
        const textarea = document.querySelector('.compose-box textarea');
        return textarea && !textarea.disabled;
    }, { timeout });
}

export async function sendMessage(page, message) {
    const textarea = page.locator('.compose-box textarea');
    await textarea.fill(message);
    await textarea.press('Enter');
}

export async function waitForAgentResponse(page, timeout = 90000) {
    const agentPost = page.locator('.post.agent-post .post-content').last();
    await agentPost.waitFor({ state: 'visible', timeout });
    return agentPost;
}

export async function waitForAgentIdle(page, timeout = 90000) {
    await page.waitForFunction(() => {
        const spinner = document.querySelector('.agent-status-spinner');
        return !spinner || spinner.offsetParent === null;
    }, { timeout });
}
