# Cool

Cool은 HolyC 계열의 네이티브 컴파일 언어입니다. 컴파일러·런타임·포매터를
독립적으로 빌드하고 사용할 수 있습니다. CoolOS, Warm, VM이나 원본 coolcom 저장소는 필요하지 않습니다.

## 시작하기

현재 지원 호스트는 **Apple Silicon macOS**입니다. Xcode Command Line Tools,
Python 3.12 이상, GNU coreutils의 `gtimeout`이 필요합니다.
전체 테스트의 x86-64 실행에는 Rosetta 2도 필요합니다.

```sh
cd ~/t5/coollang
make -j4
export PATH="$PWD/build:$PATH"
cool run examples/hello.cool
cool build examples/hello.cool -o build/hello
./build/hello
```

`cool`은 어느 디렉터리에서나 실행할 수 있습니다. PATH 설정을 새 터미널에도
적용하려면 셸 설정에 `export PATH="$HOME/t5/coollang/build:$PATH"`를 추가하세요.
CLI는 저장소를 필요로 하지만, `cool build`로 만든 실행 파일은 소스·컴파일러·Python
없이 호환되는 Apple Silicon Mac에서 실행할 수 있습니다.

```cool
extern U0 Print(U8i *fmt, ...);

U0 Hello()
{
    Print("Hello, Cool!\n");
}

Hello;
```

프로그램은 최상위 문장을 실행합니다. `main`을 자동으로 호출하지 않습니다.
`U0`, `U8i`, `I64i`, `F64` 등은 기본 타입이며, 헤더 없는 소스에서 사용할 수 있습니다.
`#include "file.coolh"`로 소스 기준 상대 경로의 헤더를 포함할 수 있습니다.

## 명령

```sh
cool run program.cool -- 'argument with spaces' --flag
cool build program.cool -o app
cool compile program.cool -o program.BIN
cool run program.BIN
cool vet program.cool
cool fmt program.cool
cool fmt --check src/
cool fmt --diff src/
```

`build`는 ARM64 Mach-O 실행 파일을 만들고 `compile`은 로더가 필요한 BIN 모듈을 만듭니다.
출력·입력 경로와 실행 중 작업 디렉터리는 호출한 디렉터리를 기준으로 합니다.
프로그램 인자는 `--` 뒤에 전달하며 종료 코드는 그대로 전달됩니다.
인자·종료 서비스는 `NativeArgCount`, `NativeArg`, `NativeExit`를 import해 사용합니다.
`fmt --check`는 변경이 필요하면 1, 오류가 있으면 2로 종료합니다.

x86-64는 ARM 호스트에서 크로스 컴파일한 BIN을 별도 로더로 실행합니다.

```sh
make build/coolc-x86_64
cool compile --target x86_64 examples/hello.cool -o build/hello-x86.BIN
build/coolc-x86_64 --run build/hello-x86.BIN
```

## 구현과 지원 범위

Cool 소스 → 자체 IR·최적화 → ARM64/x86-64 기계어 → BIN 모듈로 이어집니다.
백엔드는 Aiwnios에서 이식·발전시킨 Cool 구현이며 LLVM을 사용하지 않습니다.
C/어셈블리 호스트 로더가 BIN 재배치와 macOS 서비스 호출을 담당합니다.
실행 파일 패키징과 로더 빌드에는 Clang을 사용합니다.

ARM64는 컴파일러 자체 재컴파일을 지원합니다. x86-64는 BIN 실행·프로브를 지원하며,
인라인 어셈블리, 컴파일러 자체 부트스트랩과 스레드 서비스에는 제한이 있습니다.
Linux·Windows 호스트는 아직 지원하지 않습니다. 자세한 제한은 [x86 문서](coolc/Host/X86.md)에 있습니다.
Cool은 포인터와 수동 메모리 관리를 제공하며 메모리 안전 언어는 아닙니다.

- `coolc/`: 프런트엔드, 백엔드, 런타임, 호스트 로더, seed, 포매터와 테스트
- `tools/cool`: 사용자 CLI와 독립 실행 파일 패키징
- `tools/native/`: 컴파일러 준비·회귀 테스트·부트스트랩 검증
- `examples/`: 실행 가능한 예제

`coolc/Host/warm_*.h`와 패키징의 내부 `WARM_PROGRAM_HEADER` 이름은 공유 호스트
서비스의 기존 이름입니다. Warm 컴파일러나 저장소를 요구하지 않습니다.

## 검증

```sh
make -j4 test
make bootstrap-check
```

`test`는 호스트 로더, ARM64/x86-64 코드생성·인라이닝, 진단·behavior,
포매터와 CLI를 검증합니다. `bootstrap-check`는 seed → gen1 → gen2 → gen3을
빌드하고 gen2와 gen3의 바이트 일치를 확인합니다. 체크인된 seed는 변경하지 않습니다.
로그와 생성물은 `build/`에 저장됩니다.

[검증 기록](docs/verification.md) · [부트스트랩](coolc/NATIVE.md) · [추출 기준](SOURCE.md)

자체 코드는 MIT이며, 포함된 외부 코드는 원래 라이선스를 따릅니다.
[LICENSE](LICENSE)와 [THIRD_PARTY.md](THIRD_PARTY.md)를 참고하세요.
