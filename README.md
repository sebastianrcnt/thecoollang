# Cool

C처럼 저수준 코드를 표현하되 읽기 쉬운 문법, 단순한 패키지 구조와 빠른 반복 실행을 목표로 하는 언어입니다. 원본 coolcom이나 OS 저장소 없이 빌드합니다.

현재는 **언어 구현 진행 단계**입니다. 스칼라·구조체·고정 배열·범위 검사 슬라이스, 함수, 패키지, 인터프리터·JIT·LLVM 실행 경로를 구현했습니다. payload enum·제네릭 특수화·명시적 이동 소유권·공유/배타적 참조·대여 반환 계약도 지원합니다. 새 문법 컴파일러의 셀프호스팅과 세대 간 일치 검증도 통과했습니다. Result·Option·슬라이스·문자열·소유 UTF-8 텍스트·검사 산술·동적 벡터·정렬 맵·파일·프로그램 인자를 제공하는 기본 표준 라이브러리도 포함합니다. 전체 목표와 실제 지원 범위를 구별해 기록합니다.

작업을 이어받는 개발자는 [HANDOFF.md](HANDOFF.md)에서 현재 변경 사항과 다음 검증 순서를 먼저 확인하세요.

## 시작하기

지원 호스트는 Apple Silicon macOS입니다. Xcode Command Line Tools, Python 3.12 이상, GNU coreutils의 `gtimeout`이 필요합니다. LLVM JIT 실행에는 LLVM의 `lli`, 기존 x86-64 회귀 검사에는 Rosetta 2가 필요합니다.

```sh
cd ~/t5/coollang
make -j4
export PATH="$PWD/build:$PATH"
cool run examples/modern.cool
cool run examples/aggregates.cool
cool build examples/modern.cool -o build/modern
./build/modern
cool repl
```

```cool
package main;
import "std/io";

fn square(n: i64) -> i64 {
    return n * n;
}

fn main() {
    for (var i = 0; i < 4; i = i + 1) {
        io.println(square(i));
    }
}
```

`&T`와 `&mut T`는 블록 범위의 공유·배타적 참조입니다. `&x`와 `&mut x`로 만들며 대여 중인 값의 충돌 접근과 소유자 이동을 검사합니다. 원시 주소는 `unsafe` 안에서 `&raw x`로 만듭니다. 벡터와 파일 API도 참조를 받으므로 일반적인 사용에는 `unsafe`가 필요하지 않습니다. 슬라이스와 REPL도 대여를 추적하며, REPL에서는 `:forget 이름`으로 바인딩과 대여를 해제합니다. 중첩 참조 저장과 장시간 세션의 자원 회수에는 아직 제한이 있습니다. [지원 범위와 예제](docs/references.md)를 확인하세요.

지역 변수는 초기화해야 하며 `let`과 함수 인자는 변경할 수 없습니다. 암시적 축소 변환은 허용하지 않습니다. 포인터 역참조·산술·외부 C 호출은 `unsafe` 블록이 필요합니다. 메모리 안전 언어라고 보장하지 않습니다.

## 실행과 개발

```sh
cool run program.cool                 # 바이트코드 실행, 자주 호출한 함수는 ARM64 JIT
cool run --backend tree program.cool  # 참조 인터프리터
cool run --backend jit program.cool   # ARM64 JIT
cool run --backend llvm program.cool  # LLVM AOT 결과 캐시 후 실행
cool run --backend llvm-jit program.cool
cool emit-ir program.cool -o program.ll
cool build program.cool -o app
cool check .
cool fmt --check src/
cool test .
cool doc .
```

C로 트랜스파일하지 않습니다. Cool로 작성된 프런트엔드가 타입 검사 후 트리·바이트코드·ARM64 기계어·LLVM IR을 생성합니다. C 코드는 OS·숫자·메모리·C ABI 어댑터입니다. Python은 빌드와 패키지 해석을 조율합니다.

