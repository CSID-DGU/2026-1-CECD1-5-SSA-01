# ERCE 로컬 기준 자료 복원

현재 단가·변수 근거와 공식 공무원 월 기본급을 재적재용 JSON으로 함께 공유한다. 원본 PDF, API 키 및 전체 기존 RAG DB는 포함하지 않는다.

저장소 루트에서 실행:

```sh
python3 -m backend.erce.scripts.reference_snapshot import
```

`backend/erce/data/reference_snapshot.json`의 자료를 `backend/generated/erce_variable_evidence.sqlite3`에 키 기준으로 적재한다. 다른 키의 기존 자료는 삭제하지 않는다. 해당 자료의 공개시점·대상·단위·기간·가정 여부는 원래 메타데이터를 유지한다. 모든 숫자가 최신 공식 단가는 아니다.

근거 Python 모듈에서 추가 보강한 행을 다시 적재하려면:

```sh
python3 -m backend.erce.scripts.build_variable_table
```

검토 완료한 로컬 DB를 공유 파일로 갱신하려면:

```sh
python3 -m backend.erce.scripts.reference_snapshot export
```

운영 PDF 분석은 로컬 `backend/.env`에 `OPENAI_API_KEY`와 `ERCE_AI_MODE=gpt`를 설정한다. 개발 중에는 `manual`로 두고 AI 분석 입력을 직접 전달할 수 있다. 환경변수 파일은 Git에 올리지 않는다.
