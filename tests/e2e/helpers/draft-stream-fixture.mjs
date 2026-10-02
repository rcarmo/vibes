// Reusable browser regression: only browser-local SSE and intercepted APIs.
export async function verifyDraftStream(page, expect, url = '/') {
    let snapshot = '';
    await page.addInitScript(() => {
        window.EventSource = class {
            constructor() { this.listeners = new Map(); this.readyState = 1; window.draftFixtureStream = this; }
            addEventListener(type, fn) { this.listeners.set(type, fn); }
            close() {}
        };
        window.emitDraftFixture = (type, data) => window.draftFixtureStream.listeners.get(type)?.({ data: JSON.stringify({ session_id: 'default', turn_id: 'synthetic-draft', ...data }) });
    });
    await page.route('**/agents/status?*', route => route.fulfill({ json: { busy:false,active_turns:[],pending_requests:[],pending_steers:[],queued_followups:[] } }));
    await page.route('**/agent/turn/**', route => route.fulfill({ json: route.request().method() === 'POST' ? {status:'ok'} : {draft:snapshot,draft_total_lines:snapshot.split('\n').length} }));
    await page.goto(url);
    await expect(page.locator('.compose-box textarea')).toBeVisible();
    const emit = (type, data) => page.evaluate(({type,data}) => window.emitDraftFixture(type,data), {type,data});
    await emit('agent_status', {type:'thinking',title:'Synthetic stream'});
    const panel = page.locator('[data-panel-key="draft"]');
    const body = panel.locator('.agent-thinking-body');
    let sentence = '';
    for (const chunk of ['This ', 'is ', 'a ', 'complete ', 'draft.']) {
        sentence += chunk;
        await emit('agent_draft', {text:chunk,mode:'append',kind:'draft'});
        await expect(body).toHaveText(sentence.trim());
    }
    // Pi's complete preview replaces the previous text; it must not append twice.
    snapshot = Array.from({length:12}, (_,i) => `Line ${i+1}`).join('\n');
    await emit('agent_draft', {text:snapshot,mode:'replace',kind:'draft',total_lines:12});
    await panel.getByTitle('Show more Draft', {exact:true}).click();
    await expect(panel).toHaveAttribute('data-expanded','true');
    await expect(body).toContainText('Line 1');
    // Both event streams arrive when expanded; only the delta is consumed.
    await emit('agent_draft', {text:'\nExpanded suffix',mode:'append',kind:'draft'});
    await emit('agent_draft_delta', {delta:'\nExpanded suffix'});
    await expect(body).toContainText('Expanded suffix');
    expect((await body.innerText()).match(/Expanded suffix/g)).toHaveLength(1);
    await panel.getByTitle('Show fewer Draft lines', {exact:true}).click();
    await expect(panel).toHaveAttribute('data-expanded','false');
    await emit('agent_draft', {text:' then collapsed',mode:'append',kind:'draft'});
    await expect(body).toContainText('Expanded suffix then collapsed');
    await emit('agent_draft_delta', {delta:' must be ignored'});
    await expect(body).not.toContainText('must be ignored');
    // Reject unrelated turn content without destroying the accumulated text.
    await emit('agent_draft', {turn_id:'stale-turn',text:'wrong',mode:'replace'});
    await expect(body).toContainText('Expanded suffix then collapsed');
}
