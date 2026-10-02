# Cool

C처럼 저수준 코드를 표현하되 읽기 쉬운 문법, 단순한 패키지 구조와 빠른 반복 실행을 목표로 하는 언어입니다. 원본 coolcom이나 OS 저장소 없이 빌드합니다.

현재는 **언어 구현 진행 단계**입니다. 스칼라 타입, 함수, 패키지, 인터프리터·JIT·LLVM 실행 경로는 구현됐지만 구조체·배열·슬라이스·제네릭·소유권 검사는 아직 없습니다. 전체 목표와 실제 지원 범위를 구별해 기록합니다.

## 시작하기

지원 호스트는 Apple Silicon macOS입니다. Xcode Command Line Tools, Python 3.12 이상, GNU coreutils의 `gtimeout`이 필요합니다. LLVM JIT 실행에는 LLVM의 `lli`, 기존 x86-64 회귀 검사에는 Rosetta 2가 필요합니다.

```sh
cd ~/t5/coollang
make -j4
export PATH="$PWD/build:$PATH"
cool run examples/modern.cool
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

컴파일러 소스는 현재 기존 Cool 문법으로 작성돼 기존 셀프호스팅 컴파일러로 부트스트랩됩니다. **새 문법으로 자기 자신을 컴파일하는 단계는 아직 아닙니다.** REPL은 변수·함수와 컴파일 캐시를 유지하며 같은 시그니처의 함수 본문만 교체할 수 있습니다.

`build`는 Clang으로 LLVM IR을 네이티브 실행 파일로 만듭니다. 생성물은 호환되는 Mac에서 소스·Python·Cool 컴파일러 없이 실행됩니다. 현재 새 언어 프로그램에 명령행 인자를 전달하는 기능은 미구현입니다.

## 패키지

디렉터리가 패키지입니다. `pub fn`만 외부에 공개하며 순환 import는 거부합니다. `cool.mod`와 `cool.sum`, MVS 버전 선택, 로컬 replace와 `cool.work`, 오프라인·동결 해석을 지원합니다.

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
make bootstrap-check
cool legacy run examples/hello.cool
```

`cool legacy`는 기존 HolyC 계열 CLI입니다. 기존 문법 예제를 새 언어 예제로 혼동하지 마세요. `coolc/`에는 기존 컴파일러·네이티브 호스트·seed가, `language/`에는 새 언어 구현이 있습니다.

회귀 검사는 기존 ARM64/x86-64 코드 생성, 새 언어 실행 경로 간 결과 일치, 패키지·캐시·체크섬, REPL 교체, 포매터·개발 도구를 확인합니다. `bootstrap-check`는 seed → gen1 → gen2 → gen3을 빌드해 gen2와 gen3의 바이트 일치를 검사합니다. 이 명령 자체는 체크인된 seed를 변경하지 않습니다.

[전체 구현 목표](docs/language-plan.md) · [현재 지원 범위](language/README.md) · [추출 기준](SOURCE.md)

자체 코드는 MIT이며 포함된 외부 코드는 원래 라이선스를 따릅니다. [LICENSE](LICENSE) · [THIRD_PARTY.md](THIRD_PARTY.md)
