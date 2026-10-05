# Standalone Cool host toolchain (Apple silicon macOS).
.DEFAULT_GOAL := all
COOLC_SEED := $(abspath coolc/seed/Compiler.BIN)
.PHONY: all native-host test coolc-test codegen-test checks-test behavior-test fmt-test cli-test bootstrap-check clean
all: build/cool build/coolc build/hcfmt.BIN
native-host: build/coolc
build:
	mkdir -p build
build/cool: tools/cool | build
	ln -sf ../tools/cool $@
build/coolc: language/repl_io.h language/args.h language/ffi.h language/numeric.h language/memory.h coolc/Host/native.c coolc/Host/warm_net.h coolc/Host/warm_task.h coolc/Host/warm_file.h coolc/Host/except.S | build
	clang -std=c11 -Wall -Wextra -Werror -O2 -fno-omit-frame-pointer -ffixed-x28 $(filter %.c %.S,$^) -lffi -o $@
build/coolc-x86_64: language/repl_io.h language/args.h language/ffi.h language/numeric.h language/memory.h coolc/Host/native.c coolc/Host/x86.S coolc/Host/x86-native.h coolc/Host/warm_net.h coolc/Host/warm_task.h coolc/Host/warm_file.h | build
	clang -arch x86_64 -std=c11 -Wall -Wextra -Werror -O2 -fno-omit-frame-pointer coolc/Host/native.c coolc/Host/x86.S -lffi -o $@
build/hcfmt.BIN: coolc/Fmt/Native.cool coolc/Fmt/HCFmt.cool coolc/Fmt/HCTok.cool coolc/seed/Compiler.BIN build/coolc | build
	COOLC_COMPILER_BIN="$(COOLC_SEED)" gtimeout 45 build/coolc coolc/Fmt/Native.cool $@ > build/hcfmt-compile.log 2>&1
	tail -1 build/hcfmt-compile.log
codegen-test: build/coolc build/coolc-x86_64
	python3 tools/native/codegen.py
checks-test: build/coolc
	tools/native/checks.sh
behavior-test: build/coolc
	tools/native/behavior.sh
fmt-test: build/hcfmt.BIN
	tools/hcfmt.sh --selftest
cli-test: all
	python3 tools/test_cli.py
coolc-test: codegen-test checks-test behavior-test
	coolc/Host/test.sh
test: coolc-test fmt-test cli-test
bootstrap-check: build/coolc
	tools/native/bootstrap.sh
clean:
	rm -rf build

