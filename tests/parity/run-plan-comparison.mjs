import {chromium,webkit} from 'playwright';
import {launchHeaded} from './capture.mjs';
import {compareCase} from './compare-case.mjs';
import {createCases,viewports} from './cases.mjs';
import {createPiclawAdapter} from './adapters/piclaw.mjs';
import {createTauAdapter} from './adapters/tau.mjs';
const frontendRoot=process.env.TAU_VISUAL_STATIC;
const sharedStaticRoot=process.env.TAU_SHARED_STATIC;
if(!frontendRoot||!sharedStaticRoot)throw new Error('Explicit Tau asset roots required');
const engineName=process.env.UI_PARITY_ENGINE||'chromium';
if(!['chromium','webkit'].includes(engineName))throw new Error('Unknown engine');
const theme=process.env.UI_PARITY_THEME||'light';
const viewportId=process.env.UI_PARITY_VIEWPORT||'tablet';
const viewport=viewports.find(view=>view.id===viewportId);
if(!viewport)throw new Error('Unknown canonical viewport');
const [testCase]=createCases({engines:[engineName],themes:[theme],viewports:[viewport],scenarios:[process.env.UI_PARITY_SCENARIO||'populated-plan-open']});
const engine={chromium,webkit}[engineName];
const launchOptions=process.env.UI_PARITY_DISABLE_GPU==='1'?{args:['--disable-gpu']}:{};
const browser=await launchHeaded(engine,launchOptions);
try{
 const report=await compareCase({browser,adapterFactories:{
 piclaw:()=>createPiclawAdapter({runtimeRoot:process.env.UI_PARITY_PICLAW_RUNTIME||'/opt/piclaw/current/app/runtime',planSource:process.env.UI_PARITY_PICLAW_PLAN||'/workspace/.pi/extensions/node_modules/@rcarmo/piclaw-addon-plan-sidebar/web/index.ts'}),
 tau:()=>createTauAdapter({frontendRoot,sharedStaticRoot}),
 },state:testCase.state,viewport:testCase.viewport,theme:testCase.theme,outDir:process.env.UI_PARITY_OUT||`/workspace/tmp/canonical-comparison/${testCase.id}`,repeats:testCase.repeats});
 console.log(JSON.stringify({engine:engineName,browser:browser.version(),launchOptions,passed:report.passed,hosts:Object.fromEntries(Object.entries(report.hosts).map(([name,host])=>[name,{stable:host.stable,repeats:host.comparisons}])),comparisons:report.comparisons},null,2));
 if(!report.passed)process.exitCode=1;
}finally{await browser.close();}
