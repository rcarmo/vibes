import {test,expect} from '@playwright/test';

test('workspace menu pointer and Escape flows preserve composer and restore focus',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('workspaceOpen','false'));
 await page.goto('/');
 const input=page.locator('.compose-box textarea');await input.fill('unsent shell draft');
 const trigger=page.getByTestId('hamburger');await trigger.click();
 await expect(trigger).toHaveAttribute('aria-expanded','true');
 await expect(page.getByRole('menu')).toBeVisible();
 await page.keyboard.press('Escape');
 await expect(page.getByRole('menu')).toHaveCount(0);await expect(trigger).toBeFocused();
 await trigger.click();await page.getByRole('menuitem',{name:'Show workspace',exact:true}).click();
 await expect(page.locator('.workspace-sidebar')).toBeVisible();await expect(page.getByRole('menu')).toHaveCount(0);
 await trigger.click();await page.getByRole('menuitem',{name:'Hide workspace',exact:true}).click();
 await expect(page.locator('.app-shell')).toHaveClass(/workspace-collapsed/);
 await expect(input).toHaveValue('unsent shell draft');
});

test('outside pointer dismissal does not activate content underneath',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('workspaceOpen','false'));
 await page.goto('/');const trigger=page.getByTestId('hamburger');await trigger.click();
 const input=page.locator('.compose-box textarea');await input.click();
 await expect(page.getByRole('menu')).toHaveCount(0);await expect(input).toBeFocused();
 await expect(input).toHaveValue('');
});

test('keyboard opens menu once and exposes only implemented capabilities',async({page})=>{
 await page.addInitScript(()=>localStorage.setItem('workspaceOpen','false'));
 await page.goto('/');const trigger=page.getByTestId('hamburger');await trigger.focus();await page.keyboard.press('Enter');
 await expect(page.getByRole('menu')).toHaveCount(1);
 for(const label of ['Show workspace','Open explorer','Quick actions','Open terminal'])await expect(page.getByRole('menuitem',{name:label,exact:true})).toHaveCount(label==='Open terminal'?1:1);
 await expect(page.getByRole('menuitem',{name:'Settings',exact:true})).toHaveCount(0);
 await page.keyboard.press('Escape');await expect(trigger).toBeFocused();
});

test('mobile workspace backdrop closes drawer without activating Plan or chat',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.addInitScript(()=>localStorage.setItem('workspaceOpen','false'));await page.goto('/');
 await page.getByTestId('hamburger').click();await page.getByRole('menuitem',{name:'Show workspace',exact:true}).click();
 await expect(page.locator('.workspace-drawer-backdrop')).toBeVisible();
 await page.locator('.workspace-drawer-backdrop').click({position:{x:380,y:200}});
 await expect(page.locator('.app-shell')).toHaveClass(/workspace-collapsed/);
 await expect(page.locator('.plan-sidebar-root')).not.toHaveClass(/open/);
 await expect(page.locator('.compose-box textarea')).not.toBeFocused();
});
