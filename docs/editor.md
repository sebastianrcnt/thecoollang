# Editor integration

Start `cool lsp` as a language server over standard input/output. Configure your
LSP client to use that command for `.cool` files and a workspace containing
`cool.mod`. The installed development archive includes the server; a source
checkout can also run `tools/cool lsp`. Standard output is reserved for framed
JSON-RPC messages. No editor extension is required by the server itself.

The current implementation supplies diagnostics, definition lookup for
successfully checked packages, and compiler-driven completion. Broader recovery
from invalid code and the documented unsupported contexts remain open for the
1.0 tooling gate. A real Neovim client integration test is included.

## Supported behavior

- Initialize/shutdown/exit and local `file:` documents.
- Open/close synchronization, full or incremental edits, and save/watch events.
- UTF-16 positions, including supplementary Unicode characters and CRLF lines.
- Ordered edits within a notification and rejection of stale document versions.
- Native lexer/parser/type/ownership diagnostics with source byte ranges mapped
  into editor positions. The same frontend checks `cool check` inputs.
- Definition lookup for local reads/writes, parameters, function calls, methods,
  named types and fields/enum variants resolved by the compiler. Generic calls
  point to their source template declaration. Shadowed bindings retain their
  individual declaration identity.
- Completion of visible locals/parameters, package functions/types, import
  aliases, primitive types, public members, enum variants and receiver methods.
  Candidates respect package visibility, lexical scopes and moved bindings.
  Type positions exclude functions and value bindings; statement positions also
  offer keywords, with break/continue limited to loops.
- Unsaved buffers across package dependencies and newly opened files in an
  existing package. Closing a buffer resumes its disk contents and clears stale
  diagnostics. Saving notifications do not write files on the client's behalf.

Analysis uses offline, frozen module resolution. Download dependencies and
update `cool.sum` with ordinary module commands before opening the project.
Missing dependencies or checksums become diagnostics; analysis does not fetch
modules or rewrite source files, `cool.mod` or `cool.sum`. Temporary buffer
snapshots are removed after analysis and never enter the persistent scan cache.
Unchanged disk-file metadata may use the ordinary compiler-versioned scan cache.

Each open package is checked with its dependencies and test files. The compiler
currently reports its first failure per analyzed package. Analysis is synchronous;
individual native scanning/checking processes have a 20-second timeout. Cancel
notifications are accepted but do not interrupt an ongoing check. Non-file URIs,
remote editing, background indexing, hover and rename are not advertised as supported capabilities.

Definition lookup uses the current successful analysis only. A failed package
check discards that package's index; it does not return locations from an older
buffer version. Unresolved locations return an empty result. Import aliases,
builtins and uninstantiated generic bodies do not yet have definition records.
Generic bodies acquire records when the compiler specializes them. Definition
lookup in incomplete/invalid programs and full generic-template indexing still
need work before the tooling gate can close.

## Completion while editing

`textDocument/completion` supports explicit requests and the `.` trigger. It uses
fresh unsaved snapshots and returns UTF-16 text edits replacing the identifier at
the cursor, including its suffix when the cursor is in the middle of a word.
Candidates are filtered by the typed prefix and deduplicated. Comments and string
contents produce no candidates.

A separate compiler process inserts a marker into its temporary token stream
when there is no identifier and closes unfinished blocks for the declaration
scan. The ordinary expression/type parser then reaches the marker with actual
locals and receiver types, emits candidates and exits without executing user
code. This supports partial expressions, empty member selections and unfinished
function blocks. It does not change files or the diagnostic analysis's AST.

After collecting declarations and checking signatures, completion checks the
requested function body first. Errors in other function bodies, including
dependency bodies, therefore do not prevent completion. Normal diagnostics still
report those errors.

This is bounded recovery, not a general error-tolerant parser: errors in earlier
statements of the requested function, invalid declarations/signatures, missing
dependencies and lexical errors may prevent the cursor from being reached. Uninstantiated generic bodies,
top-level declarations and import path strings still need completion support.
The server returns an empty incomplete list when scanning/checking fails. Each
request uses synchronous analysis with the same native-process timeout; requests
are not yet cancellable or debounced.

