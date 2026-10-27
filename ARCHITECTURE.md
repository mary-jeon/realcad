# RealCAD 아키텍처

> 자연어 프롬프트 → **실제로 조립되는** CAD(STEP/STL). text-to-cad가 안 하는 "빡센 검증"(볼트 머리 간섭·공구 접근·체결 길이·연단거리·출력 가능성)을 커널(build123d/OCC)로 실측해서 잡는다. 메타 AI 해커톤(인디, Push the Frontier/제조) 제출작.

## 메타 모델은 필수 (해커톤 통과 기준)
심사 1차 관문 = "메타 Model API나 오픈웨이트를 해커톤 기간에 실제로 썼는가". 그래서 LLM 단계는 전부 **Meta Model API(Muse Spark)** 로 호출한다. $150 크레딧이 이걸 위한 거다. (Muse Code = 메타의 코딩 에이전트, 우리가 개발할 때 쓰는 건 선택. 제출물의 런타임이 메타 모델을 써야 함.)

## 데이터 흐름
```
사용자 프롬프트 (+선택: 사진 / PDF / 기준물)
  └─▶ [planner]  Muse Spark(멀티모달)         요구·이미지·PDF → 설계 계약(DesignContract, JSON)
        └─▶ [coder]  Muse Spark / Spark Open    계약 → build123d 파이썬 코드
              └─▶ [builder]  build123d 실행      코드 → Part/Assembly + 표준 볼트 배치
                    └─▶ [verify]  커널 측정       간섭·공구접근·체결길이·연단거리·동축도 + 출력가능성(trimesh)
                          └─▶ [report]           통과/실패 + 수치 + 규격 근거
                                ├─ 실패 ─▶ [judge]  Muse Spark(렌더+리포트 보고) → 수정 지시 → coder 로 (반복 N회)
                                └─ 통과 ─▶ [export]  STEP + STL + OBJ/glTF + 볼트 BOM
                                              └─ [calibration]  프린터 공차 오프셋 적용
```
웹 UI: 업로드+프롬프트 → 3D 뷰어 + 검증 리포트 + 다운로드 (심사위원이 직접 실행).

## 역할 분리 (메타 도구 활용 25% 점수)
- **Muse Spark = 기획자**(사진/PDF→계약)이자 **판정자**(렌더+리포트→수정). 생성자와 판정자를 분리(CADSmith/ProCAD 방식)해서 자기 승인 편향을 피함.
- **오픈웨이트(Muse Spark Open / Glimmer)** = 빠른 컴파일오류 수정 루프 / 오프라인 모드.
- 지표: 통과까지 반복 횟수, 계약 통과율, 심은 오류 검출율.

## 검증(핵심 차별점) — 전부 OCC 커널 측정, 렌더 눈대중 아님
1. 볼트 현실성: 모든 구멍이 표준 볼트에 바인딩, 지름=규격 clearance hole
2. 볼트 머리 간섭: 볼트 솔리드 ∩ 부품/옆 볼트 부피 > 0 → 충돌
3. 공구 접근: 머리 주변 소켓/렌치 스윙, SHCS 직선 접근
4. 체결 길이: 탭 깊이 ≥ 1~1.5×dia, 관통은 그립+와셔+너트로 볼트 길이 선택
5. 연단거리: 구멍 중심 ≥ 약 2×dia from 모서리
6. 동축도: 맞물리는 부품 구멍 정렬
7. 출력 가능성: 최소 벽두께, 오버행>45°, watertight/manifold(trimesh)

## 패키지 구조
```
realcad/
  src/realcad/
    fasteners/standards.py   표준 볼트 라이브러리 (UNC/UNF 인치 + ISO 미터, clearance/counterbore)
    contract/schema.py       DesignContract 스키마 (치수·볼트·조립관계)
    contract/extract.py      Muse Spark: 텍스트/사진/PDF → 계약
    geometry/builder.py      계약 → build123d Part/Assembly
    geometry/primitives.py   구멍·카운터보어·보스 등
    verify/checks.py         간섭·공구접근·체결길이·연단거리·동축도
    verify/printability.py   벽두께·오버행·watertight (trimesh)
    verify/report.py         검증 리포트
    agent/meta_client.py     Meta Model API 클라이언트
    agent/planner.py         요구 → 계약
    agent/coder.py           계약 → build123d 코드
    agent/judge.py           렌더+리포트 → 수정 지시
    agent/loop.py            생성→검증→판정 반복
    export/exporters.py      STEP/STL/OBJ + BOM
    calibration/tolerance.py 프린터 공차 시험편·오프셋
    web/app.py               업로드+프롬프트+3D뷰어+리포트
  examples/                  데모용 입력(프롬프트·사진·PDF)
  tests/
  out/                       생성물(gitignore)
```

## 기술 스택
- 커널: build123d 0.13 (Apache-2.0), OCC. 메시: trimesh. 3D 뷰어: three.js. 웹: FastAPI(또는 Streamlit).
- 파이썬 3.12 전용 venv(uv). 레포 공개.
- 규격 기본 US(인치), "미터로" 하면 ISO.

