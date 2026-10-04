# Editor integration

Start `cool lsp` as a language server over standard input/output. Configure your
LSP client to use that command for `.cool` files and a workspace containing
`cool.mod`. The installed development archive includes the server; a source
checkout can also run `tools/cool lsp`. Standard output is reserved for framed
JSON-RPC messages. No editor extension is required by the server itself.

The current implementation supplies diagnostics and definition lookup for
successfully checked packages. Completion remains mandatory work for the 1.0
developer-tools gate.

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
remote editing, background indexing, hover, rename and completion
are not advertised as supported capabilities.

Definition lookup uses the current successful analysis only. A failed package
check discards that package's index; it does not return locations from an older
buffer version. Unresolved locations return an empty result. Import aliases,
builtins and uninstantiated generic bodies do not yet have definition records.
Generic bodies acquire records when the compiler specializes them. Definition
lookup in incomplete/invalid programs and full generic-template indexing still
need work before the tooling gate can close.

## Implementation and verification

`compiler/29-editor.cool` and bootstrap `language/Editor.cool` serialize native
errors and semantic references. `diagnostics-bundle` checks a bundle;
`editor-index-bundle` additionally indexes references after successful checking; `editor-scan-bundle` preserves
structured lexer errors during import discovery. `tools/lsp_server.py` handles
JSON-RPC transport, temporary overlays and UTF-8-byte to UTF-16 conversion; it
contains no Cool parser or type checker. The driver retains original package
paths for resolution while passing snapshot paths to the compiler.

`make lsp-test` checks both frontends: fragmented framing, UTF-16/CRLF locations,
sequential changes, unsaved imports and files, stale versions, close/reset,
lexer/EOF errors, shadowed bindings, assignments, parameters, imported types,
fields, methods, generic calls, index invalidation, and source/manifest preservation. `make lsp-sanitize-test`
adds the compiler-instrumented ASan frontend. `make distribution-test` checks
server startup, diagnostics and cross-package definition lookup from a read-only installation with no usable
seed or make command. CI includes the sanitizer target; local success does not
constitute observed remote CI success.

Protocol reference: [Language Server Protocol 3.17](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/),
including [ordered document changes](https://raw.githubusercontent.com/microsoft/language-server-protocol/gh-pages/_specifications/lsp/3.17/textDocument/didChange.md).
