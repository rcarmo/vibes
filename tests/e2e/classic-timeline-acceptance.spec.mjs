import { test, expect } from '@playwright/test';

test.use({ hasTouch: true });

const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z2SMAAAAASUVORK5CYII=', 'base64');
const post = (id, content = 'message', extra = {}) => ({ id, timestamp: '2026-09-15T12:00:00Z', reply_count: 0, data: { type: 'agent_response', content, agent_id: 'default', session_id: 'default', media_ids: [], ...extra } });
async function timeline(page, posts) { await page.route('**/timeline?*', route => route.fulfill({ json: { posts, has_more: false } })); }
async function imagePost(page) {
  await page.route('**/media/7/info', route => route.fulfill({ json: { id: 7, filename: 'pixel.png', content_type: 'image/png', metadata: { width: 1, height: 1 } } }));
  await page.route('**/media/7{,/**}', route => route.fulfill({ body: png, contentType: 'image/png' }));
  await timeline(page, [post(700, '', { media_ids: [7], content_blocks: [{ type: 'image', media_id: 7, name: 'pixel.png' }] })]);
  await page.goto('/'); await page.locator('#post-700 img').click(); await expect(page.locator('.image-modal')).toBeVisible();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

test('@ux-timeline-013 Escape dismisses image lightbox', async ({ page }) => { await imagePost(page); await page.keyboard.press('Escape'); await expect(page.locator('.image-modal')).toHaveCount(0); await expect(page.locator('.timeline')).toBeVisible(); });
test('@ux-timeline-014 non-Escape keys retain image lightbox', async ({ page }) => { await imagePost(page); for (const key of ['Space','Enter','a','ArrowLeft']) { await page.keyboard.press(key); await expect(page.locator('.image-modal')).toBeVisible(); } });
test('@ux-timeline-015 backdrop and image clicks dismiss image lightbox', async ({ page }) => { await imagePost(page); await page.locator('.image-modal img').click(); await expect(page.locator('.image-modal')).toHaveCount(0); await page.locator('#post-700 img').click(); await page.locator('.image-modal').click({ position: { x: 2, y: 2 } }); await expect(page.locator('.image-modal')).toHaveCount(0); });
test('@ux-timeline-016 touch tap dismisses image lightbox', async ({ page }) => { await imagePost(page); await page.locator('.image-modal').tap({ position: { x: 2, y: 2 } }); await expect(page.locator('.image-modal')).toHaveCount(0); });

async function deletionFixture(page, posts, handler) { await timeline(page, posts); await page.route('**/post/*', handler); await page.goto('/'); }
async function clickDelete(page, id) { const row=page.locator(`#post-${id}`); await row.hover(); await row.getByRole('button',{name:'Delete message'}).click(); }

test('@ux-timeline-017 direct deletion removes a message and stays gone after refresh', async ({ page }) => {
 let removed=false; await deletionFixture(page,[post(710)],route=>{removed=true;return route.fulfill({json:{ids:[710]}})}); await clickDelete(page,710); await expect(page.locator('#post-710')).toHaveCount(0); expect(removed).toBe(true); await timeline(page,[]); await page.reload(); await expect(page.locator('#post-710')).toHaveCount(0);
});
test('@ux-timeline-018 backend reply detection confirms and retries cascade', async ({ page }) => {
 const cascade=[]; await deletionFixture(page,[post(720)],route=>{const yes=new URL(route.request().url()).searchParams.get('cascade')==='true';cascade.push(yes);return yes?route.fulfill({json:{ids:[720,721]}}):route.fulfill({status:409,json:{error:'Replies exist'}})}); page.once('dialog',d=>d.accept()); await clickDelete(page,720); await expect.poll(()=>cascade).toEqual([false,true]); await expect(page.locator('#post-720')).toHaveCount(0);
});
test('@ux-timeline-019 cancelling backend cascade preserves message', async ({ page }) => {
 await deletionFixture(page,[post(730)],route=>route.fulfill({status:409,json:{error:'Replies exist'}})); page.once('dialog',d=>d.dismiss()); await clickDelete(page,730); await expect(page.locator('#post-730')).toBeVisible();
});
test('@ux-timeline-020 visible replies show exact cascade prompt', async ({ page }) => {
 const posts=[post(740),...Array.from({length:3},(_,i)=>post(741+i,'reply',{thread_id:740}))]; await deletionFixture(page,posts,route=>route.fulfill({json:{ids:[740,741,742,743]}})); let text=''; page.once('dialog',d=>{text=d.message();d.dismiss()}); await clickDelete(page,740); await expect.poll(()=>text).toBe('Delete this message and its 3 replies?');
});
test('@ux-timeline-021 confirmed cascade removes parent and visible replies together', async ({ page }) => {
 const posts=[post(750),post(751,'reply',{thread_id:750})]; await deletionFixture(page,posts,route=>route.fulfill({json:{ids:[750,751]}})); page.once('dialog',d=>d.accept()); await clickDelete(page,750); await expect(page.locator('#post-750,#post-751')).toHaveCount(0);
});
test('@ux-timeline-022 cancelled cascade preserves parent and replies', async ({ page }) => {
 const posts=[post(760),post(761,'reply',{thread_id:760})]; await deletionFixture(page,posts,route=>route.fulfill({json:{ids:[760,761]}})); page.once('dialog',d=>d.dismiss()); await clickDelete(page,760); await expect(page.locator('#post-760,#post-761')).toHaveCount(2);
});

test('@ux-timeline-023 markdown tables span the post with automatic layout', async ({ page }) => {
 await timeline(page,[post(770,'| A | B |\n|---|---|\n| 1 | 2 |')]); await page.goto('/'); const table=page.locator('#post-770 table'); await expect(table).toBeVisible(); await expect(table).toHaveCSS('display','table'); await expect(table).toHaveCSS('table-layout','auto'); const [tableBox,bodyBox]=await Promise.all([table.boundingBox(),page.locator('#post-770 .post-body').boundingBox()]); expect(tableBox.width).toBeGreaterThan(bodyBox.width*.9);
});
test('@ux-timeline-024 code copy control occupies the top-right and copies source', async ({ page }) => {
 await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>window.__copied=text}})); await timeline(page,[post(771,'```js\nconst answer = 42;\n```')]); await page.goto('/'); const pre=page.locator('#post-771 pre'),copy=page.locator('#post-771 .post-code-copy-btn'); await pre.hover(); await expect(copy).toBeVisible(); const [pb,cb]=await Promise.all([pre.boundingBox(),copy.boundingBox()]); expect(cb.x+cb.width).toBeGreaterThan(pb.x+pb.width-20); expect(cb.y).toBeLessThan(pb.y+20); await copy.click(); expect(await page.evaluate(()=>window.__copied)).toBe('const answer = 42;\n');
});
test('@ux-timeline-025 resource links and previews use isolated new tabs', async ({ page }) => {
 await timeline(page,[post(772,'',{content_blocks:[{type:'resource_link',uri:'https://example.com/a',title:'Resource'}],link_previews:[{url:'https://example.com/b',title:'Preview',site_name:'Example'}]})]); await page.goto('/'); for(const link of await page.locator('#post-772 a.resource-link,#post-772 a.link-preview').all()){await expect(link).toHaveAttribute('target','_blank');await expect(link).toHaveAttribute('rel','noopener noreferrer');}
});
test('@ux-timeline-026 outcome chip follows the timestamp in post metadata', async ({ page }) => {
 const marker={type:'turn_outcome_marker',severity:'warning',label:'tool budget',detail:'Budget reached',next_action:'Continue manually'}; await timeline(page,[post(777,'Finished',{content_blocks:[{type:'text',text:'Finished'},marker]})]); await page.goto('/'); const meta=page.locator('#post-777 .post-meta'); const time=meta.locator('.post-time'),chip=meta.locator('.post-outcome-chip'); await expect(chip).toHaveText('tool budget'); expect(await time.evaluate((a,b)=>a.compareDocumentPosition(b)&Node.DOCUMENT_POSITION_FOLLOWING,await chip.elementHandle())).toBeTruthy(); await chip.click(); await expect(page.locator('#post-777 .post-outcome-pill-detail')).toContainText('Budget reached');
});

