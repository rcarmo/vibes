import {test,expect} from '@playwright/test';
function luminance(rgb){const values=rgb.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;});return .2126*values[0]+.7152*values[1]+.0722*values[2];}
function ratio(a,b,opacity=1){const fg=a.match(/[\d.]+/g).slice(0,3).map(Number),bg=b.match(/[\d.]+/g).slice(0,3).map(Number);const blended=`rgb(${fg.map((v,i)=>v*opacity+bg[i]*(1-opacity)).join(',')})`;const x=luminance(blended),y=luminance(b);return(Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
for(const theme of ['light','dark'])test(`model hint meets text contrast in ${theme} theme`,async({page})=>{
 await page.addInitScript(value=>localStorage.setItem('vibes-theme',value),theme);
 await page.route('**/sessions/*/model-state',route=>route.fulfill({json:{available:true,model:{provider:'test',id:'fixture',reasoning:true,contextWindow:65536},thinking_level:'medium',compacting:false}}));
 await page.goto('/');
 const hint=page.locator('.compose-model-hint-btn');await expect(hint).toBeVisible();
 const colors=await hint.evaluate(node=>{const style=getComputedStyle(node);let parent=node.parentElement,background='';while(parent){const value=getComputedStyle(parent).backgroundColor;if(value&&!value.endsWith(', 0)')&&value!=='rgba(0, 0, 0, 0)'){background=value;break;}parent=parent.parentElement;}return{color:style.color,background,opacity:style.opacity,fontSize:style.fontSize};});
 expect(Number(colors.opacity)).toBeGreaterThanOrEqual(.88);
 expect(ratio(colors.color,colors.background,Number(colors.opacity)),JSON.stringify(colors)).toBeGreaterThanOrEqual(4.5);
});
