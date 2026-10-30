# RealCAD 아키텍처 (2026-10-29 기준, 실제 코드와 1:1)

> 자연어(+사진) → **실제로 조립되는** 3D 프린팅 부품(STEP/STL/3MF/OBJ). 생성은 Meta Muse Spark, 검증은 OCC 커널 실측.
> Meta Global AI Developer Hackathon 제출작(인디, Push the Frontier/제조). 모든 코드는 2026-10-27 KST(킥오프 이후) 시작.

## 런타임에 부르는 AI = Meta Muse Spark 1.3 하나
| 단계 | 모듈 | 모델 호출 | 역할 |
|---|---|---|---|
| 역질문 | `agent/clarify.py` | muse-spark-1.3 (JSON) | 꼭 필요한 1개만 되묻기(대부분 질문 없음) |
| 기획자 | `agent/planner.py` | muse-spark-1.3 (JSON, 멀티모달) | 요구/사진 → 설계 계약(`DesignContract`) |
| 코더 | `agent/codegen.py` | muse-spark-1.3 (코드, 멀티모달) | 기본형으로 안 되는 임의 부품 → build123d 코드. 사진이면 기준물(카드·A4·동전·자)로 mm 역산 |
| 판정자 | `agent/judge.py` | muse-spark-1.3 (JSON) | 커널 실패 리포트 → 계약 파라미터 수정(그림 재생성 아님) |
| 편집자 | `agent/editor.py` | muse-spark-1.3 | "더 크게/구멍 추가" 후속 지시를 계약 diff 또는 코드 최소 수정으로 |
외부 생성 모델(Meshy)은 `REALCAD_ENABLE_EXTERNAL=1` 일 때만 켜지는 옵션이며 기본 빌드에선 꺼져 있다. Thingiverse 는 모델이 아니라 라이브러리 검색이다.

## 두 경로
```
A. 계약 경로(exec 없음)   프롬프트 → planner → DesignContract(JSON) → geometry/builder → verify → judge 루프(≤3회) → export
B. 코드 경로(샌드박스)     프롬프트/사진 → codegen → build123d 코드 → agent/sandbox(격리 실행) → 실패 메시지로 auto-repair(≤3회) → export
```
A 는 7종 기본형(plate/container/gear/enclosure/profile/clamp/ball), B 는 "뭐든 다"(텀블러·거치대·메카·치비…). 웹에서 "설계"=A, "만능"=B, 사진은 B 우선.

## 검증 — 전부 커널 실측 (`verify/checks.py`, `pipeline.py`)
| 코드 | 검사 | 방법 | 대상 |
|---|---|---|---|
| F0 | 요청 규격 보유 여부 | 표 조회(미보유 → HARD, 가까운 규격 제안) | plate |
| H1 | 볼트 머리 ↔ 벽·옆 볼트 간섭 | 볼트 솔리드 ∩ 장애물 부피 > 0 | plate |
| H2 | 구멍 ≥ 규격 공차구멍 | **완성 솔리드의 원통면 반지름 실측** vs ASME B18.2.8 | plate(through) |
| H3 | 탭 체결 깊이 ≥ k·D | 나사산 반경(0.47D)에서 레이캐스트한 재료 길이, k=강1.0/Al1.5/플라스틱2.0 | plate(tapped) |
| H4 | 연단거리 ≥ 1.5D | 구멍 중심 ↔ 판 외곽(바운딩 산식) | plate |
| S2 | 렌치 간격 ≥ 2×머리폭 | 구멍 중심거리 | plate(SOFT) |
| G1 | 기어 맞물림 | 같은 기어를 이론 중심거리에 반피치 돌려 교차 부피 = 0 | gear |
| E1/E2 | 보드 구멍 일치 / 바닥 피막 | 파일럿 구멍 위치·지름 실측 / 레이캐스트 ≥ 1 mm | enclosure |
| H5 | 공구 접근 | 머리 위 소켓 OD 포락선 ∩ 벽 = 0 | plate(벽) |
| H6 | 카운터보어 머리 묻힘 | 묻힌 머리 솔리드 ∩ 판 = 0 | plate(counterbore) |
| I1/I2 | 히트세트 인서트 구멍 | 깊이 ≥ 인서트 길이+1, 바닥 ≥ 1 (레이캐스트) / 둘레 살두께 ≥ 2 | plate(insert) |
| P1 | FDM 구멍 보정 | 자동 사이징 구멍 지름 +hole_comp(기본 0.2, 탭 제외) 적용 사실 리포트 | plate |
| D1 | 치수 충실도 | 코드 주석의 선언 전체 크기 vs 커널 bbox ±60% | 코드 경로 |
| M3 | 오버행 | 45° 넘는 하향면 면적 비율 > 10% 경고 | 전부(SOFT) |
| M1 | 최소 벽두께 | 파라미터 ≥ 노즐×2 | 전부(SOFT) |
| M2 | watertight | OCC 유효 + 내보낸 메시 watertight(퇴화면 정리 후), 측정 실패는 실패 | 전부 |
| C1 | 미융합 겹침 | ≤10개 솔리드 쌍별 교차 > 0.5 mm³ → HARD | 전부 |
코드 경로(B)는 샌드박스 하네스가 같은 M2·C1 + **공중에 뜬 분리 솔리드**를 실패로 돌려 모델이 고치게 한다.
아직 없는 것: 실제 외곽 기준 연단거리, 렌치 스윙(오픈엔드), 티어드롭 구멍, 스냅핏 보 계산 — 로드맵. (치수 기입 DXF 도면은 export/drawing.py 로 추가됨)

