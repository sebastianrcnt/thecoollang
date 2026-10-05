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
Its declared module identity must match when used.

The nearest `cool.work` found from the manifest directory upwards supplies local
workspace modules. It accepts an optional, single `cool 1.0` and `use DIRECTORY`
or a multiline `use (` block. Paths are relative to the workspace file. Unknown
or unsupported language directives, malformed/nested/unclosed blocks and
unmatched closing parentheses are errors. Workspace entries override matching
manifest replacements, as in the existing resolver. Local workspaces/replacements
remain mutable and are outside immutable dependency checksum verification.

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

MVS traverses declared requirements and selects the greatest required version of
each module, including transitive requirements from every visited version.
`cool.mod` stores minimum requirements; it does not by itself pin an exact whole
graph. Local replacement/workspace sources have separate mutable semantics.

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
`make`. Network transport credentials, public remote availability, signed tags
and a release-wide module/distribution gate remain outside this local regression.
