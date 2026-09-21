export async function assertModelPickerReady(page,state){
 if(state.ui.popup!=='models')return;
 await page.getByRole('button',{name:'Open model picker',exact:true}).click();
 const popup=page.locator('.compose-model-catalogue');
 await popup.waitFor({state:'visible'});
 await page.getByRole('combobox',{name:/Search models/i}).waitFor({state:'visible'});
 const expected=`${state.model.provider}/${state.model.id}`;
 await page.waitForFunction(label=>document.querySelector('.compose-model-catalogue')?.textContent.includes(label),expected);
}
