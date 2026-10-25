# OfficeCLI MCP HTTP

[OfficeCLI](https://github.com/iOfficeAI/OfficeCLI)로 **DOCX·XLSX를 생성하고 첨부 문서를 편집**하는 컨테이너입니다. 공식 MCP Python SDK의 **Streamable HTTP `/mcp`**와 웹앱용 첨부 업로드·다운로드 API를 제공합니다.

웹앱의 AI가 자연어를 도구 호출로 변환하고, 컨테이너 안의 **실제 OfficeCLI v1.0.158**이 문서를 처리합니다. Office·LibreOffice·외부 문서 SaaS 계정이 필요하지 않습니다. OfficeCLI의 원래 stdio 서버를 외부에 노출하는 대신, 사용자별 파일 접근을 제어하는 HTTP 어댑터를 제공합니다.

## 실행

```bash
git clone https://github.com/Jungwoo-Ryu/officecli-mcp-http.git
cd officecli-mcp-http
python3 scripts/setup_env.py
docker compose up -d --build --wait
```

- MCP: `http://localhost:18080/mcp`
- 상태 확인: `http://localhost:18080/health`
- 데이터: Docker named volume `officecli_data`, 사용자별 디렉터리에 영속 저장
- `.env`에 생성한 비밀키는 서버에만 보관합니다. Git에 포함되지 않습니다.

## 웹앱 연결

```text
사용자: 파일 첨부 + "이 계약서 첫 문단을 바꿔줘"
  → 웹앱 백엔드: 로그인 세션의 userId 확인 → 첨부 업로드
  → 웹앱 AI: 반환된 filename을 참고하여 MCP 도구 호출
  → OfficeCLI: 원본 복사 → 읽기/수정 → 새 DOCX 또는 XLSX 저장
  → 사용자: 만료 시간이 있는 수정본 다운로드 링크
```

**웹앱 백엔드가 보낼 헤더**:

```http
Authorization: Bearer <OFFICECLI_MCP_TOKEN>
X-User-Id: <로그인 세션에서 가져온 사용자 ID>
```

`X-User-Id`는 1~128자의 영문/숫자/`_`/`-`/`.`이며 영문·숫자로 시작합니다. 백엔드에서 로그인 세션으로 결정하고, 브라우저 요청의 임의 userId를 그대로 전달하지 마세요. 서버 공용 토큰을 아는 백엔드는 사용자를 지정할 수 있는 신뢰 경계입니다.

웹앱도 Docker Compose에 있다면 같은 네트워크에 연결한 뒤 **`http://officecli-mcp:8080/mcp`**를 사용합니다. 호스트에서 실행하는 웹앱은 `http://localhost:18080/mcp`를 사용합니다. 이 저장소의 Compose 파일을 웹앱 Compose에 병합하거나 네트워크를 공유하면 됩니다.

[TypeScript 백엔드 예제](examples/webapp/office-agent.ts)는 업로드 함수와 자연어 → MCP 도구 실행 루프를 제공합니다. 실제 웹앱의 인증된 백엔드 라우트에서 호출하세요.

```bash
cd examples/webapp
npm ci
npm run check
```

백엔드 환경변수:

```dotenv
OFFICECLI_MCP_URL=http://officecli-mcp:8080/mcp
OFFICECLI_MCP_TOKEN=<서버 .env의 OFFICECLI_MCP_TOKEN과 같은 값>
OPENAI_API_KEY=<자연어 처리용 키>
OPENAI_MODEL=gpt-4.1-mini
```

```ts
// req.user.id는 기존 웹앱의 인증 미들웨어가 확정한 값입니다.
const attached = await uploadOfficeFile(req.user.id, file.originalname, file.buffer);
const answer = await editOffice(
  req.user.id,
  `첨부 파일: ${attached.filename}\n${req.body.message}`,
);
```

OpenAI는 예제일 뿐이며, MCP를 지원하는 다른 모델/에이전트에도 연결할 수 있습니다. 모델 키는 **웹앱 백엔드에만** 필요합니다. 컨테이너 자체는 LLM을 호출하지 않습니다. 대화 이력은 웹앱 서버에서 저장하고 후속 요청에 전달하세요.

## 파일 첨부 API

먼저 서버 쉘에서 `.env`를 읽습니다. 비밀키를 로그에 출력하지 마세요.

```bash
set -a
. ./.env
set +a
```

일반 첨부(`multipart/form-data`, 필드명 `file`):

```bash
curl --fail-with-body http://localhost:18080/api/files \
  -H "Authorization: Bearer $OFFICECLI_MCP_TOKEN" \
  -H 'X-User-Id: user-123' \
  -F 'file=@./계약서.docx'
```

바이너리 업로드도 지원합니다:

```bash
curl --fail-with-body -X PUT http://localhost:18080/api/files/budget.xlsx \
  -H "Authorization: Bearer $OFFICECLI_MCP_TOKEN" \
  -H 'X-User-Id: user-123' \
  --data-binary @./budget.xlsx
```

응답은 `filename`, `size_bytes`, `download_url`, `download_expires_at`입니다. 같은 사용자의 동일 파일명 업로드는 `409`로 거절합니다. 첨부 파일명이 겹치면 웹앱에서 UUID 등을 붙여 업로드하세요. 한글 파일명을 지원합니다. 기본 용량 제한은 **25 MB**이고 확장자·Office ZIP 구조·압축 해제 크기를 검사합니다. 암호화/매크로 문서는 지원하지 않습니다.

인증 다운로드는 `GET /api/files/{filename}`, 브라우저용 링크는 응답의 `/files/{signed-token}`입니다. 링크의 기본 만료 시간은 15분입니다. 만료되면 `office_download`로 갱신할 수 있습니다. 링크를 가진 사람은 만료 전까지 다운로드할 수 있습니다.

## MCP 도구

| 도구 | 기능 |
|---|---|
| `office_help` | 설치된 OfficeCLI의 DOCX/XLSX 요소·속성 도움말 |
| `office_create` | 새 문서 생성 + 선택적 일괄 편집 |
| `office_read` | 첨부/생성 문서를 text/outline/stats/issues로 읽기 |
| `office_get` | DOM 경로로 문단·셀·수식 등 조회 |
| `office_edit` | add/set/remove를 새 복사본에 적용; 원본 보존 |
| `office_files` | 현재 사용자 파일 목록 |
| `office_download` | 만료되는 다운로드 URL 발급 |

예: 업로드한 Word 첫 문단을 변경합니다.

```json
{
  "name": "office_edit",
  "arguments": {
    "filename": "계약서.docx",
    "output_filename": "계약서-수정.docx",
    "operations": [
      {"action": "set", "path": "/body/p[1]", "props": {"text": "변경된 계약 내용"}}
    ]
  }
}
```

예: 수식이 있는 Excel 파일을 만듭니다.

```json
{
  "name": "office_create",
  "arguments": {
    "filename": "budget.xlsx",
    "operations": [
      {"action": "set", "path": "/Sheet1/A1", "props": {"value": 100}},
      {"action": "set", "path": "/Sheet1/B1", "props": {"formula": "A1*2"}}
    ]
  }
}
```

한 번에 최대 100개 작업을 지원합니다. 생성·수정 중 하나라도 실패하면 새 결과 파일을 게시하지 않습니다. `office_edit`의 후속 수정에는 **반환된 새 filename**을 사용합니다. 기존 출력 이름을 덮어쓰지 않습니다.

## 배포 설정과 범위

- 외부 브라우저에서 다운로드하려면 `.env`의 `OFFICECLI_MCP_PUBLIC_BASE_URL=https://office.example.com`을 설정하고 HTTPS 역방향 프록시로 연결하세요. `OFFICECLI_MCP_ALLOWED_HOSTS`에도 `office.example.com`을 추가합니다. 브라우저 주소와 내부 MCP 주소는 달라도 됩니다.
- Compose는 호스트의 `127.0.0.1`에만 포트를 엽니다. 브라우저가 MCP 서버를 직접 호출하는 구성보다 웹앱 백엔드가 인증·첨부를 중계하는 구성을 사용하세요.
- HTTP는 stateless 모드입니다. 파일 잠금은 프로세스 내부이므로 **공유 볼륨에 쓰는 컨테이너는 1개**로 운영하세요. 별도 영속 볼륨과 작업 큐를 두면 사용자 단위 확장이 가능합니다.
- 생성/업로드 파일의 자동 삭제는 없습니다. 서비스의 보관 정책에 맞춰 볼륨 정리·백업·전체 저장 용량 제한을 운영하세요.
- 어댑터는 DOCX/XLSX의 텍스트·표·셀·수식·기본 서식 작업을 구조화해 노출합니다. OfficeCLI 전체 CLI, 셸, 임의 경로, raw XML, 외부 미디어/OLE 삽입, PDF/화면 렌더링은 노출하지 않습니다. 허용 속성은 [server.py](src/officecli_mcp/server.py)의 `SAFE_PROPS`/`SAFE_PREFIXES`를 참고하세요. 지원되지 않는 속성은 명확히 거절합니다.
- OfficeCLI의 수식 평가는 Excel 전체 엔진과 동일하지 않습니다. 입력값 수정 후 기존 수식의 저장 캐시가 비워질 수 있으며 Excel에서 열면 재계산됩니다. `office_get`의 `computedValue`로 지원되는 수식의 계산값을 조회할 수 있습니다. 지원되지 않는 함수나 고급 서식은 실제 파일로 확인하세요.
- 엔진 바이너리는 공식 릴리스 **v1.0.158**과 SHA-256을 고정합니다. 컨테이너에서 자동 업데이트를 끕니다. Linux amd64/arm64를 지원하며 arm64 체크섬도 포함되어 있습니다. 이 작업의 실제 실행 검증은 amd64에서 했습니다.

## 개발·검증

```bash
uv sync --frozen --group dev
python scripts/download_officecli.py
uv run ruff check .
uv run pytest -q
# Docker 컨테이너를 실행한 상태에서:
uv run python scripts/smoke_http.py
```

테스트는 실제 OfficeCLI와 공식 MCP HTTP 클라이언트를 사용해 DOCX/XLSX 생성, 첨부 업로드·편집, 원본 보존, 실패 시 결과 미게시, 수식 조회, 사용자 격리, 인증, 압축 폭탄·용량 제한을 확인합니다. 자연어 LLM 응답은 별도 모델 키가 필요하므로 자동 테스트 대상에 포함하지 않습니다.

TLS 검사 프록시가 있는 환경의 이미지 빌드에는 세션별 CA를 이미지에 넣지 않고 BuildKit secret으로 전달할 수 있습니다.

```bash
docker build --secret id=proxy_ca,src=/path/to/combined-ca-bundle.pem -t officecli-mcp-http:local .
```

## 라이선스·출처

어댑터: Apache-2.0. 문서 엔진: [iOfficeAI/OfficeCLI v1.0.158](https://github.com/iOfficeAI/OfficeCLI/releases/tag/v1.0.158), Apache-2.0. 원본 라이선스와 제3자 고지는 [vendor/officecli](vendor/officecli)에 보존하며 Docker 이미지에도 포함합니다. 독립적인 HTTP 어댑터로 OfficeCLI 공식 배포판은 아닙니다.
