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
build/coolc: coolc/Host/native.c coolc/Host/warm_net.h coolc/Host/warm_task.h coolc/Host/warm_file.h coolc/Host/except.S | build
	clang -std=c11 -Wall -Wextra -Werror -O2 -fno-omit-frame-pointer -ffixed-x28 $(filter %.c %.S,$^) -o $@
build/coolc-x86_64: coolc/Host/native.c coolc/Host/x86.S coolc/Host/x86-native.h coolc/Host/warm_net.h coolc/Host/warm_task.h coolc/Host/warm_file.h | build
	clang -arch x86_64 -std=c11 -Wall -Wextra -Werror -O2 -fno-omit-frame-pointer coolc/Host/native.c coolc/Host/x86.S -o $@
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
build/language-runtime.o: language/runtime.c | build
	clang -std=c11 -Wall -Wextra -Werror -O2 -c $< -o $@
build/language-runtime.dylib: language/runtime.c | build
	clang -std=c11 -Wall -Wextra -Werror -O2 -dynamiclib $< -o $@
all: build/language.BIN build/language-runtime.o
.PHONY: project-test
project-test: build/language.BIN build/language-runtime.o build/language-runtime.dylib
	python3 tools/test_projects.py
test: language-test project-test
