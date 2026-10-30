# 커뮤니티 니즈 100건 ↔ RealCAD 대조 (2026-10-30)

원천: `커뮤니티_3D프린팅_50건_20261030.md`(Reddit 32·Bambu 12·Prusa 2·HN 3·V1E 1), `커뮤니티_CAD_AutoCAD_50건_20261030.md`(HN 16·Autodesk 22·Onshape 5·Eng-Tips 4·CadTutor 3). 두 조사 모두 원문 열람/본문 확인, 창작 URL 없음. CAD 쪽은 Reddit 차단으로 0건(보강 여지).

## 3D 프린팅 커뮤니티 (태그 건수 → RealCAD)
| 니즈(건수) | 사람들 말 | RealCAD 현재 | 오늘 보완 |
|---|---|---|---|
| 공차·치수오류(17·14) "구멍이 0.2~0.7 작게 나온다" | "the holes are .1 to .3 mm smaller than they are designed", "Oversizing… best permanent solution" | FDM 끼워맞춤 규칙(0.075/0.15/0.2/0.4 mm/변)이 코드 경로 프롬프트에 있었음 | **hole_comp +0.2 mm 기본 보정**(자동 사이징 구멍, 탭 제외) + P1 리포트, **핏 테스트 쿠폰 프리셋**으로 내 프린터 값 측정 |
| 학습장벽(16) "Fusion 너무 어렵다" | "Even trying to learn Fusion 360??!!", "I know nothing" | 자연어·사진 입력, 프리셋, 역질문 최소화 | 프리셋 12종(인서트·카운터보어·쿠폰·ESP32 추가) |
| 인서트·나사구멍(11) | "whats the approach?", "So there is no standard size, then.", 벽 얇아 "warping and melting" | 없었음 | **히트세트 인서트 표 + hole_type=insert**(깊이·바닥 I1, **둘레 살두께 ≥2mm I2**), 코드 경로 프롬프트에 인서트 치수표 |
| AI-CAD(11) "메시 생성기는 쓸모없고 코드 경로만 통한다", 뷰어 없이 스크린샷 루프 | "pretty much useless when you need precise dimensions", "screenshot, scribbled on it, pasted it back" | 코드 경로(build123d) + 뷰어 + 대화형 수정·되돌리기 + 커널 오류→자동수정 | D1 치수 충실도, 미융합/공중부양 거부 → "tiny gaps or unconnected edges" 문제 직접 차단 |
| 케이스(6) ESP32/Pi | "The electronics part was fun. The enclosure part was not." | Pi/Uno 프리셋 | **custom 보드**(치수·구멍 좌표 입력) + E1/E2 실측, ESP32 프리셋 |
| 분할(5) | "absolutely no idea on how to split it" | grid/BSP/목 선분리 분할 + 다월 | (변경 없음; 도브테일은 로드맵) |
| 내보내기(5) STEP vs STL | "STL's are garbage… STEP files instead" | STEP·STL·3MF·OBJ | **DXF 도면** 추가 |
| 스냅핏·힌지(4) | "burned through an entire roll" | 코드 경로 + 공차 규칙 | (프리셋/규칙 보강 여지) |
| 벽두께(4), 오버행(3) | "does my model have to have a certain thickness" | M1 벽두께, **M3 오버행 45°** | M3 신설 |
| 측정(4) | "not something I can just measure… with calipers" | 사진 기준물 치수 역산 | (변경 없음) |
| 기어(3) | "the modules are what confuse me" | 인벌류트 기어 + 맞물림 G1 | 오늘 새로 만든 것 |

## CAD/AutoCAD 커뮤니티 (태그 건수 → RealCAD)
| 니즈(건수) | 사람들 말 | RealCAD 현재 | 오늘 보완 |
|---|---|---|---|
| AI-CAD 기대·불만(25) "정확하고 편집 가능해야 믿는다" | "they are not technically accurate", "minimize how often the LLMs think about numbers" | 숫자는 LLM이 아니라 표(ASME B18.2.8/ISO 273)와 커널이 결정, 계약(JSON)은 편집 가능 | H2 실측·F0 미지 규격 거부로 "지어낸 치수" 차단 |
| 자동화·명령줄(14) | "deterministic and efficient tools" | 명령줄 UI, 계약 경로는 exec 없음(결정론) | — |
| 파라메트릭(10) | "change one dimension and everything breaks" | 계약 수정(diff)·되돌리기, 코드 보관 | — |
| 검증·간섭(10+1) "interference dimension" | "subtle errors, hard to find", 간섭 깊이 수치 요구 | 간섭 **부피 수치** 리포트, 12종 검사 | H5 공구접근·H6 머리묻힘 추가 |
| 내보내기 DXF/STEP·단위(8+5) "DXF가 10배 작게" | "assumes units in feet" | STEP mm | **DXF $INSUNITS=4(mm) 명시**, 노트에 units: mm |
| 구멍·체결·규격조회(7+7) hole wizard 327표 | "I had to google for free-fit hole sizes", "Pick a Standard… Class of Fit" | fit class 3종, 규격표 | **카운터보어/카운터싱크/탭/인서트/관통** 한 필드로 |
| 도면·치수(6) "Fusion already knows the dimensions" | "I always miss something" | 없었음 | **치수 기입 DXF**(전체·구멍 Ø·위치·체결 노트) |
| BOM(2) "fasteners missing" | — | 없었음 | **볼트 길이·너트·와셔 BOM CSV** |
| 학습장벽(6), 공차 스택(3) | — | 자연어 | (공차 스택업은 범위 밖) |

## 남은 갭(로드맵)
도브테일/스냅 조인트 분할, 티어드롭 구멍(수평 축 구멍 오버행), 스냅핏 캔틸레버 계산, "모델 가리켜서 수정", 기존 도면/데이터시트 첨부, MCP 연결, 공차 스택업.
