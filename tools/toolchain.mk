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
build/coolc: language/args.h language/ffi.h language/numeric.h language/memory.h coolc/Host/native.c coolc/Host/warm_net.h coolc/Host/warm_task.h coolc/Host/warm_file.h coolc/Host/except.S | build
	clang -std=c11 -Wall -Wextra -Werror -O2 -fno-omit-frame-pointer -ffixed-x28 $(filter %.c %.S,$^) -lffi -o $@
build/coolc-x86_64: language/args.h language/ffi.h language/numeric.h language/memory.h coolc/Host/native.c coolc/Host/x86.S coolc/Host/x86-native.h coolc/Host/warm_net.h coolc/Host/warm_task.h coolc/Host/warm_file.h | build
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
build/compiler-host.o: compiler/host.c language/ffi.h language/memory.h language/numeric.h | build
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
