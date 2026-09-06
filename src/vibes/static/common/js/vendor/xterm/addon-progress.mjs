/**
 * Copyright (c) 2014-2024 The xterm.js authors. All rights reserved.
 * @license MIT
 *
 * Copyright (c) 2012-2013, Christopher Jeffrey (MIT License)
 * @license MIT
 *
 * Originally forked from (with the author's permission):
 *   Fabrice Bellard's javascript vt100 for jslinux:
 *   http://bellard.org/jslinux/
 *   Copyright (c) 2011 Fabrice Bellard
 */
/*---------------------------------------------------------------------------------------------
 *  Copyright (c) Microsoft Corporation. All rights reserved.
 *  Licensed under the MIT License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/
function n(i){let t=0;for(let s=0;s<i.length;++s){let e=i.charCodeAt(s);if(e<48||57<e)return-1;t=t*10+e-48}return t}var o=class{constructor(){this._st=0;this._pr=0}dispose(){this._seqHandler?.dispose(),this._onChange?.dispose()}activate(t){this._seqHandler=t.parser.registerOscHandler(9,s=>{if(!s.startsWith("4;"))return!1;let e=s.split(";");if(e.length>3)return!0;e.length===2&&e.push("");let r=n(e[1]),a=n(e[2]);switch(r){case 0:this.progress={state:r,value:0};break;case 1:if(a<0)return!0;this.progress={state:r,value:a};break;case 2:case 4:if(a<0)return!0;this.progress={state:r,value:a||this._pr};break;case 3:this.progress={state:r,value:this._pr};break}return!0}),this._onChange=new t._core._onData.constructor,this.onChange=this._onChange.event}get progress(){return{state:this._st,value:this._pr}}set progress(t){if(t.state<0||t.state>4){console.warn("progress state out of bounds, not applied");return}this._st=t.state,this._pr=Math.min(Math.max(t.value,0),100),this._onChange?.fire({state:this._st,value:this._pr})}};export{o as ProgressAddon};
//# sourceMappingURL=addon-progress.mjs.map
