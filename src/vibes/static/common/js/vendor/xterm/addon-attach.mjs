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
var r=class{constructor(e,t){this._disposables=[];this._socket=e,this._socket.binaryType="arraybuffer",this._bidirectional=!(t&&t.bidirectional===!1)}activate(e){this._disposables.push(o(this._socket,"message",t=>{let s=t.data;e.write(typeof s=="string"?s:new Uint8Array(s))})),this._bidirectional&&(this._disposables.push(e.onData(t=>this._sendData(t))),this._disposables.push(e.onBinary(t=>this._sendBinary(t)))),this._disposables.push(o(this._socket,"close",()=>this.dispose())),this._disposables.push(o(this._socket,"error",()=>this.dispose()))}dispose(){for(let e of this._disposables)e.dispose()}_sendData(e){this._checkOpenSocket()&&this._socket.send(e)}_sendBinary(e){if(!this._checkOpenSocket())return;let t=new Uint8Array(e.length);for(let s=0;s<e.length;++s)t[s]=e.charCodeAt(s)&255;this._socket.send(t)}_checkOpenSocket(){switch(this._socket.readyState){case WebSocket.OPEN:return!0;case WebSocket.CONNECTING:throw new Error("Attach addon was loaded before socket was open");case WebSocket.CLOSING:return console.warn("Attach addon socket is closing"),!1;case WebSocket.CLOSED:throw new Error("Attach addon socket is closed");default:throw new Error("Unexpected socket state")}}};function o(i,e,t){return i.addEventListener(e,t),{dispose:()=>{t&&i.removeEventListener(e,t)}}}export{r as AttachAddon};
//# sourceMappingURL=addon-attach.mjs.map
