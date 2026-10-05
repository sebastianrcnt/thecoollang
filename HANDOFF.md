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

이 커밋 — Deep owned destruction stays bounded in native stack with dispatch-free shallow drops.

- 셀프호스팅, tree/bytecode/ARM64 JIT/LLVM AOT/LLVM JIT 실행 경로 구현.
- 참조를 담는 Vector와 조건부 stores 효과 구현(draft 36 그대로).
- 깊은 소유 구조의 scope 종료가 native stack을 값 깊이만큼 키우지 않는다.
  인터프리터는 32개 inline DFS frame + 성장 heap buffer를 쓰고, LLVM 생성
  소멸자는 C 런타임의 LIFO worklist에 typed callback을 제출하며 owner
  저장소는 자식 해제 뒤에 반환한다. 배열/구조체 자식은 역순 enqueue로
  LIFO에서 순방향 DFS 순서를 유지하고 enum은 활성 payload만 해제한다.
- 회귀 fixture: 1MiB RLIMIT_STACK에서 32,768 소유 노드 체인이 이전에는 모든
  엔진이 충돌(tree/interp/jit/llvm exit 139, llvm-jit exit 132), 이제 양
  frontend와 release O2에서 stdout `123`, exit 0, 잔여 owner 0.
- 일반 소멸은 direct-call 비용 유지: 구조적 소멸 깊이가 유한한 타입은
  dispatcher 없이 직접 재귀 drop으로 생성하고, owner wrapper는 move/null
  슬롯에서 worklist를 건너뛴다.
- Release O2 소멸 마이크로벤치(3회, 7샘플 교대): shallow 원소별 owner drop과
  300-wide 배열은 이전 재귀 코드와 동등, 재귀 체인 ~1.16x, 500k 바이트 vector
  해제 ~1.33x. 잔여 비용은 재귀 타입에 대한 bounded worklist 비용이며 G8
  후속 과제다. 인터프리터 backend는 shallow drop에서 iterative-DFS frame
  비용을 아직 지불한다(fast path 미구현).
- 전체 회귀 `make -k -j4 test bootstrap-check editor-distribution-test
  borrowed-vector-sanitize-test nested-reference-slice-sanitize-test
  stores-sanitize-test` exit 0. 두 bootstrap 경로와 self-host 수렴 통과
  (self-host IR SHA256 `6f186acc8c51245b...`). drop-depth sanitizer는 runtime
  ASan/UBSan + ASan frontend 포함 129 실행 통과.

로컬 증거:
`tools/test_drop_depth.py`, `tools/bench_drop_depth.py`,
`docs/benchmarks/drop-depth-arm64.json`, `build/drop-depth/full-regression.log`.
`build/`는 생성물이라 새 clone에는 없을 수 있다. 없는 로그를 검증 증거로
주장하지 않는다.

## 이전 체크포인트(d29d578) 이력

`d29d578` "Checkpoint bounded-depth destruction pending regression validation"
는 위 작업의 시작점이었다. 그때는 7개 소스 파일 변경이 검증 전이었고, 깊이
재현·해제 순서·sanitizer·전체 회귀·bootstrap·성능이 모두 미확인이었다.
이번 커밋에서 그 검증을 완료하고, 추가로 shallow 타입 직접 drop과 null/moved
owner worklist 회피를 구현해 소멸 성능 회귀를 줄였다. `75304cb`는 그 이전의
마지막 전체 검증 상태였다.

## 다음 실행 순서

1. G8: 재귀 타입 long-chain scope-exit 소멸의 잔여 ~1.2-1.35x 비용을 줄이고
   인터프리터 shallow-drop fast path를 추가한다. lifetime/destructor 검사를
   유지한다.
2. G2/G4/G5: 저장된 참조, tracked iteration, 남은 collection API와 임시
   receiver 제약을 확장한다. 명세/참조 문서의 제약을 갱신한다.
3. G6: REPL 세션 자원의 bounded/reclaimable 처리를 완성한다.
4. G9: 평가 순서·소유권·borrowed storage에 대한 결정적 fuzz를 확장하고
   발견된 실패를 영구 회귀 테스트로 승격한다.
5. G1/G3/G7/G10: 언어 명세 동결, frontend 정리, 도구/LSP 회복 범위 확대,
   원격 CI와 1.0 릴리스 노트를 완료한다. 빌드 성공만으로 1.0 완료 아님.

## 작업 규칙

- 실행 중인 검사/컴파일러가 사용하는 compiler·language·stdlib·test 소스를
  수정하지 않는다. 보고서가 종료 시 소스 해시를 검증한다. 관측 timeout은
  프로세스 종료가 아니다. 같은 session을 다시 확인한 뒤 수정/재시작한다.
- 두 frontend를 의미적으로 맞추고 bootstrap 수렴을 보존한다.
- 거부 검사를 없애거나 언어 목표를 줄여 실패를 통과 처리하지 않는다.
- 작은 성능 차이는 측정 잡음과 구분한다. 다른 검사가 없는 상태에서 재측정한다.
- 사용 가능한 개발 버전과 검증이 완료된 정식 1.0을 구분한다.