test('@ux-timeline-027 read aloud is gated by support and speakable content', async ({ page }) => {
 await page.addInitScript(()=>{window.speechSynthesis={cancel(){},speak(){}};window.SpeechSynthesisUtterance=function(t){this.text=t}}); await timeline(page,[post(773,'Readable'),post(774,'')]); await page.goto('/'); await page.locator('#post-773').hover(); await expect(page.locator('#post-773').getByRole('button',{name:'Read aloud'})).toBeVisible(); await expect(page.locator('#post-774 .post-speak-btn')).toHaveCount(0);
});
test('@ux-timeline-028 read aloud transfers playback ownership', async ({ page }) => {
 await page.addInitScript(()=>{window.__speech={cancel:0,spoken:[]};Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{cancel(){window.__speech.cancel++},speak(u){window.__speech.spoken.push(u)}}});window.SpeechSynthesisUtterance=class{constructor(t){this.text=t}}}); await timeline(page,[post(775,'First'),post(776,'Second')]); await page.goto('/'); for(const id of[775,776]){const row=page.locator(`#post-${id}`);await row.hover();await row.getByRole('button',{name:'Read aloud'}).click();} expect(await page.evaluate(()=>window.__speech.cancel)).toBeGreaterThanOrEqual(2); await expect(page.locator('#post-775').getByRole('button',{name:'Read aloud'})).toBeVisible(); await expect(page.locator('#post-776').getByRole('button',{name:'Stop reading aloud'})).toBeVisible();
});
