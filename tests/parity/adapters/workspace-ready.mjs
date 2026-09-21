export async function assertWorkspaceReady(page,state){
 if(!state.ui.workspaceOpen)return;
 const tree=page.locator('.workspace-tree');
 if(!await tree.isVisible()){
  await page.getByTestId('hamburger').click();
  await page.getByRole('menuitem',{name:'Show workspace',exact:true}).click();
 }
 await tree.waitFor({state:'visible'});
 const toggle=page.getByRole('button',{name:'Hide workspace',exact:true});
 await toggle.waitFor({state:'visible'});
 if(await toggle.getAttribute('aria-expanded')!=='true')throw new Error('Canonical workspace toggle is not expanded');
 await page.waitForFunction(names=>names.every(name=>document.querySelector('.workspace-tree')?.textContent.includes(name)),state.workspace.entries.map(entry=>entry.name));
 const text=await tree.innerText();
 for(const entry of state.workspace.entries)if(!text.includes(entry.name))throw new Error(`Canonical workspace missing entry ${entry.name}; tree=${JSON.stringify(text)}`);
 const backdrop=page.locator('.workspace-drawer-backdrop');
 if(await backdrop.count()&&!await backdrop.isVisible())throw new Error('Canonical workspace backdrop is not visible');
}
