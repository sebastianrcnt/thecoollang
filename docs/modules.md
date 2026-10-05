# Module file and resolution contract (development draft)

Cool uses directory packages and minimum version selection (MVS). These rules
specify the current development format; they do not declare a frozen 1.0 release
or compatibility with Go's module proxy/checksum protocols.

## Manifest and workspace files

`cool.mod` requires one `module PATH`. An optional, single `cool 1.0` directive
selects the currently supported language/manifest interpretation; absence means
1.0. This language selector is distinct from the installed toolchain's
`0.1.0-dev` distribution version. Other language selectors and unknown directives
are errors, including proposed future `format` directives.

Requirements have the form `require PATH VERSION`, and local replacements have
`replace PATH => LOCAL_DIRECTORY`. `require` and `replace` also accept multiline
parenthesized blocks. Duplicate module/require/replace/cool declarations,
malformed directives, nested blocks and unclosed blocks are errors. Shell-style
quoting preserves local paths containing spaces; `//` starts a comment only
outside quotes. Local replacement paths are relative to the manifest directory
unless absolute. A replacement supplies source, not a version requirement.
Its manifest must exist and declare the matching module identity during graph
resolution, even when no explicit version requirement names that local root.

The nearest `cool.work` found from the manifest directory upwards supplies local
workspace modules. It accepts an optional, single `cool 1.0` and `use DIRECTORY`
or a multiline `use (` block. Paths are relative to the workspace file. Unknown
or unsupported language directives, malformed/nested/unclosed blocks and
unmatched closing parentheses are errors. Workspace entries override matching
manifest replacements, as in the existing resolver. A workspace entry declaring
the main module identity must point to the actual invoking manifest directory;
a different directory is an explicit conflicting-main-identity error. A main-identity
local replacement must likewise point to the invoking root. Two workspace
entries for another module may repeat the same directory, but conflicting
directories for that identity are rejected rather than silently selecting the last. Repeating
the same main root does not seed its requirements twice. Local workspaces,
replacements and the main checkout remain mutable and are outside immutable
dependency checksum verification.

## Versions and fetching

A requirement version is `vMAJOR.MINOR.PATCH`, optionally followed by a SemVer
prerelease suffix. Leading zeroes in numeric components or numeric prerelease
identifiers, empty prerelease identifiers, unprefixed versions, commit pseudo
versions and build metadata (`+...`) are unsupported and rejected. Ordering uses
numeric major/minor/patch and numeric prerelease identifiers; a release sorts
above its prereleases. The implementation therefore supports a documented
subset of SemVer syntax, not every SemVer version spelling.

For major 2 or later, the module path must end in its exact `/vMAJOR` suffix,
including majors 10, 19, 100 and above. Fetching removes that suffix to identify
the Git repository, then archives `refs/tags/VERSION`. Remote repository identities
currently require `host/owner/repo` and fetch over HTTPS, or SSH when
`COOL_GIT_SSH=1`. Downloaded, cached and vendored manifests must declare the exact
requested module identity. This prevents cached source from being silently
assigned a different import identity.

MVS starts with the main manifest and every addressable workspace/local
replacement manifest as unversioned graph roots. Each root's outgoing
requirements participate, including a local module with no explicit `require`
in the main manifest and workspace roots not imported by the current package.
Consequently all configured local root manifests must be present and valid, and
their declared dependencies are resolved eagerly. An addressable root alone
does not invent a selected version or checksum for that mutable module. When an
actual version requirement names a local root, selection records the greatest
required version while that root still supplies its local source.

The resolver selects the greatest required version of other modules, including
transitive requirements from every visited version. A dependency's requirement
on a tagged version of the main module is syntax/version validated but does not
fetch that tag, select a main-module version, demand its checksum or replace the
invoking checkout. The main root's outgoing requirements were already seeded.
This fixes source identity to the invoking directory; it does not promise that
mutable main/local file contents are frozen during a build.

`cool.mod` stores minimum requirements; it does not by itself pin an exact whole
graph. Requirements declared in a dependency's manifest participate in MVS;
that dependency's own replacement directives do not override the invoking main
manifest/workspace replacement policy.

## Checksums, frozen builds and vendor format

`cool.sum` is a line-based verification record: `MODULE VERSION h1:BASE64`.
Every nonblank row must have exactly three fields, a valid module/version pair,
and canonical Base64 encoding of a 32-byte SHA-256 digest. Unknown hash prefixes,
malformed hashes and conflicting duplicate rows are errors even when that row
is not selected by the current graph. Identical duplicate checksum rows remain
accepted. An unsupported future header is rejected as an invalid row.

The Cool `h1` tree hash includes sorted relative file names, byte lengths and
contents; `.git` metadata is excluded and symlinks in module contents are
rejected. This is Cool's existing algorithm, not Go's `h1` protocol. Ordinary
resolution records previously unseen immutable dependencies; an existing
checksum mismatch fails. `--frozen` requires already recorded checksums and
`--offline` prohibits fetching a missing cache entry. Neither flag claims that
local workspace/replacement files are immutable. A checksum first recorded from
a repository is a local trust decision; there is no public checksum transparency
service or authentication of Git tag authors.

The current `vendor/cool.vendor.json` format is a plain JSON object mapping module
identities to selected version strings. Duplicate keys, nonobject roots,
nonstring versions, invalid identities and version/path mismatches are rejected.
A future envelope such as `{"format":2,"modules":{...}}` is explicitly rejected,
not treated as the existing module map. Selected sources live at `vendor/PATH`;
other visited versions live at `vendor/.versions/PATH@VERSION`. Both must pass
identity and checksum checks. This index is not an independent graph lockfile.

There is currently no `cool.lock` protocol or exact-resolution lockfile command.
No file with that name is read or interpreted as a lock. The compatibility
policy's requirement to reject unsupported lockfile formats applies if such a
protocol is introduced; the current implementation must not be advertised as
providing exact graph locking merely because it supports `--frozen`.

## Reproduction

```sh
python3 tools/test_module_contract.py
```

The contract regression exercises malformed/future manifests and workspaces,
quoted replacement paths, all checksum rows, vendor formats, module identity,
major suffixes and SemVer prerelease ordering. Temporary real Git repositories
provide tagged `/v10` sources through Git's URL rewrite mechanism. The production
HTTPS clone/archive path is exercised without a network service or subprocess
mocking; two graph paths request different prereleases and MVS selects the higher
one. The test checks immutable cache/offline/frozen resolution, checksum tampering,
and actual CLI checking/interpreter execution using a copied frontend with no
`make`. Additional replace/workspace fixtures have an empty main requirement
list, an imported local library and an unused local peer whose requirements
raise a shared dependency's selected version. Offline/frozen CLI output checks
that this transitive dependency resolves and that a requirement back to a tagged
main module cannot shadow the invoking checkout's package. Missing/tampered
transitive cache entries and conflicting workspace main identities are rejected.
Set `COOL_FRONTEND` to pin the frontend that the test copies into its private
fixture. Network transport credentials, public remote availability, signed tags
and a release-wide module/distribution gate remain outside this local regression.
