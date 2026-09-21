import {mkdir,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {snapshotAssets,verifyAssets} from './assets.mjs';

/** Adapter callbacks own native routes/state and semantic readiness.
 * No product CSS is copied or normalized by this primitive.
 */
export async function captureCase({browser,adapter,state,viewport,theme,outDir,repeat}) {
  if(!Number.isInteger(repeat)||repeat<1)throw new Error('Explicit repeat number required');
  if(!adapter.assets||!adapter.install||!adapter.ready||!adapter.assertRequests)throw new Error('Incomplete capture adapter');
  await mkdir(outDir,{recursive:true});
  const assets=await snapshotAssets(adapter.assets);
  const context=await browser.newContext({viewport,colorScheme:theme,locale:'en-US',timezoneId:'UTC',deviceScaleFactor:1,reducedMotion:'reduce',serviceWorkers:'block'});
  const page=await context.newPage();
  const errors=[],networkFailures=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('requestfailed',request=>networkFailures.push({url:request.url(),error:request.failure()?.errorText}));
  const report={adapter:adapter.name,repeat,viewport,theme,assets,errors,networkFailures,passed:false};
  let installed;
  try {
    await page.clock.setFixedTime(new Date('2026-01-01T12:00:00Z'));
    installed=await adapter.install({page,context,state,theme,viewport});
    await page.goto(installed.url,{waitUntil:'domcontentloaded'});
    await adapter.ready({page,state});
    await page.bringToFront();
    report.focusBeforeCapture=await page.evaluate(()=>({tag:document.activeElement?.tagName,className:document.activeElement?.className}));
    if(!state.ui?.preserveFocus){
      await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur();});
    }
    if(!state.ui?.hoverMessageId)await page.mouse.move(1,1);
    await page.evaluate(()=>document.fonts.ready);
    await page.evaluate(async()=>{
      const images=[...document.images];
      await Promise.all(images.map(async image=>{
        if(!image.currentSrc&&!image.src)return;
        await image.decode();
        if(!image.naturalWidth)throw new Error(`Image failed to decode: ${image.currentSrc||image.src}`);
      }));
    });
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    // Headed Chromium can expose a document before its compositor surface exists.
    await page.waitForTimeout(500);
    // Addons may schedule focus after mount; settle first, then normalize again.
    if(!state.ui?.preserveFocus){
      await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur();});
      await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
    }
    if(state.ui?.hoverMessageId){
      const post=page.locator(`#post-${state.ui.hoverMessageId}`);await post.hover();
      await page.waitForFunction(id=>document.querySelector(`#post-${id}:hover`)!==null,state.ui.hoverMessageId);
    }
    // Normalize native animation phase without injecting styles or hiding pixels.
    await page.evaluate(()=>{for(const animation of document.getAnimations()){try{animation.currentTime=0;animation.pause();}catch{}}});
    await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(resolve)));
    if(state.ui?.popup==='sessions'&&!await page.locator('.compose-session-popup').isVisible())throw new Error('Canonical session picker closed before screenshot');
    report.focusAtScreenshot=await page.evaluate(()=>({tag:document.activeElement?.tagName,className:document.activeElement?.className}));
    await adapter.assertRequests();
    if(errors.length||networkFailures.length)throw new Error('Browser errors or failed requests');
    await verifyAssets(assets);
    report.rendered=await page.evaluate(({hoverMessageId})=>({
      text:document.body.innerText,
       pointProbe:[...Array(4)].map((_,index)=>{const el=document.elementFromPoint(745+index,1077);if(!el)return null;const s=getComputedStyle(el),r=el.getBoundingClientRect();return{tag:el.tagName,className:el.className,html:el.outerHTML,x:r.x,y:r.y,width:r.width,height:r.height,color:s.color,background:s.backgroundColor,opacity:s.opacity,font:s.font,pseudos:['::before','::after'].map(p=>{const q=getComputedStyle(el,p);return{pseudo:p,content:q.content,width:q.width,height:q.height,color:q.color,border:q.border,transform:q.transform,opacity:q.opacity}})};}),
      metersHTML:document.querySelector('.system-meters-card')?.outerHTML,
      meterGraphics:[...document.querySelectorAll('.system-meters-card svg, .system-meters-card path, .system-meters-card polyline')].map(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{tag:el.tagName,outerHTML:el.outerHTML,x:r.x,y:r.y,width:r.width,height:r.height,stroke:s.stroke,fill:s.fill,opacity:s.opacity};}),
      quickActions:[...document.querySelectorAll('.timeline-quick-actions,.timeline-quick-actions-header,.timeline-quick-actions-input,.timeline-quick-actions-list,.timeline-quick-actions-item,.timeline-quick-actions-keyhint,.timeline-quick-actions-keyhint kbd,.timeline-quick-actions-section-label,.timeline-quick-actions-item-placeholder,.timeline-quick-actions-item-title,.timeline-quick-actions-item-action-hint,.timeline-quick-actions-item-subtitle,.timeline-quick-actions-item-category')].map(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{className:el.className,text:el.textContent,x:r.x,y:r.y,width:r.width,height:r.height,padding:s.padding,background:s.backgroundColor,border:s.border,color:s.color,font:s.font,letterSpacing:s.letterSpacing,textTransform:s.textTransform,opacity:s.opacity};}),
      statusHTML:document.querySelector('.agent-status-panel')?.outerHTML,
      status:[...document.querySelectorAll('.agent-status-panel,.agent-status,.agent-status-spinner,.agent-status-text')].map(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{className:el.className,text:el.textContent,x:r.x,y:r.y,width:r.width,height:r.height,padding:s.padding,margin:s.margin,background:s.backgroundColor,border:s.border,color:s.color,font:s.font};}),
      workspaceControls:[...document.querySelectorAll('.workspace-menu-button,.workspace-create,.workspace-refresh,[data-testid="hamburger"]')].map(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{className:el.className,title:el.title,disabled:el.disabled,expanded:el.getAttribute('aria-expanded'),x:r.x,y:r.y,width:r.width,height:r.height,opacity:s.opacity,color:s.color,background:s.backgroundColor};}),
      workspaceHTML:document.querySelector('.workspace-sidebar')?.outerHTML,
      workspace:[...document.querySelectorAll('.workspace-sidebar,.workspace-header,.workspace-tree,.workspace-tree-list,.workspace-drawer-backdrop')].map(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{className:el.className,text:el.textContent,x:r.x,y:r.y,width:r.width,height:r.height,padding:s.padding,background:s.backgroundColor,border:s.border};}),
      pickerHTML:document.querySelector('.compose-session-popup')?.outerHTML,
      modelPickerHTML:document.querySelector('.compose-model-catalogue')?.outerHTML,
      modelPicker:[...document.querySelectorAll('.compose-model-catalogue,.compose-model-catalogue-header,.compose-model-catalogue-search,.compose-model-catalogue-results,.compose-model-catalogue-option,.compose-session-row-pin,.compose-model-catalogue-badge,.compose-model-catalogue-footer')].map(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{className:el.className,text:el.textContent,x:r.x,y:r.y,width:r.width,height:r.height,padding:s.padding,background:s.backgroundColor,border:s.border};}),
      picker:[...document.querySelectorAll('.compose-session-popup, .compose-session-popup-header, .compose-session-search, .session-picker-row, .compose-session-popup .compose-model-popup-item-row, .compose-session-popup .session-item, .compose-session-row-pin, .compose-model-popup-item-popout, .compose-model-popup-item-delete, .session-row-action, .compose-model-popup-actions')].map(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);return {className:el.className,text:el.textContent,x:r.x,y:r.y,width:r.width,height:r.height,font:s.font,padding:s.padding};}),
      composer:document.querySelector('.compose-meta-row')?.outerHTML,
      hoveredPost:(()=>{const el=document.querySelector(`#post-${hoverMessageId}`);if(!el)return null;const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{html:el.outerHTML,x:r.x,y:r.y,width:r.width,height:r.height,background:s.backgroundColor,opacity:s.opacity,boxShadow:s.boxShadow};})(),
      avatars:[...document.querySelectorAll('.post-avatar')].map(el=>{const s=getComputedStyle(el),r=el.getBoundingClientRect();const image=el.querySelector('img');return {html:el.outerHTML,x:r.x,y:r.y,width:r.width,height:r.height,background:s.backgroundColor,borderRadius:s.borderRadius,overflow:s.overflow,image:image?{width:getComputedStyle(image).width,height:getComputedStyle(image).height,objectFit:getComputedStyle(image).objectFit,borderRadius:getComputedStyle(image).borderRadius}:null};}),
      elements:Object.fromEntries(['.compose-box','.compose-box textarea','.compose-context-pie','.compose-model-meta','.timeline','.plan-sidebar-panel','.plan-sidebar-header','.plan-sidebar-progress','.plan-sidebar-editor','.plan-sidebar-footer','.system-meters-card','[data-testid="session-switcher"]','.compose-queue-stack','.compose-queue-stack-item','.compose-queue-stack-content','.compose-queue-stack-actions','.workspace-row','.workspace-row[data-path="README.md"]','.workspace-header-actions','.workspace-sidebar','.workspace-header > span','.workspace-header-left > span'].map(selector=>{
        const el=document.querySelector(selector);if(!el)return [selector,null];
        const r=el.getBoundingClientRect(),style=getComputedStyle(el);
        return [selector,{x:r.x,y:r.y,width:r.width,height:r.height,font:style.font,color:style.color,background:style.backgroundColor,opacity:style.opacity,padding:style.padding,border:style.border,boxSizing:style.boxSizing,position:style.position,zIndex:style.zIndex,boxShadow:style.boxShadow,transform:style.transform}];
      })),
    }),{hoverMessageId:state.ui?.hoverMessageId});
    await page.screenshot({path:join(outDir,'original.png'),animations:'disabled',caret:'hide'});
    // Recheck after screenshot: late errors and unknown requests must not slip through.
    await adapter.assertRequests();
    await verifyAssets(assets);
    if(errors.length||networkFailures.length)throw new Error('Late browser failure');
    report.passed=true;
    return report;
  } catch(error) {
    report.failure=error.message;
    await page.screenshot({path:join(outDir,'failure.png')}).catch(()=>{});
    throw error;
  } finally {
    const cleanupFailures=[];
    for(const cleanup of [()=>context.close(),()=>installed?.dispose?.(),()=>adapter.dispose?.()]){
      try { await cleanup(); } catch(error) { cleanupFailures.push(error.message); }
    }
    if(cleanupFailures.length){report.passed=false;report.cleanupFailures=cleanupFailures;}
    await writeFile(join(outDir,'capture.json'),JSON.stringify(report,null,2));
    if(cleanupFailures.length)throw new Error(`Capture cleanup failed: ${cleanupFailures.join('; ')}`);
  }
}

export async function launchHeaded(engine,options={}) {
  if(options.headless===true)throw new Error('Canonical captures require headed browsers');
  return engine.launch({...options,headless:false});
}
