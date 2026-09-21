// Native queue markup shared by both hosts; no synthetic controls or CSS.
export async function assertQueueReady(page,state){
 const expected=state.queue.filter(item=>item.sessionKey===state.currentSession).sort((a,b)=>a.position-b.position).map(item=>item.text);
 if(!expected.length)return;
 await page.waitForFunction(texts=>JSON.stringify([...document.querySelectorAll('.compose-queue-stack-text')].map(el=>el.textContent))===JSON.stringify(texts),expected);
 const rows=page.locator('.compose-queue-stack-item');
 if(await rows.count()!==expected.length)throw new Error('Canonical queue count mismatch');
 for(const row of await rows.all()){
  for(const selector of ['.compose-queue-stack-steer-btn','.compose-queue-stack-close-btn'])if(!await row.locator(selector).isVisible())throw new Error('Canonical queue control missing: '+selector);
  // Enabled state is host behavior: retain it for comparison, do not normalize it.
 }
}
