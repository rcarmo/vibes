import {test,expect} from 'bun:test';
import {piclawAssets,tauAssets} from './assets.mjs';
test('host manifests require explicit native roots and include editor/addon sources',()=>{
 expect(()=>piclawAssets({})).toThrow('Explicit');
 expect(()=>tauAssets({frontendRoot:'/tmp/tau'})).toThrow('Explicit');
 const reference=piclawAssets({runtimeRoot:'/tmp/piclaw',planSource:'/tmp/addon.ts'});
 expect(reference.editor).toBe('/tmp/piclaw/extensions/viewers/editor/vendor/codemirror.js');
 expect(reference.plan).toBe('/tmp/addon.ts');
 const tau=tauAssets({frontendRoot:'/tmp/tau/static',sharedStaticRoot:'/tmp/shared'});
 expect(tau.app).toBe('/tmp/tau/static/dist/app.js');
 expect(tau.frontendSDK).toBe('/tmp/shared/frontend-sdk.js');
});
