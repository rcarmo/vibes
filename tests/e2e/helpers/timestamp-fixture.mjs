// Check real timeline rendering with SQLite-shaped UTC and a controlled clock.
export async function verifyTimestampUi(page, expect, url='/') {
    await page.clock.install({time:new Date('2026-10-02T15:19:03Z')});
    await page.addInitScript(()=>{window.EventSource=class { addEventListener(){} close(){} };});
    const post=(id,timestamp)=>({id,timestamp,data:{type:'user_message',content:'Timestamp fixture',session_id:'default'}});
    await page.route('**/timeline?*',route=>route.fulfill({json:{posts:[
        post(99001,'2026-10-02 15:15:48'),post(99002,'2026-10-02 15:18:40'),
    ],has_more:false}}));
    await page.route('**/agents/status?*',route=>route.fulfill({json:{busy:false,active_turns:[],pending_requests:[],queued_followups:[],pending_steers:[]}}));
    await page.goto(url);
    await expect(page.locator('#post-99001 .post-time')).toHaveText('3m');
    await expect(page.locator('#post-99002 .post-time')).toHaveText('just now');
    const expectedTitle=await page.evaluate(()=>new Date('2026-10-02T15:15:48Z').toLocaleString());
    await expect(page.locator('#post-99001 .post-time')).toHaveAttribute('title',expectedTitle);
    await page.clock.runFor(65000);
    await expect(page.locator('#post-99001 .post-time')).toHaveText('4m');
    await expect(page.locator('#post-99002 .post-time')).toHaveText('1m');
}
