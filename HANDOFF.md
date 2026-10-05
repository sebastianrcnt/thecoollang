# Cool 1.0 작업 인수인계

갱신: 2026-10-06. 리모트는 등록되어 있지 않다. **1.0 개발 중이며 완료 선언 전이다.**

## 시작 폴더와 먼저 볼 문서

실제 작업 저장소는 **`/Volumes/t5/coollang`** 이다. 현재 대화의 기본 cwd가
`/Volumes/t5/coolcom`일 수 있으므로 모든 명령에 작업 폴더를 명시한다.
**coolcom은 수정하지 않는다.** 별도 coolcom 설치 없이 Cool을 개발한다.

```sh
cd /Volumes/t5/coollang
git status --short
git log -5 --oneline
git diff --stat
git diff
git show --stat HEAD
```

읽는 순서:

1. 이 문서: 현재 작업과 검증 경계.
2. [release-1.0.md](docs/release-1.0.md): 최초 출시 범위, G1–G10 필수 기준,
   마지막 감사 기록과 Next implementation checkpoints. 모든 gate는 아직 Open.
3. [specification.md](docs/specification.md), [references.md](docs/references.md):
   명세 draft 36과 실제 참조/대여 제약. 구현된 범위와 향후 목표를 구분한다.
4. [compiler-invariants.md](docs/compiler-invariants.md),
   [compiler/README.md](compiler/README.md): 컴파일러 구조·메모리·AST·소유권 불변식.
5. [README.md](README.md), [performance.md](docs/performance.md),
   [language-plan.md](docs/language-plan.md): 사용 방법, 측정 근거, 설계 배경.

사용자는 1.0까지 자율 구현과 중간 커밋을 승인했다. 필요하면 gpt-6.1-sol
서브에이전트 하나를 사용해도 된다. 기존 `/root/performance` 에이전트는
현재 맡긴 구현을 완료했다. 새 세션에서는 그 핸들이 유지된다고 가정하지 않는다.

## 마지막 검증 완료 상태

`75304cb` — Restore narrow vector storage and clear chunks with bounded recursion.

- 셀프호스팅, tree/bytecode/ARM64 JIT/LLVM AOT/LLVM JIT 실행 경로 구현.
- 참조를 담는 Vector와 조건부 stores 효과 구현. sizeof(T)==1은 48바이트
  inline chunk, 그 외는 초기화된 Option 슬롯. 원소별 별도 할당 없음.
- clear는 tail chunk 단위로 해제. 일반 scope 종료의 재귀 해제는 당시 미해결.
- 50만 바이트 동일 O2 작업: 옛 plain 구현 58.367ms, 이 커밋 56.555ms 중앙값.
  draft 35의 528바이트/91.655ms 회귀 해소. 일반 성능 향상 주장으로 확대하지 않는다.
- 전체 회귀, 외부 설치/편집기, 두 bootstrap 경로, 관련 sanitizer 검사 통과.
- Vector 정상 34개·sanitizer 52개 관측, 중첩 참조 304개 판정·136개 positive·
  816개 실행·48개 REPL·0개 gap. 그 당시 소스 해시 일치.

로컬 증거:
`build/release-audit/vector-inline-final-regression.log`,
`build/release-audit/vector-inline-final-benchmark.log`,
`docs/benchmarks/vector-inline-arm64.json`.
`build/`는 생성물이라 새 clone에는 없을 수 있다. 없는 로그를 검증 증거로 주장하지 않는다.

## 현재 체크포인트: 깊은 소유 구조의 자동 해제

1MiB RLIMIT_STACK에서 32,768개 재귀 소유 노드의 scope 종료가 충돌하는
실제 결함을 발견했다. baseline의 tree/interp/jit/llvm은 exit 139,
llvm-jit은 exit 132. 단순히 Vector를 clear하도록 사용자에게 요구하는 것으로
해결하지 않는다. 안전한 일반 소유 구조의 자동 해제를 고친다.

현재 다음 **7개 소스 파일의 변경은 체크포인트로 커밋했으며 검증 완료 전**이다.
커밋 제목: `Checkpoint bounded-depth destruction pending regression validation`.
사용자가 작업 보존을 위해 커밋을 요청했다. 기존 변경을 reset/checkout으로
없애거나 완료 코드로 간주하지 않는다. 마지막 전체 검증 완료 소스는 여전히
`75304cb`이다.

| 파일 | 변경 |
| --- | --- |
| compiler/07-interpreter.cool | DropValue를 32개 inline DFS frame + 성장하는 heap buffer로 변경 |
| language/Interpreter.cool | legacy frontend의 동일 동작 |
| compiler/10-ownershipllvm.cool | typed destructor callback 생성, 역순 enqueue로 기존 순방향 해제 순서 유지 |
| language/OwnershipLLVM.cool | legacy frontend의 동일 LLVM 생성 |
| compiler/08-llvm.cool | dispatcher 런타임 선언 |
| language/LLVM.cool | legacy frontend의 동일 선언 |
| language/runtime.c | bounded native stack용 LIFO callback dispatcher와 deferred owner free |

