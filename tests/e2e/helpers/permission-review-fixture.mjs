// Browser-local fixture: no real tool request is accepted or denied.
export const reviewCommand = '$source = "C:\\Preview\\input files\\report.json"\n' +
    '$destination = "C:\\Preview\\output\\' + 'long-directory-name-'.repeat(18) + 'report.txt"\n' +
    'Get-Content -LiteralPath $source | ConvertFrom-Json | ForEach-Object { $_.title } | Set-Content -LiteralPath $destination\n' +
    Array.from({length:12},(_,i)=>`Write-Output "Review step ${i+1}: ${'detail '.repeat(14)}"`).join('\n');

export async function mountPermissionReview(page, url='/') {
    await page.addInitScript(()=>{window.EventSource=class {addEventListener(){} close(){}};});
    await page.route('**/agents/status?*',route=>route.fulfill({json:{busy:false,active_turns:[],pending_requests:[],queued_followups:[],pending_steers:[]}}));
    await page.goto(url,{waitUntil:'networkidle'});
    await page.evaluate(async(command)=>{
        const {html,render}=await import('/static/js/vendor/preact-htm.js');
        const {AgentRequestModal}=await import('/static/js/components/status.js');
        const root=document.querySelector('#app'); if(root)render(null,root);
        const fixture=document.createElement('div');fixture.id='permission-review-fixture';document.body.append(fixture);
        window.fixtureAnswers=[];
        // Exercise the actual HTTP/LAN copy fallback, recording exact selected text.
        Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});
        document.execCommand=(action)=>{if(action==='copy'){window.copiedPermissionText=document.activeElement.value;return true;}return false;};
        const raw={kind:'shell',fullCommandText:command,intention:'Read a local report and write a formatted copy.',
            resolvedWorkingDirectory:'C:\\Preview',possiblePaths:['C:\\Preview\\input files\\report.json'],
            hasWriteFileRedirection:true,warning:'Review the destination before allowing this command.'};
        window.renderPermissionReview=(request)=>render(html`<${AgentRequestModal} request=${request} onRespond=${id=>window.fixtureAnswers.push(id)} />`,fixture);
        window.reviewRequest={request_id:'fixture-only',tool_call:{title:'Copilot tool permission',rawInput:raw},options:[
            {optionId:'allow',name:'Allow once',kind:'allow_once'},{optionId:'deny',name:'Deny',kind:'reject_once'}]};
        window.renderPermissionReview(window.reviewRequest);
    },reviewCommand);
}

export async function verifyPermissionLayout(page, expect) {
    const dialog=page.locator('#permission-review-fixture [role="dialog"]');
    await expect(dialog).toHaveAccessibleName('Run command');
    await expect(dialog).toBeFocused();
    const command=dialog.getByTestId('permission-command');
    expect(await command.textContent()).toBe(reviewCommand);
    const layout=await dialog.evaluate(el=>{
        const body=el.querySelector('.agent-request-body'),command=el.querySelector('[data-testid="permission-command"]');
        const footer=el.querySelector('.agent-request-footer'),box=el.getBoundingClientRect(),foot=footer.getBoundingClientRect();
        return {width:box.width,left:box.left,right:box.right,top:box.top,bottom:box.bottom,viewportWidth:innerWidth,viewportHeight:innerHeight,
            bodyClient:body.clientWidth,bodyScroll:body.scrollWidth,bodyScrolls:body.scrollHeight>body.clientHeight,
            commandClient:command.clientWidth,commandScroll:command.scrollWidth,wrap:getComputedStyle(command).whiteSpace,
            footerTop:foot.top,footerBottom:foot.bottom};
    });
    const badge = await dialog.locator('.agent-request-icon').evaluate(el => {
        const rgb = value => value.match(/[\d.]+/g).slice(0,3).map(Number);
        const luminance = color => rgb(color).map(v => { const n=v/255; return n<=.04045 ? n/12.92 : ((n+.055)/1.055)**2.4; }).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
        const background=getComputedStyle(el).backgroundColor, stroke=getComputedStyle(el.querySelector('path')).stroke;
        const a=luminance(background), b=luminance(stroke);
        return {stroke, background, contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
    });
    expect(badge.contrast).toBeGreaterThanOrEqual(3);
    expect(layout.wrap).toBe('pre-wrap');
    expect(layout.commandScroll).toBeLessThanOrEqual(layout.commandClient+1);
    expect(layout.bodyScroll).toBeLessThanOrEqual(layout.bodyClient+1);
    expect(layout.left).toBeGreaterThanOrEqual(0);expect(layout.right).toBeLessThanOrEqual(layout.viewportWidth);
    expect(layout.top).toBeGreaterThanOrEqual(0);expect(layout.bottom).toBeLessThanOrEqual(layout.viewportHeight);
    expect(layout.bodyScrolls).toBe(true);
    expect(layout.footerBottom).toBeLessThanOrEqual(layout.viewportHeight);
    expect(await dialog.locator('.permission-actions button').allTextContents()).toEqual(['Deny','Allow once']);
    for(const name of ['Deny','Allow once'])await expect(dialog.getByRole('button',{name,exact:true})).toBeInViewport();
    await dialog.getByRole('button',{name:'Copy command'}).click();
    await expect(dialog.getByRole('status')).toHaveText('Copied');
    expect(await page.evaluate(()=>window.copiedPermissionText)).toBe(reviewCommand);
    await dialog.getByRole('button',{name:'Allow once'}).focus();
    await page.keyboard.press('Tab');
    await expect(dialog.locator('.agent-request-body')).toBeFocused();
    await page.keyboard.press('Shift+Tab');
    await expect(dialog.getByRole('button',{name:'Allow once'})).toBeFocused();
    await dialog.locator('.agent-request-technical summary').click();
    expect(await dialog.locator('.agent-request-technical pre').evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    await dialog.locator('.agent-request-body').evaluate(el=>el.scrollTop=el.scrollHeight);
    for(const name of ['Deny','Allow once'])await expect(dialog.getByRole('button',{name,exact:true})).toBeInViewport();
    expect(await page.evaluate(()=>window.fixtureAnswers)).toEqual([]);
    return {...layout,badge};
}
