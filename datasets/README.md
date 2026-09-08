# datasets/

Harbor가 읽는 로컬 데이터셋입니다. 폴더 하나가 문제 하나이고, 각 폴더는 Harbor 레지스트리의
`swebench-verified@1.0` 태스크를 복사한 뒤 `task.toml`만 고친 것입니다. 고치는 내용은
네트워크 정책(설치 단계는 프록시와 패키지 저장소만, 실행 단계는 프록시만)과 문제당 시간 제한입니다.

- `public/` Public 50문제. `task_ids.json`에 목록이 있고 공개됩니다.
- `dev/` Dev 5문제. Public의 부분집합으로, 참가자가 바로 돌려 볼 때 씁니다.
- `smoke/` 스모크 테스트용 임시 폴더. 커밋되지 않습니다.
- `private/` **여기에 두지 않습니다.** 저장소 밖 경로에 만들고 `arena final run --private-dir`로 넘깁니다.

만드는 명령은 `arena dataset build <이름> <instance_id>...`(직접 지정) 또는
`arena curate sample` → `arena curate assemble`(베이스라인 결과로 자동 구성)입니다.
