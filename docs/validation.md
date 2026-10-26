# 신규 문서·첨부 템플릿 검증

검증일: 2026-10-26 (UTC). 엔진: **OfficeCLI v1.0.158, Linux amd64**.

실제 문서를 만들고 공식 MCP Python 클라이언트로 `initialize → tools/call`을 수행한 뒤, HTTP로 결과 파일을 다운로드해 **python-docx/openpyxl로 다시 열어** 검사합니다. 엔진 함수만 직접 부르는 테스트가 아닙니다. 동일한 시나리오를 호스트의 실제 OfficeCLI 서버와 Docker 컨테이너의 Streamable HTTP `/mcp`에서 실행합니다.

| 시나리오 | 확인 내용 |
|---|---|
| 신규 DOCX 생성 | 한글 제목, Heading1 스타일, 본문, 2×2 표의 실제 내용 |
| 신규 XLSX 생성 | 여러 시트, 숫자·셀 서식, 시트 내부 수식, 다른 시트 참조 및 계산값 |
| DOCX 양식 첨부 후 편집 | multipart 업로드, 고객명 run·표 안의 프로젝트명 수정, 결과 다운로드 |
| DOCX 서식 보존 | 혼합 run의 굵게·기울임·밑줄·색·글자 크기, 표 스타일, 머리글·바닥글, 여백, 북마크, 문서 제목 속성, 변경 대상 외 문장 |
| DOCX 후속 편집 | 반환받은 수정본 filename으로 재편집하고 이전 수정본도 그대로 보존 |
| XLSX 양식 첨부 후 편집 | raw PUT 업로드, 고객명·수량 수정, 수식 유지, 시트 간 부가세·합계 계산값 확인 |
| XLSX 양식 보존 | 셀 글꼴·색·채우기·숫자 서식·정렬, 병합 셀, 열 너비, 행 높이, 틀 고정, 인쇄 영역·방향, 입력 규칙, 기존 차트·참조·위치 |
| 원본 보존 | 업로드 원본을 다시 내려받아 바이트가 완전히 같은지 비교 |
| 전용 템플릿 확장자 | `.dotx`/`.xltx` 업로드가 명확히 거절되는지 확인; 현재 지원하지 않음 |

추가한 시나리오 파일: [tests/test_document_workflows.py](../tests/test_document_workflows.py). 6개 테스트 중 4개는 생성·양식 편집 성공 흐름이고, 2개는 미지원 확장자 거절을 확인합니다. 기존 10개 테스트는 사용자 격리, 인증, 용량 제한, 원본 보존, 편집 실패 시 결과 미게시 등을 확인합니다.

## 재현

```bash
uv sync --frozen --group dev
python scripts/download_officecli.py
uv run pytest -q
```

실행 중인 컨테이너에서 생성·첨부 편집을 재검증하려면, 저장소 루트의 `.env`가 컨테이너와 같은 비밀키를 갖도록 합니다.

```bash
docker compose up -d --build --wait
OFFICECLI_WORKFLOW_URL=http://localhost:18080 \
OFFICECLI_ARTIFACT_DIR=./validation-artifacts \
uv run pytest tests/test_document_workflows.py -q
```

`validation-artifacts`에는 생성 결과와 테스트용 원본 양식·수정본이 저장됩니다. CI에서도 `document-workflow-samples` artifact로 받아 직접 열 수 있습니다. 실행은 고유 테스트 사용자 ID를 사용하며 운영 사용자 문서는 건드리지 않습니다. 테스트 데이터는 컨테이너 볼륨에 남으므로 검증 환경에서 실행하세요.

## 실제 사용 시 범위

- 여기서 “템플릿”은 **양식으로 사용하는 `.docx`/`.xlsx` 파일**입니다. Word의 `.dotx`, Excel의 `.xltx`는 문서 형식으로 저장한 뒤 첨부해야 합니다.
- `{{고객명}}` 같은 문자열이 업로드만으로 자동 치환되지는 않습니다. AI가 문서를 읽고 해당 DOM 경로에 `office_edit`를 호출합니다. DOCX에서 기존 혼합 서식을 유지하려면 문단 전체를 새 텍스트로 바꾸기보다 해당 `/r[N]` run이나 정확한 표 셀을 수정하세요.
- XLSX 입력값을 변경하면 수식의 저장된 캐시가 비워질 수 있습니다. 지원되는 수식은 `office_get`의 `computedValue`로 계산값을 확인하며, Excel에서 파일을 열면 캐시가 다시 계산됩니다. Excel 전체 함수와의 호환성을 보증하지 않습니다.
- 위 테스트는 **MCP·첨부 API·OfficeCLI·결과 파일**을 검증합니다. 실제 웹앱의 로그인·파일 첨부 UI 및 LLM의 자연어 해석 정확도는 연결된 웹앱과 모델 키가 없어 검증하지 않았습니다. TypeScript 예제는 타입 검사까지 통과했으며, 실제 모델 호출이 성공했다는 의미는 아닙니다.
- 모든 고객 양식에 대한 무손실 보증은 아닙니다. 특수 필드, 외부 연결, 서명, 고급 수식 등이 있는 실사용 양식은 동일한 방식으로 별도 확인하세요.
