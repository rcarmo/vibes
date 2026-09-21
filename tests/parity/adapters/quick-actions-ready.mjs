export async function assertQuickActionsReady(page,state){
 if(state.ui.popup!=='quick-actions')return;
 const active=await page.evaluate(()=>{const el=document.activeElement;return el?.tagName||'';});
 if(['INPUT','TEXTAREA','SELECT'].includes(active))await page.evaluate(()=>document.activeElement?.blur());
 await page.locator('.timeline').click({position:{x:8,y:8}});
 await page.keyboard.press('r');
 const popup=page.locator('.timeline-quick-actions');
 await popup.waitFor({state:'visible',timeout:5000});
 const input=popup.locator('.timeline-quick-actions-input');
 await input.waitFor({state:'visible'});
 if(await input.inputValue()!=='r')throw new Error('Quick-actions initial query mismatch');
}