## Neovim setup

The release includes `editors/neovim/cool.lua`, tested with Neovim 0.12.5's
built-in LSP client. It registers `.cool` files, finds the package workspace via
`cool.mod`, starts `cool lsp`, and enables native completion with automatic
triggering. It does not install plugins or modify your editor configuration.
Add this to your own Neovim configuration after putting `cool` on PATH:

```lua
local cool = vim.fn.exepath('cool')
assert(cool ~= '', 'cool must be on PATH')
local executable = assert(vim.uv.fs_realpath(cool))
local root = vim.fs.dirname(vim.fs.dirname(executable))
dofile(root .. '/editors/neovim/cool.lua').setup({ cmd = { cool, 'lsp' } })
```

The same root lookup works for `tools/cool` in a checkout and the installed
`bin/cool` symlink. You can also load the Lua file using an explicit absolute
path and pass `{ cmd = { '/absolute/path/to/cool', 'lsp' } }`. The optional table
accepts ordinary Neovim LSP configuration fields; supplied fields override the
module defaults. No keymaps are replaced. Neovim's definition and completion
commands remain available through its built-in LSP APIs.

Real-client checks are separate from the compiler suite:

```sh
make editor-client-fetch       # pinned, checksummed client downloaded into build/
make editor-client-test
make editor-client-sanitize-test
make editor-distribution-test
# Or use an existing client without downloading:
make editor-client-test NVIM=/absolute/path/to/nvim
```

The fetch helper currently targets Apple Silicon macOS, the first release host.
Ordinary `make test` does not download software. The headless test uses Neovim's
actual filetype detection, workspace attachment, incremental synchronization,
UTF-16 conversion, diagnostic store, request client and text-edit application.
It tests CRLF/emoji positions, cross-package definitions, applying a completion
edit, shared-client unsaved dependency buffers, close/reset, standalone files
outside modules and graceful shutdown.
Source and module files must remain unchanged. Config/data/state/cache directories
are temporary, and user init/runtime overrides are excluded. This is native
client integration evidence, not a visual popup/UI acceptance test.

The same test runs against the instrumented ASan frontend and the checksummed,
read-only installed distribution with seed/make unavailable. CI downloads the
pinned client and runs these explicit targets; remote CI still requires observation.
The client archive is a test dependency, not part of the Cool distribution.

References: [Neovim LSP documentation](https://neovim.io/doc/user/lsp/) and
[the pinned Neovim 0.12.5 release](https://github.com/neovim/neovim/releases/tag/v0.12.5).

## Implementation and verification

`compiler/29-editor.cool` and bootstrap `language/Editor.cool` serialize native
errors and semantic references. `diagnostics-bundle` checks a bundle;
`editor-index-bundle` additionally indexes references after successful checking; `editor-scan-bundle` preserves
structured lexer errors during import discovery.
`compiler/30-completion.cool` and `language/Completion.cool` implement
`editor-complete-bundle <manifest> <file> <byte-offset>`; native parser hooks
select candidates at the cursor. The lexer marks comment ranges for exclusion. `tools/lsp_server.py` handles
JSON-RPC transport, temporary overlays and UTF-8-byte to UTF-16 conversion; it
contains no Cool parser or type checker. The driver retains original package
paths for resolution while passing snapshot paths to the compiler.

`make lsp-test` checks both frontends: fragmented framing, UTF-16/CRLF locations,
sequential changes, unsaved imports and files, stale versions, close/reset,
lexer/EOF errors, shadowed bindings, assignments, parameters, imported types,
fields, methods, generic calls, index invalidation, scoped and qualified
completion, private/moved/out-of-scope exclusions, enum/generic receivers, partial
blocks, comments/strings, and source/manifest preservation. `make lsp-sanitize-test`
adds the compiler-instrumented ASan frontend. `make distribution-test` checks
server startup, diagnostics, cross-package definition lookup and completion from a read-only installation with no usable
seed or make command. CI includes the sanitizer target; local success does not
constitute observed remote CI success.

Protocol reference: [Language Server Protocol 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/),
including [ordered document changes](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/textDocument/didChange.md).
