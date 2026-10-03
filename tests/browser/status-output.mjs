import { chromium } from '@playwright/test';
const root = process.cwd() + '/src/vibes/static';
const server = Bun.serve({port:0, async fetch(req) { const path = new URL(req.url).pathname; if(path==='/') return new Response('<div id="root"></div>',{headers:{'Content-Type':'text/html'}}); const file=Bun.file(root+path); return new Response(file); }});
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage(); await page.goto(`http://127.0.0.1:${server.port}`);
 await page.evaluate(async()=>{
  const {html,render}=await import('/js/vendor/preact-htm.js'); const {AgentStatus}=await import('/js/components/status.js');
  window.calls=[{tool_call_id:'a',title:'First',output:'<img src=x onerror="window.injected=true">',started_at:Date.now()/1000,status:'running'},{tool_call_id:'b',title:'Second',output:'second',started_at:1,ended_at:2,status:'completed'}];
  window.paint=()=>render(html`<${AgentStatus} status=${{type:'writing',tool_calls:window.calls,tool_calls_truncated:true}} renderMarkdown=${x=>x} />`,document.querySelector('#root')); window.paint(); window.stream=setInterval(window.paint,100);
 });
 await page.waitForTimeout(2300);
 const buttons=page.locator('.thinking-panel-header'); if(await buttons.count()!==2) throw Error('missing panels');
 if(!(await buttons.first().innerText()).match(/· [2-9]s/)) throw Error('timer starved');
 await buttons.first().click(); await page.waitForTimeout(150); if(await buttons.first().getAttribute('aria-expanded')!=='true'||await buttons.nth(1).getAttribute('aria-expanded')!=='false') throw Error('disclosures coupled');
 if(await page.locator('#root img').count()) throw Error('output interpreted as markup');
 if(!await page.getByText('Earlier tool calls omitted from this bounded activity snapshot.').count()) throw Error('missing omission notice');
 await page.evaluate(()=>clearInterval(window.stream)); console.log('PASS: rendered collection, streaming timer, independent disclosures, escaping, omission notice');
} finally { await browser.close(); server.stop(); }