유지할 불변식: 배열 원소/구조체 필드는 기존 순방향 DFS 순서, enum은 활성
payload만 해제, owner slot은 이동/해제 시 null, 자식 해제 후 부모 owner free,
각 owner 정확히 한 번 해제, 성공 종료 후 작업용 heap 해제. 런타임 C는
기계적인 callback dispatch만 담당하고 타입별 파괴 의미는 Cool이 생성한다.

**현재까지 확인한 것:** 아래 빌드 exit 0. build/drop-depth/build.log에 기록.

```sh
make -j4 build/cool-compiler build/language.BIN build/language-runtime.o build/language-runtime.dylib
```

**아직 확인하지 않은 것:** 수정 후 깊이 재현 검사, 해제 순서/널/이동/혼합
소유 구조 검사, sanitizer, 전체 회귀, 새 bootstrap fixed point, 성능 영향.
이후 작업의 소스 해시는 이전 통과 보고서와 다르므로 과거 보고서로 현재
체크포인트 코드를 통과 처리하지 않는다. ClearMoved의 재귀는 이번 수정과 별개다.

## 다음 실행 순서

1. git status와 체크포인트 커밋의 git show로 위 7개 변경을 검토한다. 실행 중인 빌드/검사를 먼저 확인한다.
   이번 인수인계 시 빌드 session 97554는 exit 0으로 종료 확인했다.
2. 아래 fixture로 1MiB/32,768 node 재현을 다시 실행한다. 기존 파일이 있으면
   `build/drop-depth/chain.cool`, baseline은 `build/drop-depth/baseline.json`.
3. tree/interp/jit/llvm/llvm-jit와 release O2, production/legacy 양쪽에서
   stdout `123\n`, exit 0, 잔여 owner 0을 확인한다. 실패 원인을 수정한다.
4. 반복 DFS/dispatcher의 성장 경계, 배열·enum·다중 필드 해제 순서,
   null/moved owner, 반환/교체/REPL forget과 런타임 오류 복구를 영구 테스트로 만든다.
   LLVM/runtime ASan·UBSan과 frontend sanitizer도 검증한다.
5. 소스를 고정한 뒤 필요한 회귀와 bootstrap을 실행한다. 예전 검증 명령:

```sh
make -k -j4 test bootstrap-check editor-distribution-test borrowed-vector-sanitize-test nested-reference-slice-sanitize-test stores-sanitize-test
```

6. 작업용 메모리 누수·성능 회귀를 확인하고 명세/감사 기록을 갱신해 중간 커밋한다.
   이후 release contract의 나머지 gate를 계속 진행한다. 빌드 성공만으로 1.0 완료 아님.

### 독립 재현 fixture

```cool
import "std/mem";
import "std/io";
struct Node { next: own[Node]; value: i64; }
fn prepend(root: &mut own[Node], value: i64) {
    let node = new[Node](Node { next: move *root, value: value });
    *root = move node;
}
fn main() {
    {
        var empty = Node {};
        var root = move empty.next;
        for (var i = 0; i < 32768; i = i + 1) { prepend(&mut root, i); }
        assert(mem.owner_count() == 32768);
    }
    assert(mem.owner_count() == 0);
    io.println(123);
}
```

Python subprocess의 preexec_fn에서 stack 제한을 적용했던 방식:

```python
import resource, subprocess

def bounded():
    resource.setrlimit(resource.RLIMIT_STACK,
                       (1024 * 1024, resource.getrlimit(resource.RLIMIT_STACK)[1]))

result = subprocess.run(
    ["./tools/cool", "run", "--backend", "tree", "build/drop-depth/chain.cool"],
    capture_output=True, text=True, timeout=90, preexec_fn=bounded)
print(result.returncode, repr(result.stdout), repr(result.stderr))
```

fixture의 `prepend` 함수는 현재의 외부 owner를 loop 내부에서 직접 move하는
제약을 피하면서 정상적인 안전 소유권 API로 체인을 만든다.

## 작업 규칙

- 실행 중인 검사/컴파일러가 사용하는 compiler·language·stdlib·test 소스를
  수정하지 않는다. 보고서가 종료 시 소스 해시를 검증한다. 관측 timeout은
  프로세스 종료가 아니다. 같은 session을 다시 확인한 뒤 수정/재시작한다.
- 두 frontend를 의미적으로 맞추고 bootstrap 수렴을 보존한다.
- 거부 검사를 없애거나 언어 목표를 줄여 실패를 통과 처리하지 않는다.
- 작은 성능 차이는 측정 잡음과 구분한다. 다른 검사가 없는 상태에서 재측정한다.
- 사용 가능한 개발 버전과 검증이 완료된 정식 1.0을 구분한다.
