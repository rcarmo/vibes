# CodeMirror vendor

`codemirror.js`, `codemirror-entry.ts` and `codemirror.meta.json` are copied from
Piclaw 3.1.2's installed editor viewer. The bundle is unchanged; its original
SHA-256 and build command are recorded in the metadata. It exports all symbols
used by the earlier Vibes editor bundle plus the parser/highlighter APIs used
for fenced code in chat. Sharing one bundle prevents duplicate CodeMirror state
instances.

`../code-highlighting.js` is the TypeScript-stripped Piclaw classic code highlighter,
with only the import path adapted to this local bundle. The MIT license is under
`licenses/PICLAW-MIT.txt`; Lezer's MIT notice is under `licenses/LEZER-MIT.txt`.
Full upstream notices for 48 resolved dependency versions (CodeMirror, Lezer,
Replit Vim/indentation markers, uiw GitHub themes and supporting packages) are
preserved verbatim in `licenses/CODEMIRROR-NOTICES.txt`. Archives were downloaded
without executing package code and verified against the deployed Piclaw Bun
lockfile SHA-512 values. The two uiw packages omit LICENSE in their archives;
their notice comes from the matching upstream `v4.25.11` tag, with its URL recorded.
Duplicate lockfile resolutions are included conservatively, not asserted to be
separate runtime copies. Keep this notice file with the vendor bundle.