LANGUAGE_SRC := $(wildcard language/*.cool)
build/language.BIN: $(LANGUAGE_SRC) build/coolc coolc/seed/Compiler.BIN | build
	COOLC_COMPILER_BIN="$(COOLC_SEED)" gtimeout 60 build/coolc language/Native.cool $@ > build/language-compile.log 2>&1 || { cat build/language-compile.log; exit 1; }
.PHONY: language-test
language-test: build/language.BIN
	python3 tools/test_language.py
build/language-runtime.o: language/runtime.c language/numeric.h language/memory.h language/args.h | build
	clang -std=c11 -Wall -Wextra -Werror -O2 -c $< -o $@
build/language-runtime.dylib: language/runtime.c language/numeric.h language/memory.h language/args.h | build
	clang -std=c11 -Wall -Wextra -Werror -O2 -dynamiclib $< -o $@
all: build/language.BIN build/language-runtime.o
.PHONY: project-test
project-test: build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_projects.py
test: language-test project-test
.PHONY: repl-test
repl-test: build/language.BIN
	python3 tools/test_repl.py
test: repl-test
.PHONY: developer-tools-test
developer-tools-test: build/language.BIN
	python3 tools/test_developer_tools.py
test: developer-tools-test

.PHONY: benchmark
benchmark: all
	python3 tools/bench_language.py --output build/language-benchmark.json

.PHONY: aggregate-test
aggregate-test: build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_aggregates.py
test: aggregate-test

.PHONY: generic-test
generic-test: build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_generics.py
test: generic-test

.PHONY: ownership-test
ownership-test: build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_ownership.py
test: ownership-test

# New-language compiler, built by the bootstrap frontend and then by itself.
build/compiler-host.o: compiler/host.c language/repl_io.h language/ffi.h language/memory.h language/numeric.h | build
	clang -std=c11 -Wall -Wextra -Werror -O2 -c $< -o $@
COMPILER_SRC := $(wildcard compiler/*.cool)
build/compiler.sources: $(COMPILER_SRC) tools/compiler_sources.py | build
	python3 tools/compiler_sources.py $@
build/compiler-stage1.ll: build/compiler.sources $(COMPILER_SRC) build/language.BIN | build
	build/coolc --run build/language.BIN llvm-bundle build/compiler.sources $@
build/compiler-stage1: build/compiler-stage1.ll build/compiler-host.o build/language-runtime.o
	clang -Wno-override-module -O2 $^ -lffi -o $@
build/compiler-stage2.ll: build/compiler.sources $(COMPILER_SRC) build/compiler-stage1
	build/compiler-stage1 llvm-bundle build/compiler.sources $@
build/cool-compiler: build/compiler-stage2.ll build/compiler-host.o build/language-runtime.o
	clang -Wno-override-module -O2 $^ -lffi -o $@
all: build/cool-compiler
.PHONY: selfhost-check
selfhost-check: build/cool-compiler
	python3 tools/test_selfhost.py
language-test aggregate-test ownership-test generic-test project-test repl-test developer-tools-test: build/cool-compiler

.PHONY: export-test
export-test: build/cool-compiler build/language-runtime.o
	python3 tools/test_exports.py
test: export-test selfhost-check

.PHONY: stdlib-test
stdlib-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_stdlib.py
test: stdlib-test

.PHONY: owner-evaluation-test
owner-evaluation-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_owner_evaluation.py
test: owner-evaluation-test

.PHONY: collection-fuzz-test collection-sanitize-test
collection-fuzz-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_collection_fuzz.py
collection-sanitize-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_collection_fuzz.py --sanitize
test: collection-fuzz-test

.PHONY: raw-address-test
raw-address-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_raw_address.py
test: raw-address-test

.PHONY: references-test
references-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_references.py
test: references-test

.PHONY: safe-vector-test
safe-vector-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_safe_vector.py
test: safe-vector-test

.PHONY: text-test text-sanitize-test
text-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_text.py
text-sanitize-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_text.py --sanitize
test: text-test

.PHONY: map-test map-sanitize-test
map-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_map_api.py
	python3 tools/test_map.py
map-sanitize-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_map_api.py
	python3 tools/test_map.py --sanitize
test: map-test

.PHONY: driver-cache-test
driver-cache-test: build/cool-compiler
	python3 tools/test_driver_cache.py
test: driver-cache-test

.PHONY: json-test json-sanitize-test
json-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_json.py
json-sanitize-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_json.py --sanitize
test: json-test

.PHONY: process-test process-sanitize-test
process-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_process.py
process-sanitize-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_process.py --sanitize
test: process-test

.PHONY: path-test path-sanitize-test
path-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_path.py
path-sanitize-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_path.py --sanitize
test: path-test

.PHONY: methods-test
methods-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_methods.py
test: methods-test

.PHONY: distribution-test package-dev
distribution-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_distribution.py
package-dev: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/package_release.py

.PHONY: reference-sets-test
reference-sets-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_reference_sets.py
test: reference-sets-test

.PHONY: stored-references-test
stored-references-test: build/cool-compiler
	python3 tools/test_stored_references.py
test: stored-references-test

.PHONY: stored-references-sanitize-test
stored-references-sanitize-test: build/cool-compiler
	python3 tools/test_stored_references.py --sanitize

.PHONY: nested-references-test tracked-iteration-test tracked-iteration-sanitize-test
nested-references-test: build/cool-compiler
	python3 tools/test_nested_references.py
tracked-iteration-test: build/cool-compiler
	python3 tools/test_tracked_iteration.py
tracked-iteration-sanitize-test: build/cool-compiler
	python3 tools/test_tracked_iteration.py --sanitize
test: nested-references-test tracked-iteration-test

.PHONY: loan-layers-test
loan-layers-test: build/cool-compiler
	python3 tools/test_loan_layers.py
test: loan-layers-test

.PHONY: exclusive-storage-test
exclusive-storage-test: build/cool-compiler
	python3 tools/test_exclusive_storage.py
test: exclusive-storage-test

.PHONY: slice-loans-test slice-loans-sanitize-test
slice-loans-test: build/cool-compiler
	python3 tools/test_slice_loans.py
slice-loans-sanitize-test: build/cool-compiler
	python3 tools/test_slice_loans.py --sanitize
test: slice-loans-test

.PHONY: repl-loans-test
repl-loans-test: build/cool-compiler
	python3 tools/test_repl_loans.py
test: repl-loans-test

.PHONY: repl-loans-sanitize-test
repl-loans-sanitize-test: build/cool-compiler
	python3 tools/test_repl_loans.py --sanitize

.PHONY: repl-packages-test
repl-packages-test: build/cool-compiler
	python3 tools/test_repl_packages.py
test: repl-packages-test

.PHONY: repl-packages-sanitize-test
repl-packages-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_repl_packages.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: repl-storage-test repl-storage-sanitize-test
repl-storage-test: build/cool-compiler build/language.BIN
	python3 tools/test_repl_storage.py
test: repl-storage-test
repl-storage-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_repl_storage.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: repl-tokens-test repl-tokens-sanitize-test
repl-tokens-test: build/cool-compiler build/language.BIN
	python3 tools/test_repl_tokens.py
test: repl-tokens-test
repl-tokens-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_repl_tokens.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: repl-functions-test repl-functions-sanitize-test
repl-functions-test: build/cool-compiler build/language.BIN
	python3 tools/test_repl_functions.py
test: repl-functions-test
repl-functions-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_repl_functions.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: repl-types-test repl-types-sanitize-test
repl-types-test: build/cool-compiler build/language.BIN
	python3 tools/test_repl_types.py
test: repl-types-test
repl-types-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_repl_types.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: repl-project-test repl-project-sanitize-test
repl-project-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_repl_project.py
test: repl-project-test
repl-project-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_repl_project.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: lsp-test lsp-sanitize-test
lsp-test: build/cool-compiler build/language.BIN
	python3 tools/test_lsp.py
test: lsp-test
lsp-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_lsp.py --frontend build/repl-loans-asan/cool-compiler

# Real-editor tests are explicit: ordinary make test never downloads a client.
NVIM ?= $(CURDIR)/build/editor-client/nvim-macos-arm64/bin/nvim
.PHONY: editor-client-fetch editor-client-test editor-client-sanitize-test editor-distribution-test
editor-client-fetch:
	python3 tools/fetch_test_neovim.py
editor-client-test: build/cool-compiler
	python3 tools/test_neovim.py --nvim "$(NVIM)"
editor-client-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_neovim.py --nvim "$(NVIM)" --frontend build/repl-loans-asan/cool-compiler --report-name neovim-sanitize
editor-distribution-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_distribution.py --nvim "$(NVIM)"

.PHONY: integer-tokens-test
integer-tokens-test: build/cool-compiler build/language.BIN
	python3 tools/test_integer_tokens.py
test: integer-tokens-test

.PHONY: integer-tokens-sanitize-test
integer-tokens-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_integer_tokens.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: input-bytes-test input-bytes-sanitize-test
input-bytes-test: build/cool-compiler build/language.BIN
	python3 tools/test_input_bytes.py
test: input-bytes-test
input-bytes-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_input_bytes.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: expressions-test expressions-sanitize-test
expressions-test: build/cool-compiler build/language.BIN
	python3 tools/test_expressions.py
test: expressions-test
expressions-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_expressions.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: integer-semantics-test integer-semantics-sanitize-test
integer-semantics-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_integer_semantics.py
test: integer-semantics-test
integer-semantics-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_integer_semantics.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: float-conversions-test float-conversions-sanitize-test
float-conversions-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_float_conversions.py
test: float-conversions-test
float-conversions-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_float_conversions.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: float-literals-test float-literals-sanitize-test
float-literals-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_float_literals.py
test: float-literals-test
float-literals-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_float_literals.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: declarations-test declarations-sanitize-test
declarations-test: build/cool-compiler build/language.BIN
	python3 tools/test_declarations.py
test: declarations-test
declarations-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_declarations.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: control-flow-test control-flow-sanitize-test
control-flow-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_control_flow.py
test: control-flow-test
control-flow-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_control_flow.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: primary-forms-test primary-forms-sanitize-test
primary-forms-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_primary_forms.py
test: primary-forms-test
primary-forms-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_primary_forms.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: package-rules-test package-rules-sanitize-test
package-rules-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_package_rules.py
test: package-rules-test
package-rules-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_package_rules.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: layout-contract-test layout-contract-sanitize-test
layout-contract-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_layout_contract.py
test: layout-contract-test
layout-contract-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_layout_contract.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: source-utf8-test source-utf8-sanitize-test
source-utf8-test: build/cool-compiler build/language.BIN
	python3 tools/test_source_utf8.py
test: source-utf8-test
source-utf8-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_source_utf8.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: template-body-test template-body-sanitize-test
template-body-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_template_body.py
test: template-body-test
template-body-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_template_body.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: coercion-test coercion-sanitize-test
coercion-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_coercion.py
test: coercion-test
coercion-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_coercion.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: module-contract-test
module-contract-test: build/cool-compiler
	python3 tools/test_module_contract.py
test: module-contract-test

.PHONY: template-aggregate-test template-aggregate-sanitize-test
template-aggregate-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_template_aggregate.py
test: template-aggregate-test
template-aggregate-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_template_aggregate.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: float-arithmetic-test float-arithmetic-sanitize-test
float-arithmetic-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_float_arithmetic.py
test: float-arithmetic-test
float-arithmetic-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_float_arithmetic.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: slice-descriptors-test slice-descriptors-sanitize-test
slice-descriptors-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_slice_descriptors.py
test: slice-descriptors-test
slice-descriptors-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_slice_descriptors.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: repl-lifecycle-test
repl-lifecycle-test: build/cool-compiler build/compiler-host.o build/language-runtime.o
	python3 tools/test_repl_lifecycle.py --output build/repl-lifecycle-audit.json
test: repl-lifecycle-test

.PHONY: template-names-test template-names-sanitize-test
template-names-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_template_names.py
test: template-names-test
template-names-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_template_names.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: repl-jit-lifecycle-test
repl-jit-lifecycle-test: build/cool-compiler build/compiler-host.o build/language-runtime.o
	python3 tools/test_repl_jit_lifecycle.py --output build/repl-jit-lifecycle-audit.json
test: repl-jit-lifecycle-test

.PHONY: repl-holes-test repl-holes-sanitize-test
repl-holes-test: build/cool-compiler build/language.BIN
	python3 tools/test_repl_holes.py
test: repl-holes-test
repl-holes-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_repl_holes.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: mixed-owned-references-test mixed-owned-references-sanitize-test
mixed-owned-references-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_mixed_owned_references.py
test: mixed-owned-references-test
mixed-owned-references-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_mixed_owned_references.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: heap-borrows-test heap-borrows-sanitize-test
heap-borrows-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_heap_borrows.py
test: heap-borrows-test
heap-borrows-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_heap_borrows.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: borrow-graphs-test borrow-graphs-sanitize-test
borrow-graphs-test: build/cool-compiler build/language.BIN build/compiler-host.o build/language-runtime.o
	python3 tools/test_borrow_graphs.py
test: borrow-graphs-test
borrow-graphs-sanitize-test: repl-loans-sanitize-test build/language.BIN build/compiler-host.o build/language-runtime.o
	python3 tools/test_borrow_graphs.py --frontend build/repl-loans-asan/cool-compiler

.PHONY: reference-replacement-test reference-replacement-sanitize-test
reference-replacement-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_reference_replacement.py
test: reference-replacement-test
reference-replacement-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_reference_replacement.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: borrow-origins-test borrow-origins-sanitize-test
borrow-origins-test: build/cool-compiler build/language.BIN build/compiler-host.o build/language-runtime.o
	python3 tools/test_borrow_origins.py --output build/borrow-origins-audit.json
test: borrow-origins-test
borrow-origins-sanitize-test: repl-loans-sanitize-test build/language.BIN build/compiler-host.o build/language-runtime.o
	python3 tools/test_borrow_origins.py --frontend build/repl-loans-asan/cool-compiler --output build/borrow-origins-asan-audit.json

.PHONY: stores-test stores-sanitize-test
stores-test: build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_stores.py
test: stores-test
stores-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_stores.py --frontend build/repl-loans-asan/cool-compiler --sanitize-runtime

.PHONY: reference-ancestry-test reference-ancestry-sanitize-test
reference-ancestry-test: build/cool-compiler build/language.BIN build/compiler-host.o build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_reference_ancestry.py --output build/reference-ancestry-audit.json
test: reference-ancestry-test
reference-ancestry-sanitize-test: repl-loans-sanitize-test build/language.BIN build/compiler-host.o build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_reference_ancestry.py --frontend build/repl-loans-asan/cool-compiler --sanitize --output build/reference-ancestry-asan-audit.json

.PHONY: place-projections-test place-projections-sanitize-test
place-projections-test: build/cool-compiler build/language.BIN build/compiler-host.o build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_place_projections.py --output build/place-projections-audit.json
test: place-projections-test
place-projections-sanitize-test: repl-loans-sanitize-test build/language.BIN build/compiler-host.o build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_place_projections.py --frontend build/repl-loans-asan/cool-compiler --sanitize --output build/place-projections-asan-audit.json

.PHONY: provenance-graph-test provenance-graph-sanitize-test
provenance-graph-test: build/cool-compiler build/language.BIN build/coolc build/compiler-host.o build/language-runtime.o
	python3 tools/test_provenance_graph.py --output build/provenance-graph-audit.json
	python3 tools/test_provenance_graph.py --legacy --output build/provenance-graph-legacy-audit.json
test: provenance-graph-test
provenance-graph-sanitize-test: repl-loans-sanitize-test build/compiler-host.o build/language-runtime.o
	python3 tools/test_provenance_graph.py --frontend build/repl-loans-asan/cool-compiler --sanitize --output build/provenance-graph-asan-audit.json

.PHONY: provenance-copy-test provenance-copy-sanitize-test
provenance-copy-test: build/cool-compiler build/language.BIN build/coolc build/compiler-host.o build/language-runtime.o
	python3 tools/test_provenance_graph.py --copy --output build/provenance-copy-audit.json
	python3 tools/test_provenance_graph.py --copy --legacy --output build/provenance-copy-legacy-audit.json
test: provenance-copy-test
provenance-copy-sanitize-test: repl-loans-sanitize-test build/compiler-host.o build/language-runtime.o
	python3 tools/test_provenance_graph.py --copy --frontend build/repl-loans-asan/cool-compiler --sanitize --output build/provenance-copy-asan-audit.json

.PHONY: loan-provenance-test loan-provenance-sanitize-test
loan-provenance-test: build/cool-compiler build/compiler-host.o build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_loan_provenance.py --output build/loan-provenance-audit.json
test: loan-provenance-test
loan-provenance-sanitize-test: repl-loans-sanitize-test build/compiler-host.o build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_loan_provenance.py --frontend build/repl-loans-asan/cool-compiler --sanitize --output build/loan-provenance-asan-audit.json

.PHONY: provenance-selection-test provenance-selection-sanitize-test
provenance-selection-test: build/cool-compiler build/compiler-host.o build/language-runtime.o
	python3 tools/test_provenance_selection.py --output build/provenance-selection-audit.json
test: provenance-selection-test
provenance-selection-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_provenance_selection.py --frontend build/repl-loans-asan/cool-compiler --sanitize --output build/provenance-selection-asan-audit.json

.PHONY: provenance-access-test provenance-access-sanitize-test
provenance-access-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_provenance_access.py --legacy --output build/provenance-access-audit.json
test: provenance-access-test
provenance-access-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_provenance_access.py --frontend build/repl-loans-asan/cool-compiler --output build/provenance-access-asan-audit.json

.PHONY: legacy-graph-lifecycle-test
legacy-graph-lifecycle-test: build/coolc
	python3 tools/test_legacy_graph_lifecycle.py --output build/legacy-graph-lifecycle-audit.json
test: legacy-graph-lifecycle-test

.PHONY: physical-address-test physical-address-sanitize-test
physical-address-test: build/cool-compiler build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_physical_address.py --legacy --output build/physical-address-audit.json
test: physical-address-test
physical-address-sanitize-test: repl-loans-sanitize-test
	python3 tools/test_physical_address.py --frontend build/repl-loans-asan/cool-compiler --output build/physical-address-asan-audit.json

.PHONY: descriptor-rollback-test descriptor-rollback-sanitize-test
descriptor-rollback-test: build/cool-compiler build/language.BIN build/coolc build/compiler-host.o build/language-runtime.o
	python3 tools/test_descriptor_rollback.py --output build/descriptor-rollback-audit.json
test: descriptor-rollback-test
descriptor-rollback-sanitize-test: build/cool-compiler build/coolc
	python3 tools/test_descriptor_rollback.py --sanitize --output build/descriptor-rollback-asan-audit.json
