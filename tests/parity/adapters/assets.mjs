import {resolve} from 'node:path';

export function piclawAssets({runtimeRoot,planSource}) {
  if(!runtimeRoot||!planSource)throw new Error('Explicit Piclaw runtime root and deployed Plan source required');
  const web=resolve(runtimeRoot,'web/static');
  return {
    html:resolve(web,'classic/index.html'),
    manifest:resolve(web,'manifest.json'),
    favicon:resolve(web,'favicon.ico'),
    app:resolve(web,'classic/dist/app.bundle.js'),
    css:resolve(web,'classic/dist/app.bundle.css'),
    editor:resolve(runtimeRoot,'extensions/viewers/editor/vendor/codemirror.js'),
    plan:resolve(planSource),
  };
}

export function tauAssets({frontendRoot,sharedStaticRoot}) {
  if(!frontendRoot||!sharedStaticRoot)throw new Error('Explicit Tau frontend and shared static roots required');
  const root=resolve(frontendRoot);
  return {
    html:resolve(root,'index.html'),
    manifest:resolve(root,'manifest.json'),
    bootstrap:resolve(root,'js/bootstrap.js'),
    app:resolve(root,'dist/app.js'),
    css:resolve(root,'dist/app.css'),
    editor:resolve(root,'js/vendor/plan-codemirror.js'),
    extensionUI:resolve(sharedStaticRoot,'extension-ui.js'),
    frontendSDK:resolve(sharedStaticRoot,'frontend-sdk.js'),
    widgetBridge:resolve(sharedStaticRoot,'widget-bridge.js'),
  };
}