## 9일 계획 → `../[hackathon]/03_기획/제품설계_프롬프트투CAD_20261027.md`
D1~2 볼트 라이브러리+첫 슬라이스 / D3~4 어셈블리+간섭 / D5 사진·PDF 계약 / D6 공차보정 / D7 메타 오케스트레이션 / D8 웹UI+내보내기 / D9 데모영상+제출(11/5 11:00).

## UX/UI — 비전문가도 쓰는 "진짜 CAD" (레퍼런스 반영)
레퍼런스 교훈: 전통 CAD는 복잡함·툴바 과다·학습곡선 때문에 초보가 이탈(engineering.com, Onshape UX). Tinkercad는 브라우저·즉시 시작·블록 조합이지만 필렛·정밀 없음. Shapr3D는 튜토리얼·빠른 온보딩. text-to-cad 비평: 출력이 "비주얼 브리프"일 뿐 편집 안 되는 미리보기 → **무엇이 진짜고 무엇이 미리보기인지 분명히** 해야 함.
RealCAD의 답:
- **대화로 시작** + **꼭 필요할 때만 질문**(ProCAD식): 용도·하중·맞물림·프린터만. 질문 폭주 금지.
- **라이브 3D 뷰어 + 평이한 검증 리포트**: "볼트가 벽에 닿아요 → 구멍 5mm 옮길까요?" 처럼 사람 말로.
- **수정은 파라미터 슬라이더/칩으로**(재프롬프트 아님) — "실패 시 파라미터 dict 반환" 패턴과 직결.
- **인지부하 최소, 한 가지 길**(Onshape 원칙). 툴바 없음.
- **차별점 = 신뢰**: text-to-cad는 "비주얼 브리프"지만 RealCAD는 **검증 완료 + 진짜 STEP/STL**. "이건 실제로 조립돼요"를 리포트로 증명.

## 플랫폼 — 웹 + 앱 공용 구조
무거운 CAD(build123d/OCC)는 브라우저·모바일에서 못 돎 → **서버에서 실행**. 그래서 한 백엔드 + 얇은 클라이언트 2개.
```
[Core 엔진 Python]  geometry·verify·export  ← 이미 있음
      │ 감싸서
[HTTP API  FastAPI]  POST /design(프롬프트+이미지) → {3d, report, step/stl url}
      ├── 웹  React/Next + three.js(react-three-fiber) 뷰어
      └── 앱  React Native/Expo (react-three-fiber + expo-gl, 또는 웹뷰 재사용)
```
한 API를 웹/앱이 공유. 해커톤은 **웹 먼저**(심사위원이 바로 실행), 앱은 같은 API 쓰는 RN 래퍼로 확장.

## 비용 — Meta $150로 되나? 됨.
- $150 = **Meta Model API 크레딧 = LLM 호출(기획자·코더·판정자) 토큰 비용만**. 설계 1건당 수천 토큰 수준이라 개발+데모에 충분. 이미지(Muse Spark 멀티모달)가 더 들지만 데모 규모면 OK.
- **CAD 커널(build123d)·검증·내보내기 = 무료**(서버/내 맥에서 돎, 메타 과금 0).
- **웹 호스팅은 별개**: 데모는 로컬 실행(무료) 또는 Modal 크레딧 $100(해커톤 제공)·무료 티어. 메타 $150과 무관.

## 기능 — 비전문가 대응 (2026-10-27 사용자 요구)
1. **역질문(핵심 UX)**: 모르는 정보는 시스템이 되물어 채운다(ProCAD식). 예 — "연필통" → "지름·높이 얼마로?"/"펜 몇 자루?"; "이 14mm에 물리는 기어" → "잇수 몇 개? 모듈? 보어 지름? 두께?". 꼭 필요한 것만, 기본값 제안과 함께.
2. **프린터 빌드볼륨 인식 + 자동 분할**: "3D 프린팅용" 선택 시 프린터 프로파일(빌드 X·Y·Z, 노즐, 재료) 묻기. 모델이 베드보다 크면 → 최적 분할면 제시 + 정렬 조인트(도브테일·핀·나사보스) 자동 추가 + 재조립 가이드. "실제 출력 가능" 테마에 직결.
3. **크기 조절**: 만든 뒤 전체/부분 스케일 업·다운(파라메트릭이라 즉시). 치수 재검증 동반.
4. **기어 등 기능 부품**: 인벌류트 기어(잇수·모듈·압력각·보어), 브래킷·엔클로저·홀더·스냅핏 — 전부 파라메트릭, RealCAD 강점.

## 스코프 경계 (피규어/고디테일)
- 피규어·얼굴(눈코입) 같은 **유기형 고디테일**은 결이 다름: 파라메트릭 CAD(build123d)가 아니라 조각·메시 생성 영역(Meshy·Tripo·Muse Image→3D). 치수·공차 검증이 적용 안 되는 분야라 RealCAD의 차별점(검증·조립성)과 안 맞음. 이미 레드오션.
- 권고: 9일 해커톤은 **기능 부품(조립·출력 가능)**에 집중 = 아무도 제대로 안 하는 승리 각도. 피규어는 "미래 모드"로 Muse Image→3D 붙이면 되지만 데모 핵심에서 빼는 게 낫다(안 그러면 메시지 흐려짐). 사용자 결정 대기.
