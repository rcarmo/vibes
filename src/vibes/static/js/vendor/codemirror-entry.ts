import { EditorSelection, EditorState, StateEffect, StateField } from "@codemirror/state";
import {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  highlightWhitespace,
  scrollPastEnd,
  showPanel,
  Decoration,
  ViewPlugin,
  WidgetType,
  drawSelection,
} from "@codemirror/view";
import { history, defaultKeymap, historyKeymap, indentWithTab } from "@codemirror/commands";
import { defaultHighlightStyle, StreamLanguage, HighlightStyle, syntaxHighlighting, syntaxTree, ensureSyntaxTree, indentOnInput, indentUnit } from "@codemirror/language";

export { EditorSelection, EditorState, Compartment, RangeSetBuilder, RangeSet, Prec, StateEffect, StateField } from "@codemirror/state";
export type { Extension, Range, Transaction } from "@codemirror/state";
export {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  highlightWhitespace,
  scrollPastEnd,
  showPanel,
  Decoration,
  ViewPlugin,
  WidgetType,
} from "@codemirror/view";
export type { DecorationSet, ViewUpdate } from "@codemirror/view";
export { javascript } from "@codemirror/lang-javascript";
export { python } from "@codemirror/lang-python";
export { markdown, markdownLanguage } from "@codemirror/lang-markdown";
export { go } from "@codemirror/lang-go";
export { cpp, cppLanguage } from "@codemirror/lang-cpp";
export { json } from "@codemirror/lang-json";
export { css } from "@codemirror/lang-css";
export { html } from "@codemirror/lang-html";
export { rust, rustLanguage } from "@codemirror/lang-rust";
export { yaml } from "@codemirror/lang-yaml";
export { sql } from "@codemirror/lang-sql";
export { xml } from "@codemirror/lang-xml";
export { StreamLanguage, HighlightStyle, syntaxHighlighting, syntaxTree, ensureSyntaxTree, indentOnInput, indentUnit } from "@codemirror/language";
export { tags, classHighlighter } from "@lezer/highlight";
export { shell } from "@codemirror/legacy-modes/mode/shell";
export { indentWithTab } from "@codemirror/commands";
export { search, openSearchPanel, closeSearchPanel, searchPanelOpen, getSearchQuery, setSearchQuery, SearchQuery, findNext, findPrevious, searchKeymap, highlightSelectionMatches } from "@codemirror/search";
export { autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";
export { lintGutter } from "@codemirror/lint";
export { vim } from "@replit/codemirror-vim";
export { indentationMarkers } from "@replit/codemirror-indentation-markers";
export { githubLight, githubDark } from "@uiw/codemirror-theme-github";
export { MergeView } from "@codemirror/merge";

// Additional exports for shared vendor usage by app-side syntax highlighting.
export { javascriptLanguage, jsxLanguage, tsxLanguage, typescriptLanguage } from "@codemirror/lang-javascript";
export { pythonLanguage } from "@codemirror/lang-python";
export { goLanguage } from "@codemirror/lang-go";
export { jsonLanguage } from "@codemirror/lang-json";
export { cssLanguage } from "@codemirror/lang-css";
export { htmlLanguage } from "@codemirror/lang-html";
export { yamlLanguage } from "@codemirror/lang-yaml";
export { xmlLanguage } from "@codemirror/lang-xml";
export { StandardSQL } from "@codemirror/lang-sql";
export { highlightTree } from "@lezer/highlight";
export { dockerFile } from "@codemirror/legacy-modes/mode/dockerfile";
export { powerShell } from "@codemirror/legacy-modes/mode/powershell";
export { ruby } from "@codemirror/legacy-modes/mode/ruby";
export { swift } from "@codemirror/legacy-modes/mode/swift";
export { toml } from "@codemirror/legacy-modes/mode/toml";

/**
 * Keep the editor bootstrap on the direct @codemirror/* packages only.
 * Importing minimalSetup from the aggregate `codemirror` package can pull a
 * second @codemirror/state instance into the graph, which then breaks
 * extension flattening with "Unrecognized extension value" errors.
 */
export const minimalSetup = [
  highlightSpecialChars(),
  history(),
  drawSelection(),
  syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
  keymap.of([
    ...defaultKeymap,
    ...historyKeymap,
  ]),
];
export { clojure } from "@codemirror/legacy-modes/mode/clojure";
export { cmake } from "@codemirror/legacy-modes/mode/cmake";
export { coffeeScript } from "@codemirror/legacy-modes/mode/coffeescript";
export { crystal } from "@codemirror/legacy-modes/mode/crystal";
export { cypher } from "@codemirror/legacy-modes/mode/cypher";
export { d } from "@codemirror/legacy-modes/mode/d";
export { diff } from "@codemirror/legacy-modes/mode/diff";
export { eiffel } from "@codemirror/legacy-modes/mode/eiffel";
export { elm } from "@codemirror/legacy-modes/mode/elm";
export { erlang } from "@codemirror/legacy-modes/mode/erlang";
export { factor } from "@codemirror/legacy-modes/mode/factor";
export { forth } from "@codemirror/legacy-modes/mode/forth";
export { fortran } from "@codemirror/legacy-modes/mode/fortran";
export { gas } from "@codemirror/legacy-modes/mode/gas";
export { gherkin } from "@codemirror/legacy-modes/mode/gherkin";
export { groovy } from "@codemirror/legacy-modes/mode/groovy";
export { haskell } from "@codemirror/legacy-modes/mode/haskell";
export { haxe } from "@codemirror/legacy-modes/mode/haxe";
export { http } from "@codemirror/legacy-modes/mode/http";
export { jinja2 } from "@codemirror/legacy-modes/mode/jinja2";
export { julia } from "@codemirror/legacy-modes/mode/julia";
export { liveScript } from "@codemirror/legacy-modes/mode/livescript";
export { lua } from "@codemirror/legacy-modes/mode/lua";
export { mathematica } from "@codemirror/legacy-modes/mode/mathematica";
export { fSharp } from "@codemirror/legacy-modes/mode/mllike";
export { nginx } from "@codemirror/legacy-modes/mode/nginx";
export { octave } from "@codemirror/legacy-modes/mode/octave";
export { oz } from "@codemirror/legacy-modes/mode/oz";
export { pascal } from "@codemirror/legacy-modes/mode/pascal";
export { perl } from "@codemirror/legacy-modes/mode/perl";
export { properties } from "@codemirror/legacy-modes/mode/properties";
export { protobuf } from "@codemirror/legacy-modes/mode/protobuf";
export { pug } from "@codemirror/legacy-modes/mode/pug";
export { puppet } from "@codemirror/legacy-modes/mode/puppet";
export { r } from "@codemirror/legacy-modes/mode/r";
export { sas } from "@codemirror/legacy-modes/mode/sas";
export { sass } from "@codemirror/legacy-modes/mode/sass";
export { scheme } from "@codemirror/legacy-modes/mode/scheme";
export { smalltalk } from "@codemirror/legacy-modes/mode/smalltalk";
export { solr } from "@codemirror/legacy-modes/mode/solr";
export { sparql } from "@codemirror/legacy-modes/mode/sparql";
export { stex } from "@codemirror/legacy-modes/mode/stex";
export { stylus } from "@codemirror/legacy-modes/mode/stylus";
export { tcl } from "@codemirror/legacy-modes/mode/tcl";
export { textile } from "@codemirror/legacy-modes/mode/textile";
export { turtle } from "@codemirror/legacy-modes/mode/turtle";
export { vb } from "@codemirror/legacy-modes/mode/vb";
export { verilog } from "@codemirror/legacy-modes/mode/verilog";
export { vhdl } from "@codemirror/legacy-modes/mode/vhdl";
export { wast } from "@codemirror/legacy-modes/mode/wast";
export { webIDL } from "@codemirror/legacy-modes/mode/webidl";
export { xQuery } from "@codemirror/legacy-modes/mode/xquery";