## 샌드박스 (`agent/sandbox.py`)
1) AST 검사: import 는 `math`·`build123d` 만(하위모듈·별칭 금지), `os/sys/open/eval/getattr/…` 이름 금지, dunder 속성·`.format` 금지, `export_*/import_*/Mesher/BRepTools…` 파일·네트워크 계열 이름/메서드 금지.
2) 격리 프로세스: `python -I`, 허용 전역은 build123d 가 **자체 정의한 비모듈 객체만**(os·sys·ctypes·requests 등 재수출 모듈 제외), `build123d` 이름으로는 허용 전역만 담은 프록시 모듈 반환, 안전 builtins 만.
3) 자원: CPU 25 s(rlimit) + 벽시계 45 s + 부모가 RSS 3 GB 감시(macOS 는 RLIMIT 무효) + stdout 상한.
4) 결과 게이트: 솔리드 0/부피 0/비3D/겹친 미융합/공중부양/non-watertight → 사람이 읽는 오류 → auto-repair 입력.
신뢰 경계는 "로컬 개발 도구". 공개 터널에 열 땐 `REALCAD_TOKEN` 으로 /api/* 토큰 요구.

## 패키지 구조 (실제)
```
src/realcad/
  fasteners/standards.py   UNC/UNF 16 + ISO 9 (B18.2.8 공차구멍·B18.2.1/B18.6.3/ISO 4017 머리·너트·와셔·소켓OD·표준길이), get/resolve/normalize
  contract/schema.py       DesignContract 7종 + plate 옵션(hole_dia/hole_type/hole_style/hole_comp/material/mate_thickness/washer/nut) + custom 보드, _sanitize 범위 가드
  geometry/builder.py      판·벽·볼트·용기·인벌류트 기어·보드 케이스(실제 구멍 좌표)·프로파일·클램프·구 쉘·wrap 케이스·뚜껑
  geometry/analyze.py      STEP 나사구멍 감지, 구멍 지름 실측
  verify/checks.py         F0 H1 H2 H3 H4 S2 G1 E1 E2 M1 M2 C1, mesh_report
  verify/engagement.py     레이캐스트 체결 길이
  pipeline.py              계약 → 조립 + 검증
  agent/                   meta_client · clarify · planner · codegen · judge · loop · editor · specs · sandbox
  export/exporters.py      STEP/STL(퇴화면 정리)/DXF 평면도  export/bom.py  볼트 길이·너트·와셔 BOM + CSV
  printing/                split(OCC 분할+다월) · mesh_split(격자) · chopper(BSP/목 선분리) 
  retrieval/library.py     Thingiverse 검색(토큰 필요), Meshy(옵트인)
  web/app.py               FastAPI: /api/clarify design design_code edit undo design_photo wrap split split_upload retrieve
web/acad.html              데모 UI(리본·ViewCube·2D 스케치→돌출·배치·공차·프리셋·되돌리기·다운로드)
examples/                  poc_bracket(검증 데모) · meta_run(CLI) · eval_seeded(심은 오류 검출율) · eval_smoke(실전 pass@1)
tests/                     fasteners · verify · sandbox · gear/enclosure (pytest)
```

## 비용
설계 1건 = planner 1회(+judge ≤3회) 또는 codegen 1회(+repair ≤3회). 12k max_tokens 라 코드 경로 1건 ≈ 수천~1.5만 토큰. 커널·검증·내보내기는 로컬·무료.
