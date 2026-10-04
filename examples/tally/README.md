# Tally

명령행으로 받은 레이블의 등장 횟수를 JSON 파일에 저장하는 예제입니다.
빈 문자열, 따옴표, 줄바꿈, 한국어 등 UTF-8 레이블을 지원합니다.
첫 인자는 출력 파일이고 나머지는 레이블입니다. 성공하면 전체 개수를 출력합니다.
인자 없이 실행하면 사용법을 표시합니다. 유효하지 않은 UTF-8 레이블과
파일 쓰기 실패는 오류로 종료합니다.

설치한 `cool`로 이 디렉터리에서 실행하세요.

```sh
cool run . -- totals.json apple 한글 apple
cool build --release . -o tally
./tally totals.json apple 한글 apple
```

결과는 `{"apple":2,"한글":1}`이며 표준 출력은 `3`입니다.

`ledger/`는 명령행 처리와 분리된 디렉터리 패키지입니다. 소유 문자열을
키로 쓰는 정렬 맵, 최근 갱신 결과 64개까지 보관하는 벡터, JSON 직렬화,
파일 출력을 함께 사용합니다. 집계 키는 세션 동안 유지하며 최근 결과는
64개가 차면 비웁니다. 예제 소스에는 `unsafe`가 없습니다.

같은 패키지를 대화형으로 사용할 수도 있습니다.

```text
cool repl --offline --frozen
import ledger "example.test/tally/ledger";
var book=ledger.create();
ledger.add(&mut book,"apple",2)
ledger.get(&book,"apple")
let held=ledger.view(&book);
ledger.add(&mut book,"apple",1)
:forget held
ledger.add(&mut book,"apple",1)
:forget book
```

`held`가 살아 있는 동안의 변경은 대여 충돌로 거부됩니다. 대여를 해제한
다음 변경할 수 있습니다. 실행 중 오류가 나기 전에 완료된 변경은
유지됩니다. `tools/test_repl_project.py`는 이 패키지를 외부 임시 디렉터리에
복사해 엔진별 결과와 장시간 REPL 작업을 독립 Python 모델과 비교합니다.