일반 `cool` 명령은 **새 문법으로 작성되고 자기 자신을 컴파일하는 `compiler/` 디렉터리 패키지**을 사용합니다. 최초 빌드는 기존 컴파일러를 seed로 사용하고, 이후 세대는 새 컴파일러로 빌드합니다. `make selfhost-check`는 3세대 LLVM IR과 2·3세대 네이티브 바이너리의 바이트 일치를 확인합니다. REPL은 변수·함수와 컴파일 캐시를 유지하며 같은 시그니처의 함수 본문만 교체할 수 있습니다. 일반 입력의 토큰·AST·임시 코드는 실행 후 회수하며, 반복 입력 100,000회와 참조·문자열의 유지 여부를 검사합니다. 함수 교체·실패 시 폐기되는 AST·바이트코드·JIT 코드도 회수합니다. 더 이상 참조하지 않는 선언 소스도 회수하며, 함수 재정의 40,000회를 검사합니다. 장시간 세션의 전체 자원 관리는 아직 개발 중입니다.

`build`는 Clang으로 LLVM IR을 네이티브 실행 파일로 만듭니다. 생성물은 호환되는 Mac에서 소스·Python·Cool 컴파일러 없이 실행됩니다. `cool run program.cool -- arg1 arg2`로 프로그램 인자를 전달하고 `std/os`에서 읽을 수 있습니다.

## 패키지

디렉터리가 패키지입니다. `pub` 함수·타입·필드를 외부에 공개하며 순환 import는 거부합니다. `cool.mod`와 `cool.sum`, MVS 버전 선택, 로컬 replace와 `cool.work`, 오프라인·동결 해석을 지원합니다. 프로젝트 디렉터리에서 `cool repl --offline --frozen`을 실행하면 같은 규칙으로 패키지를 import할 수 있습니다. 로딩한 패키지가 바뀌면 새 세션이 필요합니다. [REPL 패키지 규칙](docs/references.md#packages-in-the-repl)을 참고하세요.

```sh
cool mod init example.com/team/demo
cool get example.com/team/library@v1.2.0
cool mod tidy
cool mod download
cool mod verify
cool mod graph
cool mod vendor
cool check --offline .
```

원격 소스는 `host/owner/repo` 형태의 Git 저장소와 버전 태그를 사용합니다. `COOL_GIT_SSH=1`로 SSH 전송을 선택할 수 있습니다. `cool.sum`은 Cool 자체 트리 해시 형식이며 Go의 체크섬 서비스와 호환되는 프로토콜은 아닙니다. 프록시·투명성 서비스·커밋 의사 버전은 미구현입니다.

## 부트스트랩과 검증

```sh
make -j4 test
make bootstrap-check  # 기존 seed 검증
make selfhost-check   # 새 문법 컴파일러 셀프호스팅 검증
make benchmark
cool legacy run examples/hello.cool
```

`cool legacy`는 기존 HolyC 계열 CLI입니다. 기존 문법 예제를 새 언어 예제로 혼동하지 마세요. `coolc/`에는 기존 컴파일러·네이티브 호스트·seed가, `language/`에는 부트스트랩 프런트엔드와 공용 런타임이, `compiler/`에는 새 문법 셀프호스팅 컴파일러가 있습니다.

회귀 검사는 기존 ARM64/x86-64 코드 생성, 새 언어 실행 경로 간 결과 일치, 패키지·캐시·체크섬, REPL 교체, 포매터·개발 도구를 확인합니다. `bootstrap-check`는 seed → gen1 → gen2 → gen3을 빌드해 gen2와 gen3의 바이트 일치를 검사합니다. 이 명령 자체는 체크인된 seed를 변경하지 않습니다.

[명세 초안](docs/specification.md) · [호환성 정책](docs/compatibility.md) · [에디터·LSP](docs/editor.md) · [다중 패키지 CLI 예제](examples/tally/README.md) · [설치·개발 배포](docs/distribution.md) · [메서드](docs/methods.md) · [성능 측정](docs/performance.md) · [표준 라이브러리](stdlib/README.md) · [셀프호스팅](compiler/README.md) · [전체 구현 목표](docs/language-plan.md) · [현재 지원 범위](language/README.md) · [추출 기준](SOURCE.md)

자체 코드는 MIT이며 포함된 외부 코드는 원래 라이선스를 따릅니다. [LICENSE](LICENSE) · [THIRD_PARTY.md](THIRD_PARTY.md)
