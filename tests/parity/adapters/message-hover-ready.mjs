export async function assertMessageHoverReady(page, state) {
  if (!state.ui.hoverMessageId) return;
  const post = page.locator(`#post-${state.ui.hoverMessageId}`);
  await post.waitFor({ state: 'visible' });
  await post.hover();
  await page.waitForFunction(id => document.querySelector(`#post-${id}:hover`) !== null, state.ui.hoverMessageId);
}
