// Piclaw classic code highlighting; upstream MIT attribution in vendor/CODEMIRROR.md.
import {
  classHighlighter,
  highlightTree,
  StreamLanguage,
  cssLanguage,
  cppLanguage,
  goLanguage,
  htmlLanguage,
  javascriptLanguage,
  jsxLanguage,
  tsxLanguage,
  typescriptLanguage,
  jsonLanguage,
  markdownLanguage,
  pythonLanguage,
  rustLanguage,
  StandardSQL,
  xmlLanguage,
  yamlLanguage,
  dockerFile,
  powerShell,
  ruby,
  shell,
  swift,
  toml,
  clojure,
  cmake,
  coffeeScript,
  crystal,
  cypher,
  d,
  diff,
  eiffel,
  elm,
  erlang,
  factor,
  forth,
  fortran,
  gas,
  gherkin,
  groovy,
  haskell,
  haxe,
  http,
  jinja2,
  julia,
  liveScript,
  lua,
  mathematica,
  fSharp,
  nginx,
  octave,
  oz,
  pascal,
  perl,
  properties,
  protobuf,
  pug,
  puppet,
  r,
  sas,
  sass,
  scheme,
  smalltalk,
  solr,
  sparql,
  stex,
  stylus,
  tcl,
  textile,
  turtle,
  vb,
  verilog,
  vhdl,
  wast,
  webIDL,
  xQuery
} from "./vendor/codemirror.js";
const MAX_HIGHLIGHT_CHARS = 96 * 1024;
function escapeHtml(value) {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
const LANGUAGE_LABEL_ALIASES = {
  js: "JavaScript",
  javascript: "JavaScript",
  ts: "TypeScript",
  typescript: "TypeScript",
  jsx: "JSX",
  tsx: "TSX",
  py: "Python",
  python: "Python",
  sh: "Shell",
  shell: "Shell",
  bash: "Bash",
  zsh: "Zsh",
  ps1: "PowerShell",
  powershell: "PowerShell",
  md: "Markdown",
  markdown: "Markdown",
  yml: "YAML",
  yaml: "YAML",
  json: "JSON",
  html: "HTML",
  css: "CSS",
  sql: "SQL",
  go: "Go",
  c: "C",
  cc: "C++",
  cpp: "C++",
  "c++": "C++",
  cxx: "C++",
  h: "C/C++",
  hh: "C++",
  hpp: "C++",
  hxx: "C++",
  rust: "Rust",
  rs: "Rust",
  ruby: "Ruby",
  swift: "Swift",
  toml: "TOML",
  dockerfile: "Dockerfile",
  asm: "Gas",
  clj: "Clojure",
  clojure: "Clojure",
  cmake: "CMake",
  coffee: "CoffeeScript",
  coffeescript: "CoffeeScript",
  conf: "nginx",
  cr: "Crystal",
  crystal: "Crystal",
  cypher: "Cypher",
  d: "D",
  diff: "Diff",
  eiffel: "Eiffel",
  elm: "Elm",
  erl: "Erlang",
  erlang: "Erlang",
  f90: "Fortran",
  f95: "Fortran",
  factor: "Factor",
  feature: "Gherkin",
  forth: "Forth",
  fortran: "Fortran",
  fsharp: "ML",
  gas: "Gas",
  gherkin: "Gherkin",
  groovy: "Groovy",
  haskell: "Haskell",
  haxe: "Haxe",
  hs: "Haskell",
  http: "HTTP",
  hx: "Haxe",
  ini: "Properties",
  jade: "Pug",
  jinja: "Jinja2",
  jinja2: "Jinja2",
  jl: "Julia",
  julia: "Julia",
  latex: "LaTeX",
  livescript: "LiveScript",
  ls: "LiveScript",
  lua: "Lua",
  mathematica: "Mathematica",
  matlab: "Octave",
  ml: "ML",
  nginx: "nginx",
  ocaml: "ML",
  octave: "Octave",
  oz: "Oz",
  pas: "Pascal",
  pascal: "Pascal",
  patch: "Diff",
  perl: "Perl",
  pl: "Perl",
  pm: "Perl",
  pp: "Puppet",
  properties: "Properties",
  proto: "Protobuf",
  protobuf: "Protobuf",
  pug: "Pug",
  puppet: "Puppet",
  r: "R",
  rq: "SPARQL",
  s: "Gas",
  sas: "SAS",
  sass: "Sass",
  scheme: "Scheme",
  scm: "Scheme",
  scss: "Sass",
  smalltalk: "Smalltalk",
  sml: "ML",
  sparql: "SPARQL",
  st: "Smalltalk",
  styl: "Stylus",
  stylus: "Stylus",
  sv: "Verilog",
  tcl: "Tcl",
  tex: "LaTeX",
  textile: "Textile",
  ttl: "Turtle",
  turtle: "Turtle",
  vb: "VB",
  verilog: "Verilog",
  vhdl: "VHDL",
  wasm: "WebAssembly",
  wast: "WebAssembly",
  webidl: "WebIDL",
  wl: "Mathematica",
  xq: "XQuery",
  xquery: "XQuery"
};
const LEGACY_SHELL_PARSER = StreamLanguage.define(shell).parser;
const LEGACY_POWERSHELL_PARSER = StreamLanguage.define(powerShell).parser;
const LEGACY_DOCKERFILE_PARSER = StreamLanguage.define(dockerFile).parser;
const LEGACY_RUBY_PARSER = StreamLanguage.define(ruby).parser;
const LEGACY_SWIFT_PARSER = StreamLanguage.define(swift).parser;
const LEGACY_TOML_PARSER = StreamLanguage.define(toml).parser;
const LEGACY_CLOJURE_PARSER = StreamLanguage.define(clojure).parser;
const LEGACY_CMAKE_PARSER = StreamLanguage.define(cmake).parser;
const LEGACY_COFFEESCRIPT_PARSER = StreamLanguage.define(coffeeScript).parser;
const LEGACY_CRYSTAL_PARSER = StreamLanguage.define(crystal).parser;
const LEGACY_CYPHER_PARSER = StreamLanguage.define(cypher).parser;
const LEGACY_D_PARSER = StreamLanguage.define(d).parser;
const LEGACY_DIFF_PARSER = StreamLanguage.define(diff).parser;
const LEGACY_EIFFEL_PARSER = StreamLanguage.define(eiffel).parser;
const LEGACY_ELM_PARSER = StreamLanguage.define(elm).parser;
const LEGACY_ERLANG_PARSER = StreamLanguage.define(erlang).parser;
const LEGACY_FACTOR_PARSER = StreamLanguage.define(factor).parser;
const LEGACY_FORTH_PARSER = StreamLanguage.define(forth).parser;
const LEGACY_FORTRAN_PARSER = StreamLanguage.define(fortran).parser;
const LEGACY_GAS_PARSER = StreamLanguage.define(gas).parser;
const LEGACY_GHERKIN_PARSER = StreamLanguage.define(gherkin).parser;
const LEGACY_GROOVY_PARSER = StreamLanguage.define(groovy).parser;
const LEGACY_HASKELL_PARSER = StreamLanguage.define(haskell).parser;
const LEGACY_HAXE_PARSER = StreamLanguage.define(haxe).parser;
const LEGACY_HTTP_PARSER = StreamLanguage.define(http).parser;
const LEGACY_JINJA2_PARSER = StreamLanguage.define(jinja2).parser;
const LEGACY_JULIA_PARSER = StreamLanguage.define(julia).parser;
const LEGACY_LIVESCRIPT_PARSER = StreamLanguage.define(liveScript).parser;
const LEGACY_LUA_PARSER = StreamLanguage.define(lua).parser;
const LEGACY_MATHEMATICA_PARSER = StreamLanguage.define(mathematica).parser;
const LEGACY_MLLIKE_PARSER = StreamLanguage.define(fSharp).parser;
const LEGACY_NGINX_PARSER = StreamLanguage.define(nginx).parser;
const LEGACY_OCTAVE_PARSER = StreamLanguage.define(octave).parser;
const LEGACY_OZ_PARSER = StreamLanguage.define(oz).parser;
const LEGACY_PASCAL_PARSER = StreamLanguage.define(pascal).parser;
const LEGACY_PERL_PARSER = StreamLanguage.define(perl).parser;
const LEGACY_PROPERTIES_PARSER = StreamLanguage.define(properties).parser;
const LEGACY_PROTOBUF_PARSER = StreamLanguage.define(protobuf).parser;
const LEGACY_PUG_PARSER = StreamLanguage.define(pug).parser;
const LEGACY_PUPPET_PARSER = StreamLanguage.define(puppet).parser;
const LEGACY_R_PARSER = StreamLanguage.define(r).parser;
const LEGACY_SAS_PARSER = StreamLanguage.define(sas).parser;
const LEGACY_SASS_PARSER = StreamLanguage.define(sass).parser;
const LEGACY_SCHEME_PARSER = StreamLanguage.define(scheme).parser;
const LEGACY_SMALLTALK_PARSER = StreamLanguage.define(smalltalk).parser;
const LEGACY_SOLR_PARSER = StreamLanguage.define(solr).parser;
const LEGACY_SPARQL_PARSER = StreamLanguage.define(sparql).parser;
const LEGACY_STEX_PARSER = StreamLanguage.define(stex).parser;
const LEGACY_STYLUS_PARSER = StreamLanguage.define(stylus).parser;
const LEGACY_TCL_PARSER = StreamLanguage.define(tcl).parser;
const LEGACY_TEXTILE_PARSER = StreamLanguage.define(textile).parser;
const LEGACY_TURTLE_PARSER = StreamLanguage.define(turtle).parser;
const LEGACY_VB_PARSER = StreamLanguage.define(vb).parser;
const LEGACY_VERILOG_PARSER = StreamLanguage.define(verilog).parser;
const LEGACY_VHDL_PARSER = StreamLanguage.define(vhdl).parser;
const LEGACY_WAST_PARSER = StreamLanguage.define(wast).parser;
const LEGACY_WEBIDL_PARSER = StreamLanguage.define(webIDL).parser;
const LEGACY_XQUERY_PARSER = StreamLanguage.define(xQuery).parser;
export function normalizeCodeLanguageLabel(lang) {
  const raw = String(lang || "").trim().toLowerCase();
  if (!raw)
    return "text";
  return LANGUAGE_LABEL_ALIASES[raw] || String(lang || "").trim();
}
export function parserForCodeFenceLanguage(lang) {
  const raw = String(lang || "").trim().toLowerCase();
  switch (raw) {
    case "js":
    case "javascript":
      return javascriptLanguage.parser;
    case "ts":
    case "typescript":
      return typescriptLanguage.parser;
    case "jsx":
      return jsxLanguage.parser;
    case "tsx":
      return tsxLanguage.parser;
    case "py":
    case "python":
      return pythonLanguage.parser;
    case "json":
      return jsonLanguage.parser;
    case "css":
      return cssLanguage.parser;
    case "html":
      return htmlLanguage.parser;
    case "xml":
      return xmlLanguage.parser;
    case "yaml":
    case "yml":
      return yamlLanguage.parser;
    case "md":
    case "markdown":
      return markdownLanguage.parser;
    case "sql":
      return StandardSQL.language.parser;
    case "go":
      return goLanguage.parser;
    case "c":
    case "cc":
    case "cpp":
    case "cxx":
    case "c++":
    case "h":
    case "hh":
    case "hpp":
    case "hxx":
      return cppLanguage.parser;
    case "sh":
    case "bash":
    case "shell":
    case "zsh":
      return LEGACY_SHELL_PARSER;
    case "ps1":
    case "powershell":
      return LEGACY_POWERSHELL_PARSER;
    case "dockerfile":
      return LEGACY_DOCKERFILE_PARSER;
    case "rb":
    case "ruby":
      return LEGACY_RUBY_PARSER;
    case "rs":
    case "rust":
      return rustLanguage.parser;
    case "swift":
      return LEGACY_SWIFT_PARSER;
    case "toml":
      return LEGACY_TOML_PARSER;
    case "asm":
      return LEGACY_GAS_PARSER;
    case "clj":
      return LEGACY_CLOJURE_PARSER;
    case "clojure":
      return LEGACY_CLOJURE_PARSER;
    case "cmake":
      return LEGACY_CMAKE_PARSER;
    case "coffee":
      return LEGACY_COFFEESCRIPT_PARSER;
    case "coffeescript":
      return LEGACY_COFFEESCRIPT_PARSER;
    case "cr":
      return LEGACY_CRYSTAL_PARSER;
    case "crystal":
      return LEGACY_CRYSTAL_PARSER;
    case "cypher":
      return LEGACY_CYPHER_PARSER;
    case "d":
      return LEGACY_D_PARSER;
    case "diff":
      return LEGACY_DIFF_PARSER;
    case "eiffel":
      return LEGACY_EIFFEL_PARSER;
    case "elm":
      return LEGACY_ELM_PARSER;
    case "erl":
      return LEGACY_ERLANG_PARSER;
    case "erlang":
      return LEGACY_ERLANG_PARSER;
    case "f90":
      return LEGACY_FORTRAN_PARSER;
    case "f95":
      return LEGACY_FORTRAN_PARSER;
    case "factor":
      return LEGACY_FACTOR_PARSER;
    case "feature":
      return LEGACY_GHERKIN_PARSER;
    case "forth":
      return LEGACY_FORTH_PARSER;
    case "fortran":
      return LEGACY_FORTRAN_PARSER;
    case "fsharp":
      return LEGACY_MLLIKE_PARSER;
    case "gas":
      return LEGACY_GAS_PARSER;
    case "gherkin":
      return LEGACY_GHERKIN_PARSER;
    case "groovy":
      return LEGACY_GROOVY_PARSER;
    case "haskell":
      return LEGACY_HASKELL_PARSER;
    case "haxe":
      return LEGACY_HAXE_PARSER;
    case "hs":
      return LEGACY_HASKELL_PARSER;
    case "http":
      return LEGACY_HTTP_PARSER;
    case "hx":
      return LEGACY_HAXE_PARSER;
    case "ini":
      return LEGACY_PROPERTIES_PARSER;
    case "jade":
      return LEGACY_PUG_PARSER;
    case "jinja":
      return LEGACY_JINJA2_PARSER;
    case "jinja2":
      return LEGACY_JINJA2_PARSER;
    case "jl":
      return LEGACY_JULIA_PARSER;
    case "julia":
      return LEGACY_JULIA_PARSER;
    case "latex":
      return LEGACY_STEX_PARSER;
    case "livescript":
      return LEGACY_LIVESCRIPT_PARSER;
    case "ls":
      return LEGACY_LIVESCRIPT_PARSER;
    case "lua":
      return LEGACY_LUA_PARSER;
    case "mathematica":
      return LEGACY_MATHEMATICA_PARSER;
    case "matlab":
      return LEGACY_OCTAVE_PARSER;
    case "ml":
      return LEGACY_MLLIKE_PARSER;
    case "mllike":
      return LEGACY_MLLIKE_PARSER;
    case "nginx":
      return LEGACY_NGINX_PARSER;
    case "ocaml":
      return LEGACY_MLLIKE_PARSER;
    case "octave":
      return LEGACY_OCTAVE_PARSER;
    case "oz":
      return LEGACY_OZ_PARSER;
    case "pas":
      return LEGACY_PASCAL_PARSER;
    case "pascal":
      return LEGACY_PASCAL_PARSER;
    case "patch":
      return LEGACY_DIFF_PARSER;
    case "perl":
      return LEGACY_PERL_PARSER;
    case "pl":
      return LEGACY_PERL_PARSER;
    case "pm":
      return LEGACY_PERL_PARSER;
    case "pp":
      return LEGACY_PUPPET_PARSER;
    case "properties":
      return LEGACY_PROPERTIES_PARSER;
    case "proto":
      return LEGACY_PROTOBUF_PARSER;
    case "protobuf":
      return LEGACY_PROTOBUF_PARSER;
    case "pug":
      return LEGACY_PUG_PARSER;
    case "puppet":
      return LEGACY_PUPPET_PARSER;
    case "r":
      return LEGACY_R_PARSER;
    case "rq":
      return LEGACY_SPARQL_PARSER;
    case "s":
      return LEGACY_GAS_PARSER;
    case "sas":
      return LEGACY_SAS_PARSER;
    case "sass":
      return LEGACY_SASS_PARSER;
    case "scheme":
      return LEGACY_SCHEME_PARSER;
    case "scm":
      return LEGACY_SCHEME_PARSER;
    case "scss":
      return LEGACY_SASS_PARSER;
    case "smalltalk":
      return LEGACY_SMALLTALK_PARSER;
    case "sml":
      return LEGACY_MLLIKE_PARSER;
    case "solr":
      return LEGACY_SOLR_PARSER;
    case "sparql":
      return LEGACY_SPARQL_PARSER;
    case "st":
      return LEGACY_SMALLTALK_PARSER;
    case "stex":
      return LEGACY_STEX_PARSER;
    case "styl":
      return LEGACY_STYLUS_PARSER;
    case "stylus":
      return LEGACY_STYLUS_PARSER;
    case "sv":
      return LEGACY_VERILOG_PARSER;
    case "tcl":
      return LEGACY_TCL_PARSER;
    case "tex":
      return LEGACY_STEX_PARSER;
    case "textile":
      return LEGACY_TEXTILE_PARSER;
    case "ttl":
      return LEGACY_TURTLE_PARSER;
    case "turtle":
      return LEGACY_TURTLE_PARSER;
    case "vb":
      return LEGACY_VB_PARSER;
    case "verilog":
      return LEGACY_VERILOG_PARSER;
    case "vhdl":
      return LEGACY_VHDL_PARSER;
    case "wasm":
      return LEGACY_WAST_PARSER;
    case "wast":
      return LEGACY_WAST_PARSER;
    case "webidl":
      return LEGACY_WEBIDL_PARSER;
    case "wl":
      return LEGACY_MATHEMATICA_PARSER;
    case "xq":
      return LEGACY_XQUERY_PARSER;
    case "xquery":
      return LEGACY_XQUERY_PARSER;
    default:
      return null;
  }
}
export function highlightCodeToHtml(code, lang) {
  if (String(code || "").length > MAX_HIGHLIGHT_CHARS)
    return escapeHtml(code);
  const parser = parserForCodeFenceLanguage(lang);
  if (!parser)
    return escapeHtml(code);
  const tokens = [];
  try {
    const tree = parser.parse(code);
    highlightTree(tree, classHighlighter, (from, to, cls) => {
      if (!cls || from >= to)
        return;
      tokens.push({ from, to, cls });
    });
  } catch {
    return escapeHtml(code);
  }
  if (!tokens.length)
    return escapeHtml(code);
  tokens.sort((a, b) => a.from - b.from || a.to - b.to);
  let cursor = 0;
  let html = "";
  for (const token of tokens) {
    if (token.from > cursor)
      html += escapeHtml(code.slice(cursor, token.from));
    html += `<span class="${escapeHtml(token.cls)}">${escapeHtml(code.slice(token.from, token.to))}</span>`;
    cursor = Math.max(cursor, token.to);
  }
  if (cursor < code.length)
    html += escapeHtml(code.slice(cursor));
  return html;
}
export function highlightCodeLinesAsHtml(code, lang) {
  const lines = String(code || "").split(`
`);
  if (!code)
    return lines;
  if (String(code || "").length > MAX_HIGHLIGHT_CHARS)
    return lines.map((line) => escapeHtml(line) || "&nbsp;");
  const parser = parserForCodeFenceLanguage(lang);
  if (!parser)
    return lines.map((line) => escapeHtml(line));
  const tokens = [];
  try {
    const tree = parser.parse(code);
    highlightTree(tree, classHighlighter, (from, to, cls) => {
      if (!cls || from >= to)
        return;
      tokens.push({ from, to, cls });
    });
  } catch {
    return lines.map((line) => escapeHtml(line));
  }
  if (!tokens.length)
    return lines.map((line) => escapeHtml(line));
  tokens.sort((a, b) => a.from - b.from || a.to - b.to);
  const lineStarts = [];
  let pos = 0;
  for (const line of lines) {
    lineStarts.push(pos);
    pos += line.length + 1;
  }
  const result = [];
  let tokenIndex = 0;
  for (let i = 0;i < lines.length; i += 1) {
    const start = lineStarts[i];
    const end = start + lines[i].length;
    let html = "";
    let cursor = start;
    while (tokenIndex < tokens.length && tokens[tokenIndex].to <= start)
      tokenIndex += 1;
    for (let j = tokenIndex;j < tokens.length; j += 1) {
      const token = tokens[j];
      if (token.from >= end)
        break;
      const tokenFrom = Math.max(start, token.from);
      const tokenTo = Math.min(end, token.to);
      if (tokenFrom > cursor)
        html += escapeHtml(code.slice(cursor, tokenFrom));
      if (tokenTo > tokenFrom)
        html += `<span class="${escapeHtml(token.cls)}">${escapeHtml(code.slice(tokenFrom, tokenTo))}</span>`;
      cursor = Math.max(cursor, tokenTo);
    }
    if (cursor < end)
      html += escapeHtml(code.slice(cursor, end));
    result.push(html || "&nbsp;");
  }
  return result;
}
export function extensionToLanguage(filePath) {
  const ext = (filePath.match(/\.([^.]+)$/) || [])[1]?.toLowerCase() || "";
  const map = {
    ts: "typescript",
    tsx: "tsx",
    js: "javascript",
    jsx: "jsx",
    mjs: "javascript",
    cjs: "javascript",
    py: "python",
    rb: "ruby",
    rs: "rust",
    go: "go",
    java: "java",
    c: "c",
    h: "c",
    cc: "cpp",
    cpp: "cpp",
    cxx: "cpp",
    hpp: "cpp",
    hxx: "cpp",
    cs: "csharp",
    swift: "swift",
    kt: "kotlin",
    sh: "shell",
    bash: "bash",
    zsh: "zsh",
    fish: "shell",
    ps1: "powershell",
    psm1: "powershell",
    json: "json",
    yaml: "yaml",
    yml: "yaml",
    toml: "toml",
    xml: "xml",
    html: "html",
    htm: "html",
    css: "css",
    scss: "sass",
    sass: "sass",
    sql: "sql",
    graphql: "graphql",
    gql: "graphql",
    dockerfile: "dockerfile",
    makefile: "makefile",
    lua: "lua",
    perl: "perl",
    pl: "perl",
    pm: "perl",
    r: "r",
    jl: "julia",
    hs: "haskell",
    erl: "erlang",
    clj: "clojure",
    scm: "scheme",
    elm: "elm",
    ex: "elixir",
    exs: "elixir",
    proto: "protobuf",
    tf: "hcl",
    diff: "diff",
    patch: "diff",
    ini: "properties",
    conf: "nginx",
    cfg: "properties",
    v: "verilog",
    sv: "verilog",
    vhd: "vhdl",
    vhdl: "vhdl",
    pas: "pascal",
    f90: "fortran",
    f95: "fortran",
    cmake: "cmake",
    groovy: "groovy",
    gradle: "groovy",
    tex: "stex",
    latex: "stex",
    bib: "stex",
    d: "d",
    nim: "nim",
    zig: "zig",
    pug: "pug",
    jade: "pug",
    styl: "stylus",
    coffee: "coffeescript",
    tcl: "tcl",
    ml: "mllike",
    sml: "mllike",
    fs: "mllike",
    wasm: "wast",
    wat: "wast",
    pp: "puppet",
    feature: "gherkin",
    ttl: "turtle",
    rq: "sparql",
    xq: "xquery"
  };
  const basename = filePath.split("/").pop()?.toLowerCase() || "";
  if (basename === "dockerfile" || basename.startsWith("dockerfile."))
    return "dockerfile";
  if (basename === "makefile" || basename === "gnumakefile")
    return "cmake";
  if (basename === ".env" || basename.endsWith(".env"))
    return "properties";
  if (basename === "cmakelists.txt")
    return "cmake";
  if (basename === "vagrantfile" || basename === "rakefile" || basename === "gemfile")
    return "ruby";
  return map[ext] || "";
}
