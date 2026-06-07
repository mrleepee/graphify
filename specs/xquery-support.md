# XQuery Language Support for Graphify — Implementation Spec

Graphify's `extract()` pipeline parses source files into a knowledge graph of nodes and edges, supporting ~30 languages via tree-sitter grammars. XQuery (`.xqy`) files — used heavily in MarkLogic Server applications — are currently skipped entirely. This spec covers adding XQuery support: forking the existing `tree-sitter-xquery` grammar, extending it with MarkLogic-specific JSON node constructors, publishing it as a PyPI package, and writing the Graphify extractor.

**Initiative:** [graphify#N] Add XQuery language support
**Status:** Phase 1 complete
**Repo:** [mrleepee/tree-sitter-xquery](https://github.com/mrleepee/tree-sitter-xquery) (fork of grantmacken/tree-sitter-xquery)
**Branch:** `feature/marklogic-json-constructors`

## Requirements

| # | User input | Current behaviour | Expected behaviour | Verified |
|---|---|---|---|---|
| R1 | Directory containing `.xqy` files passed to `graphify extract` | `.xqy` files skipped — not in `CODE_EXTENSIONS`, no extractor in `_DISPATCH` | `.xqy` files parsed, nodes and edges emitted like other languages | Tested by running graphify on a MarkLogic codebase |
| R2 | MarkLogic XQuery using `object-node { "key": value }` syntax, `as object-node()` type tests, `declare private function`, `catch ($e)` | `grantmacken/tree-sitter-xquery` grammar produces ERROR nodes for MarkLogic extensions | Grammar parses all five JSON constructors, five node tests, `declare private function/variable`, and `catch ($var)` without errors | ✅ Phase 1: 139/144 CAS corpus clean (96.5%) |
| R3 | `pip install tree-sitter-xquery` | Package not found on PyPI | Installable Python wheel published to PyPI | `pip install tree-sitter-xquery` succeeds |
| R4 | XQuery module with `declare function au:foo($x as xs:int)` | Function not extracted as a graph node | Function declaration produces a node with ID via `_make_id(file_stem, qname)` (e.g. `mymodule_au_foo`), label `au:foo()`, metadata `{kind: "function", arity: 1, parameterStrictTyping: 1.0, hasReturnType: false}`, contained by its file node. Arity is in metadata, not the ID or label. | Verified in extract output |
| R5 | XQuery file with `import module namespace asc = "urn:asc" at "/lib/asc.xqy"` | Import not captured as an edge | Module import produces an `imports` edge from the file node with `{namespace: "urn:asc", target_path: "/lib/asc.xqy"}` in metadata. Cross-file resolution to corpus file nodes deferred to follow-up. | Verified in extract output |
| R6 | XQuery function body calling `cts:search($x, $query)` | Call not captured | Function call produces a `calls` edge from the enclosing function node to a node for the callee. Internal callees (declared in same file) get `confidence: "EXTRACTED"`. External callees are emitted as `raw_calls` entries for the symbol resolution pipeline (which emits `INFERRED` for unique matches, otherwise drops them). No new confidence values introduced — uses existing `EXTRACTED`/`INFERRED`/`AMBIGUOUS` set. | Verified in extract output |
| R7 | XQuery `declare variable $MAX as xs:integer := 200` | Variable not captured | Global variable declaration produces a node with label `$MAX`, kind `variable`, contained by its file node | Verified in extract output |
| R8a | `pip install graphifyy[xquery]` | tree-sitter-xquery not installable | Phase 2 publishes `tree-sitter-xquery` to PyPI; Phase 3 adds `xquery = ["tree-sitter-xquery"]` to `pyproject.toml` `[project.optional-dependencies]` and adds it to the `all` aggregation | `pip install graphifyy[xquery]` succeeds after Phase 2 |
| R8b | `.xqy` file extraction when tree-sitter-xquery not installed | Crash or silent failure | `extract_xquery()` returns `{nodes: [], edges: [], error: "tree-sitter-xquery not installed..."}` when absent (tested at individual extractor level, not through aggregate `extract()`) | Verified without package installed |

## Phases

### Phase 1 — Fork & extend tree-sitter-xquery grammar with MarkLogic constructors

**Status:** ✅ Complete
**Fixes:** R2
**Branch:** `feature/marklogic-json-constructors` on [mrleepee/tree-sitter-xquery](https://github.com/mrleepee/tree-sitter-xquery)
**Commit:** `3b53ef7`

#### Behaviour

- Given XQuery source `object-node { "key": fn:concat("a","b") }`, when parsed by the grammar, then produces a valid AST node (no ERROR nodes)
- Given XQuery source `array-node { 1, 2, 3 }`, when parsed, then produces a valid AST node
- Given XQuery source `number-node { 42 }`, when parsed, then produces a valid AST node
- Given XQuery source `boolean-node { true() }`, when parsed, then produces a valid AST node
- Given XQuery source `null-node {}`, when parsed, then produces a valid AST node
- Given XQuery source `as object-node()` in a function return type, when parsed, then produces a valid `object_node_test` AST node (MarkLogic node test)
- Given the 144-file CAS MarkLogic XQuery corpus, when parsed, then ≥95% of files produce zero ERROR nodes
- Given XQuery source `declare private function foo()`, when parsed, then produces a valid function declaration (MarkLogic `%private` shorthand)
- Given XQuery source `try { ... } catch ($e) { ... }`, when parsed, then produces a valid try/catch with variable binding

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| `object-node { "key": "value" }` | No ERROR nodes | ✅ Pass |
| `object-node { 'key': "value" }` (single-quoted key) | No ERROR nodes | ✅ Pass |
| `object-node { . : map:get($m,.) }` (expression key) | No ERROR nodes | ✅ Pass |
| `object-node {}` (empty) | No ERROR nodes | ✅ Pass |
| `object-node{ "k": 1 }` (tight spacing) | No ERROR nodes | ✅ Pass |
| Nested: `object-node { "k": object-node { "inner": 1 } }` | No ERROR nodes | ✅ Pass |
| Inside FLWOR: `return object-node { "k": $x }` | No ERROR nodes | ✅ Pass |
| `array-node { $x, $y }` | No ERROR nodes | ✅ Pass |
| `number-node { 42 }` | No ERROR nodes | ✅ Pass |
| `boolean-node { fn:true() }` | No ERROR nodes | ✅ Pass |
| `null-node {}` | No ERROR nodes | ✅ Pass |
| `declare function foo() as object-node()` | `object_node_test` node, no errors | ✅ Pass |
| `instance of array-node()` | `array_node_test` node, no errors | ✅ Pass |
| `declare private function foo()` | Function declaration, no errors | ✅ Pass |
| `try { 1 } catch ($e) { 2 }` | Try/catch with variable, no errors | ✅ Pass |
| 144-file CAS corpus | ≥136/144 files clean (95%) | ✅ 139/144 clean (96.5%) |

#### Grammar changes

**Reserved words added:** `object-node`, `array-node`, `number-node`, `boolean-node`, `null-node`

**Computed constructors added to `_computed_constructor`:**
- `comp_object_node_constructor` — uses dedicated `json_object_content` rule (key:value pairs like `map_constructor`, not `enclosed_expr`)
- `comp_array_node_constructor`, `comp_number_node_constructor`, `comp_boolean_node_constructor`, `comp_null_node_constructor` — use `enclosed_expr`

**Node tests added to `_kind_test`:**
- `object_node_test`, `array_node_test`, `number_node_test`, `boolean_node_test`, `null_node_test` — each `seq(keyword, '(', optional(string_literal), ')')` like `document_test`

**Additional MarkLogic extensions:**
- `function_declaration` — added `optional('private')` between `declare` and `repeat($.annotation)`, followed by `'function'` (correct ordering: `declare [private] [%annotations] function`)
- `variable_declaration` — added `optional('private')` for `declare private variable` support
- `catch_clause` — added `seq('(', $.variable, ')')` as alternative to `catch_error_list`
- All 5 MarkLogic reserved words added to `_non_delimiting_word` to preserve identifier usage (`$object-node`, `local:object-node()`, etc.)

#### Not in scope

- MarkLogic-specific function names (xdmp:*, cts:*, etc.) — these are regular function calls and parse fine
- `json:null()` — already parses correctly as a function call
- XQuery Scripting Extension (`try/catch` with `block`/`exit` statements)
- MarkLogic `xdmp:sql` and other extension expressions
- Pre-existing comment parsing edge cases (nested comments with code examples, `~:)` endings) — affects 5/144 files, unrelated to JSON constructors

### Phase 2 — Publish tree-sitter-xquery as PyPI package

**Status:** not started
**Fixes:** R3

#### Behaviour

- Given a fresh Python environment, when `pip install tree-sitter-xquery` is run, then the package installs successfully with a compiled parser for the current platform
- Given the installed package, when `import tree_sitter_xquery as tsx` is executed, then `tsx.language()` returns a PyCapsule pointer consumable by `Language(...)` (matching Graphify's existing extractor pattern)
- Given the installed package, when the language is loaded into a Parser and a minimal XQuery module is parsed, then no errors occur

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| `pip install tree-sitter-xquery` | Exit code 0, package installed | |
| `Language(tree_sitter_xquery.language())` | Returns a Language object with name `xquery` | |
| Parse `xquery version "1.0-ml"; 1` | Root node type `module`, no errors | |

#### Deliverables

- `pyproject.toml` with `tree-sitter>=0.23.0` dependency (Graphify's minimum)
- Pre-built wheels for: macOS ARM64, macOS x86_64, Linux x86_64
- CI workflow (GitHub Actions) to build and publish wheels on tag

#### Not in scope

- Publishing to conda-forge or other registries
- Linux ARM64 or Windows wheels (can add later if needed)
- The `LANGUAGE_VERSION` in `src/parser.c` is 14 — must be regenerated against Graphify's tree-sitter version before publishing

### Phase 3 — Write `extract_xquery()` and register in Graphify

**Status:** not started
**Fixes:** R1, R4, R5, R6, R7, R8b
**Prerequisites:** Phase 2 (R8a — package must be on PyPI before `graphifyy[all]` can include it)

#### Behaviour

- Given a `.xqy` file passed to `extract()`, when the dispatcher looks up the extension, then `extract_xquery` is returned
- Given `xquery version "1.0-ml"; module namespace au = "urn:test"; declare function au:foo($x as xs:string) as xs:string { au:bar($x) }; declare function au:bar($x as xs:string) as xs:string { $x };`, when extracted, then the output contains:
  - A file node with ID `_make_id(file_stem)`, label matching the filename
  - Two function nodes with IDs `_make_id(file_stem, "au:foo")` / `_make_id(file_stem, "au:bar")` (normalized: punctuation stripped, casefolded), labels `au:foo()` and `au:bar()`, metadata `{kind: "function", arity: 1, parameterStrictTyping: 1.0, hasReturnType: true}`, with `contains` edges from the file node
  - A `calls` edge from `au:foo` to `au:bar` with confidence `EXTRACTED`
- Given `import module namespace asc = "urn:asc" at "/lib/asc.xqy";`, when extracted, then the output contains an `imports` edge from the file node with metadata `{namespace: "urn:asc", target_path: "/lib/asc.xqy"}`
- Given `declare variable $MAX as xs:integer := 200;`, when extracted, then the output contains a variable node `$MAX` with a `contains` edge from the file node
- Given a `.xqy` file when `tree-sitter-xquery` is not installed, when `extract_xquery(path)` is called directly, then it returns `{"nodes": [], "edges": [], "error": "tree-sitter-xquery not installed..."}`
- Given the 144-file CAS corpus, when extracted via Graphify, then all files that parse cleanly produce valid nodes+edges dicts

#### Registration changes

All registration happens in this phase (merged with what was previously Phase 4):

| File | Change |
|---|---|
| `graphify/extract.py` | Add `".xqy": extract_xquery` to `_DISPATCH` dict |
| `graphify/extract.py` | Add `extract_xquery()` function following `extract_sql()` / `extract_bash()` pattern |
| `graphify/detect.py` | Add `".xqy"` to `CODE_EXTENSIONS` set |
| `graphify/watch.py` | Pick up extension from `CODE_EXTENSIONS` (no change if already derives from `detect`) |
| `pyproject.toml` | Add `xquery = ["tree-sitter-xquery"]` to `[project.optional-dependencies]` |
| `pyproject.toml` | Add `"tree-sitter-xquery"` to the `all` extra aggregation |
| `uv.lock` | Regenerate lockfile to include tree-sitter-xquery in xquery/all resolution |
| `README.md` | Add XQuery to supported languages table AND optional extras table (alongside `sql`, `dm`, `terraform`) |

#### Verification

| Input | Expected output | Verified result |
|---|---|---|
| `module.xqy` (simple library module) | File node + function nodes with `contains` edges; function IDs via `_make_id(stem, qname)`, labels `au:foo()`, metadata includes `arity`, `parameterStrictTyping`, `hasReturnType` | |
| File with `import module ... at "path"` | `imports` edge with `{namespace, target_path}` in metadata | |
| File with `cts:search()` call | Internal: `calls` edge, confidence `EXTRACTED`. External: emitted as `raw_calls` for symbol resolution pipeline | |
| File with `declare variable $X` | Variable node `$X` + `contains` edge | |
| File with `object-node {}` | No error in output (Phase 1 grammar) | |
| `.xqy` file without tree-sitter-xquery installed | `extract_xquery()` returns error dict; no crash | |
| `collect_files(dir)` with `.xqy` files | Files returned in file list (derives from `_DISPATCH.keys()`) | |
| `graphify detect` on directory with `.xqy` | Files appear in `code` list | |
| `graphify watch` on directory with `.xqy` | Change events emitted for modifications | |
| `pip install graphifyy[xquery]` | Installs tree-sitter-xquery (requires Phase 2) | |
| `pip install graphifyy[all]` | Includes tree-sitter-xquery (requires Phase 2) | |
| Overloaded functions `au:foo#1` and `au:foo#2` | Distinct node IDs via `_make_id(stem, qname)` + arity in metadata; labels both `au:foo()` | |

#### Not in scope

- Cross-file import resolution (resolving `at "/lib/foo.xqy"` to a file node in the corpus) — deferred to a follow-up
- Per-function call attribution with namespace resolution (resolving prefixed calls like `cts:search` to their module) — deferred
- Variable reference tracking (`$x` references) — deferred
- `xdmp:eval` / `xdmp:value` dynamic function detection — deferred
- `.xq` / `.xqm` / `.xql` extensions — rare in MarkLogic ecosystems where `.xqy` is standard; must not be added unless a new requirement is approved

## Constraints

- **One branch per phase.** Branch naming: `feature/xquery-<phase-description>` from the `v8` branch (Graphify's current development branch).
- **Optional dependency.** `tree-sitter-xquery` must be an optional dependency (like `sql = ["tree-sitter-sql"]`), not a core dependency. The extractor must degrade gracefully when the package is absent.
- **Follow existing patterns.** The extractor must follow the same structure as `extract_sql()` or `extract_bash()` — import tree-sitter, parse, walk AST, return `{nodes, edges}`.
- **Test with real corpus.** Verification uses the 144-file CAS MarkLogic XQuery corpus at `/Users/lpollington/Dev/cas/repos/ls-prime-schema-analyser/marklogic/src/main/ml-modules/root/`.
- **Grammar fork ownership.** The forked grammar lives at [mrleepee/tree-sitter-xquery](https://github.com/mrleepee/tree-sitter-xquery) — a permanent namespace for the PyPI package source.
- **Tree-sitter ABI compatibility.** The grammar's `LANGUAGE_VERSION` is currently 14 in `src/parser.c`. Graphify requires `tree-sitter>=0.23.0` and rejects runtimes with `LANGUAGE_VERSION < 14`. Before Phase 2 publishing, the parser must be tested against both Graphify's minimum runtime (`0.23.0`) and the locked runtime to confirm compatibility — regenerating to a newer ABI version would actually force raising the minimum runtime.

## Not In Scope

- **Cross-file import resolution:** Resolving `import module ... at "path"` to actual file nodes requires a two-pass resolution across all extracted files. Deferred as a dependency — needs the single-file extractor working first.
- **Namespace-resolved call edges:** Resolving `cts:search()` to `http://marklogic.com/cts#search` requires a namespace resolution table built from imports and module declarations. Deferred as complexity.
- **`.xq` / `.xqm` / `.xql` extensions:** Rare in MarkLogic ecosystems where `.xqy` is standard. Must not be added in Phase 3 unless a new requirement is approved.
- **XQuery Scripting Extension / MarkLogic Update syntax:** These are rarely used in library modules and would require grammar extensions beyond the JSON constructors.
- **Per-function variable reference tracking:** Tracking `$var-ref` → `declare variable $var` edges is a separate extraction concern deferred to a follow-up.
- **Pre-existing comment parsing edge cases:** The upstream grammar has known issues with deeply nested comments and `~:)` endings (5/144 files). These are independent of MarkLogic extensions and not addressed here.

## Appendix: Investigation Notes

### A1. tree-sitter-xquery grammar evaluation

Tested [grantmacken/tree-sitter-xquery](https://github.com/grantmacken/tree-sitter-xquery) (606-line `grammar.js`, v0.1.2) against the 144-file CAS MarkLogic XQuery corpus.

**Results without modification:**
- 103/144 files (71.5%) parsed with zero errors
- 41/144 files had errors

**Error categorisation (602 total ERROR nodes):**

| Cause | Count | Notes |
|---|---|---|
| `object-node { "key": value }` JSON constructor | 110 | MarkLogic extension, not in XQuery 3.1 |
| `array-node { ... }` JSON constructor | 43 | MarkLogic extension |
| JSON key-value pairs inside object-node (cascading) | ~280 | Consequence of object-node parse failure |
| `number-node {}`, `boolean-node {}`, `null-node {}` | ~10 | MarkLogic extensions |
| Cascading closing braces from object-node blocks | ~137 | Consequence of above |
| `declare private function` | ~4 | MarkLogic `%private` shorthand |
| `catch ($e)` variable binding | ~6 | MarkLogic extension to try/catch |
| `as object-node()` in return types | ~12 | MarkLogic node test syntax |
| Other (xqDoc comments, main-module-no-body edge case) | ~0 | Previously counted as cascading |

**Results after Phase 1 grammar extensions:**
- 139/144 files (96.5%) parsed with zero errors
- 5/144 files still have errors (all pre-existing comment parsing edge cases)

**What works perfectly (verified with isolated tests):**
- All standard XQuery 3.1: FLWOR, typeswitch, arrow expr (`=>`), string concat (`||`), module imports
- Function declarations with any type annotations: `xs:int`, `xs:unsignedLong`, `map:map`, `cts:query`, `json:object`
- `private:` prefix, annotations (`%rest:GET`), xqDoc comments (`(:~ ... :)`)
- `json:null()`, `document { }` constructor, `xdmp:eval()`
- All five MarkLogic JSON node constructors and node tests
- `declare private function` and `catch ($e)` MarkLogic extensions

**Grammar compilation:** The repo includes a pre-compiled `src/parser.c` (8.7MB). Compiling to a shared library and loading via ctypes + tree-sitter 0.25.2 Python bindings works with no modifications to the grammar itself.

**PyPI status:** No `tree-sitter-xquery` package exists on PyPI. The repo has no `pyproject.toml` or `setup.py` — only `package.json` for the Node.js tree-sitter CLI workflow.

### A2. Graphify extractor architecture

Graphify's `extract.py` (11,000+ lines) uses a dispatch pattern:

```python
_DISPATCH: dict[str, Any] = {
    ".py": extract_python,
    ".sql": extract_sql,
    ".bash": extract_bash,
    # ... ~30 languages
}

def _get_extractor(path: Path) -> Any | None:
    return _DISPATCH.get(path.suffix)
```

Each extractor function follows the same pattern (example: `extract_sql`, `extract_bash`):
1. `import tree_sitter_<lang>` — return error dict if not installed
2. Create `Language` and `Parser`
3. Parse the file bytes
4. Walk the AST, collecting nodes and edges into lists
5. Return `{nodes, edges}` (and optionally `raw_calls` for cross-file resolution)

**Node schema:** `{id, label, file_type, source_file, source_location, metadata}`
**Edge schema:** `{source, target, relation, confidence, source_file, source_location, weight}`

**Key XQuery AST node types from tree-sitter-xquery grammar:**
- `module`, `library_module`, `main_module`
- `version_declaration`, `module_declaration`
- `module_import`, `schema_import`
- `function_declaration` (with fields: name via `_EQName`, params via `param_list`, return type via `type_declaration`, body via `enclosed_expr`)
- `variable_declaration` (with field: variable via `variable`)
- `function_call` (with field: name via `_EQName`, args via `arg_list`)
- `var_ref` (with field: name via `_var_name`)
- `flwor_expr`, `let_clause`, `for_clause`, `return_clause`
- `if_expr`
- `string_concat_expr`
- `comment`
- MarkLogic extensions: `comp_object_node_constructor`, `json_object_pair`, `comp_array_node_constructor`, `comp_number_node_constructor`, `comp_boolean_node_constructor`, `comp_null_node_constructor`, `object_node_test`, `array_node_test`, etc.

### A3. ANTLR4 grammar comparison

The code-analyser project uses an ANTLR4 XQuery grammar (890-line lexer + 859-line parser = 1,749 lines). This grammar is **not usable by Graphify** — Graphify is built entirely on tree-sitter. The ANTLR grammar includes:
- Java `@members` actions for brace-counting inside string interpolation
- `rebuild.sh` sed passes to rewrite Java actions into Python
- Hand-edited Python runtime files in `src/python/`

The tree-sitter grammar (606 lines → 645 lines with MarkLogic extensions) is more compact and already compiles to C, making it directly usable via tree-sitter's Python bindings.

The ANTLR grammar does provide a useful reference for MarkLogic extension points — its `mlNodeTest` rules (lines 610-625 of `XQueryParser.g4`) confirmed the node test syntax used in Phase 1.

### A4. MarkLogic JSON node constructor syntax

MarkLogic Server extends XQuery with five JSON node constructors not in the W3C XQuery 3.1 specification:

```xquery
object-node { "key": expr, "key2": expr }   (: JSON object :)
array-node { expr, expr, expr }               (: JSON array :)
number-node { expr }                          (: typed JSON number :)
boolean-node { expr }                         (: typed JSON boolean :)
null-node {}                                  (: JSON null :)
```

**Grammar implementation notes:**

The `object-node` constructor requires a dedicated `json_object_content` rule (not `enclosed_expr`) because its content is JSON-style `"key": value` pairs, not a regular XQuery expression. This mirrors the existing `map_constructor` pattern in the grammar:

```javascript
// object-node uses dedicated content rule (like map_constructor):
comp_object_node_constructor: ($) => seq('object-node', field('content', $.json_object_content)),
json_object_content: ($) => seq('{', optional($.json_object_pair), repeat(seq(',', $.json_object_pair)), '}'),
json_object_pair: ($) => seq(field('key', $._expr_single), ':', field('value', $._expr_single)),

// array-node, number-node, boolean-node, null-node reuse enclosed_expr:
comp_array_node_constructor: ($) => seq('array-node', field('content', $.enclosed_expr)),
```

The CAS corpus uses all variants: double-quoted and single-quoted keys, expression keys (`.` as context item), nested constructors, tight spacing (`object-node{`), and empty constructors. All verified in Phase 1.

### A5. tree-sitter Python packaging pattern

Modern tree-sitter grammar packages on PyPI follow a standard layout. Example from `tree-sitter-sql`:

```
tree-sitter-xquery/
├── pyproject.toml          # Python packaging config
├── setup.py                # Build script (compiles parser.c)
├── tree_sitter_xquery/
│   ├── __init__.py         # Exposes language() function returning PyCapsule
│   └── bindings/
│       └── python/
│           └── tree_sitter_xquery/
│               └── __init__.py
├── src/
│   ├── parser.c            # Pre-compiled parser
│   └── tree_sitter/
│       └── parser.h        # tree-sitter runtime header
├── grammar.js              # Source grammar
└── package.json            # Node metadata (existing)
```

The `tree_sitter_xquery/__init__.py` exposes a `language()` function that returns the tree-sitter Language pointer/PyCapsule, matching the pattern used by Graphify's existing extractors:
```python
import tree_sitter_xquery as tsx
from tree_sitter import Language
LANG = Language(tsx.language())
```

The package targets `tree-sitter>=0.23.0` (Graphify's minimum) and provides pre-built wheels for:
- macOS ARM64 (Apple Silicon)
- macOS x86_64
- Linux x86_64

**Important:** The `LANGUAGE_VERSION` in `src/parser.c` (currently 14) must be regenerated against the target tree-sitter runtime version to avoid ABI incompatibility.

### A6. Review findings incorporated

This spec was reviewed using codex-cli (read-only sandbox). The following findings were incorporated:

| # | Severity | Finding | Resolution |
|---|---|---|---|
| 1 | High | R5 required cross-file resolution but Phase 3 deferred it | Downgraded R5 to namespace/path metadata only; cross-file resolution explicitly deferred |
| 2 | High | R8 didn't require adding to pyproject.toml extras | Added explicit deliverables: pyproject.toml extras, `all` aggregation, README update |
| 3 | High | Phase 1 didn't include MarkLogic node tests (`as object-node()`) | Added node tests to `_kind_test`, verified against corpus |
| 4 | Medium | `object-node` constructor rule insufficient — no JSON pair verification | Added `json_object_content` rule; added 7 explicit verification rows covering all variants |
| 5 | Medium | Error handling didn't match aggregate `extract()` | Clarified: tested at `extract_xquery()` level, not through aggregate `extract()` |
| 6 | Medium | R1 split across Phase 3 & 4; two registration points (`_DISPATCH` + `CODE_EXTENSIONS`) | Merged Phase 4 into Phase 3; added registration table |
| 7 | Medium | Packaging plan inconsistent (Linux ARM excluded vs included); `language()` return type unspecified | Resolved: exclude Linux ARM from both; specified PyCapsule return type |
| 8 | Medium | Function identity missing arity (XQuery = name+arity) | Added arity to node IDs (`au:foo#1`) and metadata |
| 9 | Low | Verification tables too outcome-light | Added specific IDs, metadata, edge confidence, stub node behaviour to Phase 3 table |

### A7. Second-round review findings (grammar)

Grammar changes reviewed by codex-cli against grammar.js diff and MarkLogic docs.

| # | Severity | Finding | Resolution |
|---|---|---|---|
| G1 | High | MarkLogic reserved words not in `_non_delimiting_word` — breaks `$object-node`, `local:object-node()`, `<object-node/>`, `%object-node` | ✅ Fixed: added all 5 words to `_non_delimiting_word` in alphabetical order |
| G2 | Medium | `declare %a private %b function` accepted but MarkLogic only supports `declare private function` | ✅ Fixed: restructured to `declare optional('private') repeat(annotation) 'function'` |
| G3 | Medium | `declare private variable` not supported | ✅ Fixed: added `optional('private')` to `variable_declaration` |
| G4 | Low | `json_object_content` approach validated as correct vs `enclosed_expr` | Confirmed correct — `:` is not an XQuery operator in expression context |
| G5 | Low | `catch($var)` safe — no conflict with `catch_error_list` | Confirmed safe |

### A8. Second-round review findings (spec)

Spec reviewed by codex-cli against Graphify codebase (extract.py, detect.py, watch.py, pyproject.toml, tests).

| # | Severity | Finding | Resolution |
|---|---|---|---|
| S1 | High | `UNRESOLVED` not a valid confidence — pipeline only accepts `EXTRACTED`, `INFERRED`, `AMBIGUOUS` | ✅ Fixed: R6 now uses `raw_calls` for external callees; no new confidence values |
| S2 | High | Function IDs use `_make_id()` which strips punctuation and casefolds; `au:foo#1` would become `aufoo1` | ✅ Fixed: IDs defined as `_make_id(file_stem, qname)`, labels human-readable `au:foo()`, arity in metadata |
| S3 | High | R8 depends on both Phase 2 (publishing) and Phase 3 (wiring) | ✅ Fixed: split into R8a (Phase 2 prerequisite) and R8b (Phase 3 extractor) |
| S4 | Medium | Package name is `graphifyy` (double-y), not `graphify` | ✅ Fixed: all pip commands now use `graphifyy[xquery]`, `graphifyy[all]` |
| S5 | Medium | Phase 3 verification missing `collect_files()` directory test | ✅ Fixed: added `collect_files(dir)` verification row |
| S6 | Medium | Phase 1 deliverables (node tests, private, catch) not traced to R2 | ✅ Fixed: R2 now explicitly covers all Phase 1 extensions |
| S7 | Medium | README deliverable missing optional extras table | ✅ Fixed: registration table now includes README extras table + uv.lock |
| S8 | Low | Grammar ABI warning imprecise — LANGUAGE_VERSION 14 may already be compatible | ✅ Fixed: constraint now says "test against minimum and locked runtime" not "regenerate" |
