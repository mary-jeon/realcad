# 프롬프트 기반(자연어) CAD 시스템 딥리서치 — RealCAD를 "프롬프트 캐드"로

> 목적: RealCAD(FastAPI + build123d/OCC 커널 + LLM 플래너 → 설계계약 JSON → 파라메트릭 형상·검증)를 **초보자~전문가까지 제대로 쓰는 "프롬프트 캐드"**로 발전시키기 위한 실행 가능한 아키텍처·로드맵 도출.
>
> 작성일 2026-10-28. 모든 핵심 주장에 출처를 인라인으로 달았고(§8 참고문헌에 품질 A~E 등급), 2차 요약에서만 나온 수치는 `[확인 필요]`로 표기했다. 추측은 넣지 않았다.

---

## ① 요약 (Executive Summary)

**1. 업계 전체가 "메시가 아니라 파라메트릭(B-rep + 피처 트리)이 정답"이라는 데 수렴하고 있다.** text-to-3D 메시 생성은 결과가 "비주얼 브리프"일 뿐 치수·구속·피처 의미가 없어 편집·제조에 못 쓴다는 것이 Zoo·DeepCAD·Text2CAD의 공통 전제다. Zoo는 "삼각형 메시는 표면의 근사일 뿐 공학 지오메트리의 정의가 아니다… 엔지니어가 다루는 실제 산출물은 (메시가 아니라) sketches·constraints·dimensions·features로 된 **파라메트릭 레시피**"라고 못 박는다([Zoo, "Why AI Must Generate Parametric CAD"](https://zoo.dev/blog/why-ai-must-generate-parametric-cad), D). **→ RealCAD의 "설계계약(DesignContract) JSON = 파라메트릭 레시피" 노선은 업계 정설과 정확히 일치한다. 이게 가장 큰 자산이다.**

**2. LLM이 직접 쓰는 중간표현은 3갈래이고, 각각 트레이드오프가 분명하다.** (a) **명령 시퀀스**(DeepCAD/Text2CAD/CAD-GPT — sketch→extrude 토큰열), (b) **코드 생성**(CadQuery/OpenSCAD/build123d — 파라메트릭이지만 복잡 곡면 약하고 컴파일 에러), (c) **직접 메시**(Meshy/Tripo — 유기형 강함, 치수 없음). RealCAD는 "LLM이 코드를 직접 exec하지 않고 **검증 가능한 계약 JSON만 신뢰**" — 이는 코드생성의 파라메트릭 장점을 취하면서 LLM 코드 오류·보안 리스크를 차단한 영리한 중간 노선이다([Zoo/Leo AI, "How Text-to-CAD Works"](https://www.getleo.ai/blog/how-text-to-cad-works), D).

**3. RealCAD의 진짜 해자(moat)는 "커널 실측 검증 루프"다.** 2024~2026 학계가 뒤늦게 같은 방향으로 가고 있다: CADCodeVerify(GPT-4 + 검증/수정 루프), IterCAD·PR-CAD(generate→verify→refine 대화 루프), MUSE 벤치마크(제조성·조립성·기능성 평가). 이들 모두 "생성 후 검증·수정"을 핵심으로 본다([IterCAD, arXiv 2606.13368](https://www.themoonlight.io/en/review/itercad-an-iterative-multimodal-agent-for-visually-grounded-cad-generation-and-editing), A). **RealCAD는 이미 OCC 커널로 간섭·연단거리·체결길이를 실측한다 — 대부분의 경쟁 연구는 Chamfer Distance 같은 형상 유사도만 보지 "볼트가 실제로 들어가는지"는 안 본다.**

**4. "자유곡면 = 생성, 기능부품 = 파라메트릭" 하이브리드가 정답.** 피규어·마우스·핸들 같은 유기형은 파라메트릭으로 불가능하고 Meshy/Tripo/Rodin 같은 메시 생성이 이미 레드오션이다. RealCAD는 `kind="retrieve"`로 이 경계를 이미 인식하고 있다 — 이를 "retrieve(검색) + generate3d(메시 생성)"로 확장하되 **기능부품 코어는 파라메트릭 유지**가 전략적으로 옳다.

**5. 프린터빌리티·대형분할·대화형 편집이 "실제로 조립/출력된다"는 메시지를 완성한다.** 45° 오버행·최소벽두께·분할(Chopper식 정렬 조인트)·STEP/3MF 파이프라인은 전부 확립된 영역이고 RealCAD에 printing/chopper·mesh_split 스캐폴드가 이미 있다. 남은 건 "리모컨 만들어줘 → 버튼 5개 추가해줘"식 **설계계약 diff 기반 대화형 반복 편집**이다.

**6. 초보-전문가 겸용의 핵심은 "모드 분리 + 되묻기 최소화 + 파라미터 칩 편집"이다.** Tinkercad(즉시 시작·블록조합·정밀 없음)와 전문 CAD(피처 트리·학습곡선)의 양 극단 사이에서, RealCAD는 "대화로 시작 + 꼭 필요할 때만 되묻기(clarify) + 수정은 재프롬프트가 아니라 슬라이더/칩" 노선을 이미 설계해 뒀다 — 이는 ProCAD식 미니멀 인테이크와 일치한다.

**7. 권장 로드맵(§7 상세):** Phase 0 설계계약 diff·대화편집 → Phase 1 프린터빌리티 자동수정 루프 완성 → Phase 2 하이브리드(retrieve+generate3d) → Phase 3 피처 히스토리(계약 이력) → Phase 4 멀티파트 어셈블리·대형분할 프로덕션화.

---

## ② Text-to-CAD 기술/제품 지형

### 2.1 세 가지 생성 패러다임 (핵심 분류)

| 접근 | 중간표현 | 대표 | 강점 | 한계 | 파라메트릭? |
|---|---|---|---|---|---|
| **명령 시퀀스** | sketch→extrude 등 CAD 연산 토큰열 | DeepCAD, Text2CAD, CAD-GPT | B-rep로 변환 쉬움, 피처 히스토리 보존, 학습 데이터셋 존재 | 복잡 연산(loft/sweep/pattern) 재현율 낮음, 오류 연쇄 | ✅ |
| **코드 생성** | CadQuery/OpenSCAD/build123d 파이썬 | Query2CAD, Text-to-CadQuery, 범용 LLM | 버전관리·재사용, 완전 파라메트릭 | 복잡 곡면·멀티바디 약함, LLM 코딩 에러로 무효 지오메트리 | ✅ |
| **직접 메시** | 삼각형 메시(voxel/점군 경유) | Meshy, Tripo, Rodin, Project Bernini | 유기형·자유곡면 강함, 빠름 | 치수·구속·피처 의미 없음, 편집·제조 불가, non-watertight 가능 | ❌ |

출처: [Leo AI, "How Text-to-CAD Works"](https://www.getleo.ai/blog/how-text-to-cad-works) (D, 벤더). API-driven(네이티브 CAD에 sketch/extrude/fillet 명령 주입) 방식은 "가장 미성숙 — 오류 하나가 모델 전체로 연쇄되고 디버깅이 처음부터 모델링하는 것보다 어려울 수 있다"고 평가.

> **RealCAD의 위치:** 코드 생성의 파라메트릭 장점을 취하되, LLM이 코드를 직접 뱉어 `exec`하는 대신 **검증된 스키마(DesignContract JSON)만** 받아 신뢰된 빌더(build123d)가 실행한다(ARCHITECTURE.md). 이는 "LLM 코드 에러·보안·연쇄 실패" 3대 리스크를 구조적으로 차단한 설계다.

### 2.2 학술 계보

- **DeepCAD** (Wu, Xiao, Zheng / Columbia, **ICCV 2021**, [arXiv 2105.09492](https://arxiv.org/abs/2105.09492), A): 형상을 voxel/점군/메시가 아니라 **CAD 연산 시퀀스**로 생성하는 최초의 3D 생성 모델. Transformer 오토인코더로 CAD 명령을 "문장의 단어"처럼 다룸. 명령열을 고른 이유 = "명령열 → B-rep 변환은 쉽지만 역은 어렵다". 파라미터를 고정크기 벡터로 통일하고 연속값을 8bit 정수로 양자화. Onshape에서 수집한 **178,238개** 모델+구성 시퀀스 데이터셋 공개. 이 데이터셋이 이후 거의 모든 후속 연구의 기반이 됨.

- **Text2CAD** (Khan et al. / DFKI, **NeurIPS 2024 spotlight**, [arXiv 2409.17106](https://arxiv.org/abs/2409.17106), A): 자연어 → 파라메트릭 CAD 생성 **최초의 AI 프레임워크로, "초보자~전문가 수준 프롬프트" 전부 지원**(RealCAD 목표와 동일 명제). DeepCAD 데이터셋에 Mistral+LLaVA-NeXT로 텍스트 주석을 자동 생성해 **~170K 모델 / 660K 텍스트 주석**(고수준 설명 ~ 상세 수치 사양) 데이터셋 구축. end-to-end autoregressive transformer. 시각품질·파라메트릭 정밀도·기하정확도로 평가. ([프로젝트](https://av.dfki.de/?p=14562))

- **CAD-GPT** (상하이교통대 등, **AAAI 2025**, [arXiv 2412.19663](https://arxiv.org/abs/2412.19663), A): MLLM이 3D 위치·방향 추론에 약해 시작점/돌출방향을 틀리는 문제를 "3D 모델링 공간 메커니즘"으로 해결 — 3D 위치와 스케치 평면 회전각을 **1D 언어 토큰으로 매핑**. LLaVA-1.5 7B(Vicuna) 기반, 단일 이미지 또는 텍스트 입력. 2차 요약(alphaXiv)은 image-to-CAD에서 Chamfer Distance 48%↓, Invalidity Ratio 91%↓ 주장 `[확인 필요 — 원 논문 대조 안 함]`.

- **Text-to-CadQuery** (**2025**, [arXiv 2505.06507](https://arxiv.org/html/2505.06507v1), A): Text2CAD 데이터셋에 **CadQuery 주석 170K** 추가, 오픈소스 LLM 6종 파인튜닝. 최고 모델 top-1 exact match 69.3%(58.8%→), Chamfer Distance 48.6%↓ `[수치는 검색 2차요약, 확인 필요]`. → **"LLM이 코드 대신 계약을 뱉게 하는 것"의 데이터셋 선례.**

- **검증·벤치마크(2024~2026):**
  - **CADCodeVerify / CADPrompt** (2024): 200개 프롬프트 벤치. **검증-수정(verify-and-refine) 루프를 GPT-4에 적용해 point-cloud distance 7.30%↓, compile rate 5.5%↑** — RealCAD의 judge/loop와 같은 철학 `[2차요약, 확인 필요]`.
  - **BenchCAD** ([arXiv 2605.10865](https://arxiv.org/pdf/2605.10865), 2026 프리프린트, A): 106개 산업 부품군 × 17,900 실행가능 CadQuery. **최신 프런티어 모델이 Vision2Code 0.397, 고급연산 recall 25.2%까지 추락** → 복잡 부품은 아직 멀었다는 강한 신호.
  - **MUSE** ([arXiv 2605.28579](https://arxiv.org/pdf/2605.28579), 2026, A): **"Manufacturable, Functional, Assemblable"** text-to-CAD 벤치 — 제조성·조립성·기능성 평가(RealCAD 차별점과 정확히 같은 축). GPT-5.5·GPT-4o·Claude Opus 4.7·Claude 3.7 Sonnet·Gemini 3.1 Pro CadQuery 스크립트 평가 `[모델명·수치 2차요약, 확인 필요]`.
  - **Text2CAD-Bench** ([arXiv 2605.18430](https://arxiv.org/pdf/2605.18430), 2026, A), **Zero-to-CAD** ([arXiv 2604.24479](https://arxiv.org/pdf/2604.24479), 2026, A — 실데이터 없이 백만 규모 해석가능 CAD 프로그램 합성). → **CadQuery가 LLM-CAD 벤치마크의 사실상 표준 타깃이 됨.**

### 2.3 상용 제품

- **Zoo (구 KittyCAD)** — text-to-cad.zoo.dev / zoo.dev:
  - 메시가 아니라 **자체 스크립트 언어 KCL**로 B-rep 생성. "다른 CAD에서 STEP으로 열어 편집 가능"([develop3d](https://develop3d.com/cad/zoo-ecosystem-lays-foundation-for-modern-hardware-design-toolkit/), C).
  - **ML-ephant API** 위에 구축. text→cad, 프롬프트로 반복(iterate), KCL 코드 완성 엔드포인트, `zoo ml text-to-cad` CLI 제공([docs.zoo.dev/docs/developer-tools/api/ml](https://docs.zoo.dev/docs/developer-tools/api/ml/converts-a-proprietary-cad-format-to-kcl), A). 과금: $10로 1,205초, 이후 $0.0083/초.
  - **한계(1차 테스트):** Wevolver 7종 테스트 — 단순 실린더는 정확·편집가능하지만 중/고복잡도에서 급락([Wevolver](https://www.wevolver.com/article/we-tested-7-text-to-cad-tools-are-they-actually-useful-for-engineers), C). Leo AI 리뷰 — 제조성 검증 불가, 팀 기존부품/PDM 이력 못 봄, **단일 부품 범위(어셈블리 아님)**([Leo AI](https://www.getleo.ai/blog/zoo-text-to-cad-review), D). **← RealCAD가 조립성 검증·어셈블리로 정확히 이 빈틈을 공략 가능.**

- **Autodesk Project Bernini** (연구, 비공개): 단일 2D 이미지·다중뷰·점군·voxel·텍스트에서 3D 형상 빠르게 생성, 기능적 변형 여러 개 생성. **1,000만 개** 3D 형상(CAD+유기형 혼합)으로 학습. 형상과 텍스처 분리 생성. 제조 자동화용 파운데이션 모델로 확장 의사([Autodesk News](https://adsknews.autodesk.com/en/?p=48194), B; [Jon Peddie](https://www.jonpeddie.com/news/bernini-grows-legs/), C). "strictly experimental, 공개 안 함".

- **Adobe**: **Substance 3D Viewer의 Text to 3D**(2025 초) — Firefly 이미지 모델을 다중뷰 생성용으로 조정 → 3D 재구성(초 단위)([Adobe Research](https://research.adobe.com/news/breakthrough-research-behind-text-to-3d), B). **Project Neo**(2025.2 퍼블릭 베타)는 생성형이라기보다 **비전문 그래픽 디자이너용 3D 디자인 툴**(벡터 3D → Illustrator 내보내기)([itmedia](https://www.itmedia.co.jp/news/articles/2504/02/news093.html), C). → Adobe는 "비주얼/아트" 방향, 기능부품 CAD 아님.

---

## ③ 커널·파라메트릭 CAD 내부 구조

### 3.1 지오메트리 커널 (B-rep 엔진)

| 커널 | 개발/소유 | 라이선스 | 쓰는 제품 |
|---|---|---|---|
| **Parasolid** | Siemens(1980s~) | 상용 | SolidWorks, Solid Edge, Siemens NX, **Onshape** |
| **ACIS** | Spatial(1986) → Dassault(2000말) | 상용 | SpaceClaim 등 |
| **ShapeManager (ASM)** | Autodesk (2001.11 **ACIS 7.0에서 포크**) | 사내 전용(미판매) | **Autodesk Inventor**, Fusion 계열 `[Fusion 명시 출처 확인 필요]` |
| **OpenCascade (OCCT)** | Open Cascade | **LGPL(상용 거의 무제한)** | **FreeCAD**, **RealCAD(build123d)** |

출처: [engineering.com, "What is a geometric modeling kernel?"](https://www.engineering.com/what-is-a-geometric-modeling-kernel/) (C); [Wikipedia, ShapeManager](https://en.wikipedia.org/wiki/ShapeManager) (C); [MachineDesign, "Autodesk to shape ACIS kernel"](https://www.machinedesign.com/archive/article/21812197/autodesk-to-shape-acis-kernel) (C). ShapeManager는 2001.11 ACIS 7.0 코드에서 포크, Inventor 5.3(2002.2) 첫 탑재, ACIS V7.0 호환 유지.

> **함의:** RealCAD는 **OCCT(build123d 경유)** — 상용 CAD(Parasolid/ACIS)와 같은 진짜 B-rep 커널 계열이다. 즉 치수·연단거리·간섭을 **메시 근사가 아니라 정확 B-rep로 실측**한다는 점이 text-to-mesh류와 근본적으로 다르다.

### 3.2 파라메트릭·구속조건 솔버

- **구속조건 = 기호대수 방정식을 수치해법으로 푼다.** SolveSpace는 구속을 "기호대수 시스템의 방정식"으로 보고 **수정 뉴턴법**으로 수치 해를 구함; 각 점은 XY 평면에서 **2 자유도(DOF)**를 가지며 솔버가 미구속 자유도를 추적·표시([SolveSpace 공식 tech/constraints](https://solvespace.com/tech.pl), A).
- **역사적 계보:** Sketchpad(1963) → D-Cubed(상용 2D DCM, 이후 3D DCM으로 공간 구속 확장). "변분(variational) 스케치를 결정론적 재생성 순서(deterministic regeneration order)로 피처에 연결"한 것이 파라메트릭을 제품 정의 능력으로 만든 전환점([Novedge, 구속 솔버 역사](https://novedge.com/blogs/design-news/design-software-history-from-sketchpad-to-d-cubed-the-evolution-and-algorithms-of-constraint-based-sketchers), C).

### 3.3 피처 히스토리 / 타임라인, 그리고 "토폴로지 네이밍 문제"

- **피처 히스토리** = sketch→feature를 정해진 순서로 재생성(regenerate)하는 타임라인. 파라미터를 바꾸면 전체를 재실행. Zoo의 표현으로 "**롤백 → 스케치 치수 변경 → 연산 재생(replay)**"이 가능한 것이 파라메트릭의 핵심([Zoo](https://zoo.dev/blog/why-ai-must-generate-parametric-cad), D).
- **토폴로지 네이밍 문제(TNP) — 대화형 편집의 근본 난제:** 모델링 연산(pad/cut/fillet 등) 후 형상의 내부 이름(face/edge id)이 바뀌면, 그 참조에 의존하던 파라메트릭 피처가 깨진다. FreeCAD는 이게 OCCT 기반 업데이트 처리 방식에서 비롯되며 특히 PartDesign/TechDraw에서 두드러진다고 기술, **1.0에서 새 네이밍 알고리즘 첫 안정 탑재**([FreeCAD Wiki, Topological naming problem](https://wiki.freecad.org/Topological_naming_problem/en), B; [Ondsel](https://ondsel.com/blog/freecad-topological-naming/), D).

> **RealCAD에 대한 결정적 함의:** "버튼 5개 추가해줘" 같은 **대화형 반복 편집을 피처 참조(face id)로 구현하면 TNP에 똑같이 빠진다.** RealCAD가 참조하는 것은 face id가 아니라 **의미론적 설계계약 필드**(`holes`, `profile.arms`, `enclosure.open_ports`…)다. **즉 "계약 diff" 편집은 TNP를 구조적으로 우회한다 — 이건 RealCAD 아키텍처의 숨은 강점이다**(§6, §7에서 전략화).

---

## ④ 텍스트→3D 메시 생성 & 하이브리드

### 4.1 메시 생성 제품 (2025~2026)

| 도구 | 백엔드/특징 | 강점 | 2026 테스트 평가 |
|---|---|---|---|
| **Rodin (구 Hyper3D)** | Bytedance Deemos | 포토리얼 품질 | 기하 2위, 텍스처·text-to-3D 속도 뒤처짐 |
| **Tripo** | — | 깨끗한 토폴로지·가성비 | **기하 1위·쿼드 토폴로지 1위**, image-to-3D 최속 |
| **Meshy** | 웹, 게임엔진 친화 | PBR 텍스처·텍스처링 | text-to-3D 최속, 복잡형 쿼드 토폴로지 최약 |
| **Luma Genie** | Luma AI | 무료 | (2026 테스트 미포함) |
| **TripoSR** | Stability+Tripo(구형) | 이미지→3D 단일뷰 | 현행 text-to-3D 비교서 거의 안 다뤄짐 |

출처: [RunDiffusion, "AI 3D Model Generators Compared: 2026"](https://learn.rundiffusion.com/ai-3d-model-generators/) (D); [StraySpark, 생성형 3D 비교 2026](https://www.strayspark.studio/blog/generative-3d-tools-comparison-meshy-rodin-tripo-csm-2026) (D); [Scenario, Comparing Generative 3D Models](https://help.scenario.com/en/articles/comparing-generative-3d-models/) (D). **주의: 전부 벤더/제휴성 블로그로 랭킹이 자주 엇갈림 — 방향성으로만 참고.** 가격·버전은 각 벤더 사이트에서 재확인 필요.

### 4.2 메시 vs B-rep — 프린터빌리티·치수정확도

- **테셀레이션은 정확도를 버린다:** B-rep은 정확(exact), 삼각화(STL)는 근사. 삼각형을 잘게 할수록 충실도↑·파일↑([Spatial 블로그](https://blog.spatial.com/stop-losing-cad-accuracy-3d-printing-software-pipeline), D).
- **메시→B-rep 역변환은 "복구가 아니라 표면 피팅"** — 손실적이고 stitching/healing 필요, 제한된 뷰에서 생성된 메시는 non-watertight 가능([Zoo](https://zoo.dev/blog/why-ai-must-generate-parametric-cad), D; [CADExchanger, mesh-to-BRep](https://cadexchanger.com/blog/the-challenge-of-the-polygonal-to-brep-conversion/), D).
- **프린팅 관점에선 포맷보다 지오메트리:** 슬라이서는 어차피 메시를 쓰므로 실제 관건은 **벽두께·피처 크기 대 프린터 해상도·치수정확도**([Leo AI](https://www.getleo.ai/blog/best-text-to-cad-tools-3d-printing), D).
- **정량 비교 데이터는 아직 공백** — text-to-mesh vs B-rep의 치수정확도·출력성공률을 통제 실험한 1차 연구는 검색으로 발견 못 함 `[확인 필요]`.

### 4.3 하이브리드 설계 (RealCAD 핵심)

**정설: 기본(primary) 지오메트리는 파라메트릭 구성, 복잡/유기 디테일은 메시 — "실용적 중간"**([youngju.dev, Generative CAD: Mesh vs B-rep](https://www.youngju.dev/blog/2026-07-31-generative-cad-text-to-3d.en), D). RealCAD는 이 경계를 `contract/schema.py`의 `kind="retrieve"`("파라메트릭 기본형으로 불가한 유기 자유곡면 → 외부 3D 라이브러리 검색")로 **이미 명시적으로 인식**하고 있다. ARCHITECTURE.md도 "피규어·얼굴 같은 유기형 고디테일은 Meshy·Tripo·Muse Image→3D 영역, 치수·공차 검증 안 맞음 → 기능부품에 집중"으로 올바르게 스코프를 잡았다.

> **권장 경계선:**
> - **기능부품**(브래킷·케이스·기어·클램프·홀더·스냅핏) → **파라메트릭 생성 + 커널 검증** (RealCAD 코어, 해자).
> - **유기 자유곡면**(피규어·손잡이 그립·동물·캐릭터) → **retrieve(검색) 또는 generate3d(메시 생성)** 후 **프린터빌리티만** 검증(watertight·벽두께), 치수·조립 검증은 면제.
> - **접착 지점:** 유기형 메시 + 기능 인터페이스(보어·마운트)를 **파라메트릭으로 덧붙이는 "mesh + parametric graft"** — 예: 생성된 손잡이 메시에 파라메트릭 나사보스를 커널로 합집합.

---

## ⑤ 3D프린터 / 슬라이서 / 프린터빌리티

### 5.1 슬라이서 아키텍처

- **한 계보(엔진 공유):** Slic3r → **PrusaSlicer** → **Bambu Studio** → **OrcaSlicer**. 각 세대가 코어 슬라이싱 엔진을 유지하고 그 위에 레이어를 더함. OrcaSlicer는 Bambu Studio·PrusaSlicer 기반에 Cura·SuperSlicer 아이디어 결합([SimplyPrint, Bambu vs Orca](https://simplyprint.io/articles/bambu-studio-vs-orcaslicer), D; Bambu/Orca GitHub 리드미, B).
- **Cura는 별도 엔진**(CuraEngine) — 프로파일 호환 안 됨([SimplyPrint](https://simplyprint.io/articles/orcaslicer-vs-bambu-studio), D). `[CuraEngine·libslic3r 모듈 구조 세부는 저장소 직접 확인 필요]`
- **공통 파이프라인(일반론):** STL/3MF 로드 → 메시 수선 → 슬라이스(레이어화) → perimeter/infill/support 생성 → G-code. (RealCAD는 **G-code 생성까지 안 가고 "출력 가능한 STEP/STL/3MF" 산출 + 프린터빌리티 사전검증**이 범위 — 올바른 스코프.)

### 5.2 포맷 파이프라인: STL / 3MF / STEP

| 포맷 | 담는 것 | 편집 | 프린팅 |
|---|---|---|---|
| **STEP** | 정확 수학 지오메트리(곡선·호·필렛) | 파라메트릭 CAD 편집 best | 슬라이서가 **메시로 변환해야 함** |
| **3MF** | XML+ZIP 컨테이너: 단위·색·재료·어셈블리 계층·슬라이서 설정 | 중간 | **단위 명시(mm) → 스케일 오류↓**, STL보다 2~5배 작음 |
| **STL** | 삼각형 표면만 | 불가("passive geometric shell") | 색·단위 없음, import시 단위 지정 필요 |

출처: [Onshape, STL vs 3MF](https://www.onshape.com/en/resource-center/tech-tips/stl-vs-3mf-files-additive-manufacturing) (B); [Sovol3D, STL vs 3MF vs STEP](https://www.sovol3d.com/blogs/news/stl-vs-3mf-vs-step-which-3d-file-format-should-you-use-for-fdm-printing) (D). **→ RealCAD 권장 기본 출력 = 3MF(단위·메타·어셈블리 보존) + STEP(편집용) + STL(호환).** 이미 pyproject에 lxml(3MF XML 처리)·manifold3d 있음.

### 5.3 프린터빌리티 규칙 (FDM, DfAM)

- **오버행:** 수직 기준 **~45°**가 자립 한계; 더 가파르면 서포트 필요. 브리지는 별도로 ~10~15mm(최대 20mm)까지 가능([cadcrowd DfAM](https://www.cadcrowd.com/blog/design-for-3d-printing-dfam-rules-for-fdm-sla-and-sls-parts-that-actually-work/), D; [core77](https://www.core77.com/posts/74401/Design-Rules-for-3D-Printing), D).
- **최소 벽두께:** 출처마다 다름 — **노즐 폭의 정수배**(0.4mm 노즐 → 0.8/1.2/1.6mm)가 가장 원칙적. 일반 최소 0.8~1.2mm, **구조부 1.5~2.0mm 권장**([printpal 설계 가이드](https://printpal.io/docs/3d-printing-design-guide), D; [wevolver](https://www.wevolver.com/article/fdm-3d-printing-design-tips-best-practices-and-techniques-for-stronger-prints), D).
- **구멍:** ≤10mm 구멍은 지름 2~4% 키움(수축 보정)([grabcad](https://cad.grabcad.com/tutorials/3d-printing-design-guidelines), D). **← RealCAD calibration/tolerance.py의 공차 오프셋과 직결.**
- **주의:** 전부 벤더/블로그 가이드로 1차 표준 아님 — 특정 프린터/재료는 제조사 스펙으로 재확인. RealCAD는 이 값들을 **프린터 프로파일(노즐·재료) 파라미터**로 받아 검증하는 게 정석.

### 5.4 대형 모델 분할

- **Chopper** (Luo·Baran·Rusinkiewicz·Matusik, **SIGGRAPH Asia 2012**, ACM TOG, [Princeton/MIT](https://gfx.cs.princeton.edu/pubs/Luo_2012_CPM/chopper.pdf), A): 빌드볼륨 초과 모델을 **조립 용이성·부품 수·솔기 비가시성·구조 건전성**을 최적화해 자동 분할, **인터페이스에 커스텀 커넥터(정렬 조인트) 출력**. RealCAD `printing/chopper.py`·`mesh_split.py`가 바로 이 계열. (Luban은 검색으로 Chopper 연관 확인 못 함 `[확인 필요]`.)
- **RealCAD 적용:** ARCHITECTURE.md의 "프린터 베드보다 크면 → 최적 분할면 + 정렬 조인트(도브테일·핀·나사보스) 자동 추가 + 재조립 가이드"는 Chopper 원리와 정확히 일치. **파라메트릭이라 분할면에서 조인트를 커널로 정밀 생성**할 수 있는 게 메시 분할 대비 우위.

---

## ⑥ 대화형 편집 & 초보-전문가 UX

### 6.1 대화형/반복 편집 — 최신 연구

- **IterCAD** ([arXiv 2606.13368](https://www.themoonlight.io/en/review/itercad-an-iterative-multimodal-agent-for-visually-grounded-cad-generation-and-editing), 2026, A): CAD를 **"에이전트가 CAD 샌드박스에서 코드를 실행하는 닫힌 루프"**로 봄. 3개 태스크 중 **Interactive Editing = 증분 지시로 기존 프로그램을 국소 수정**. 매 턴 **전체 상호작용 이력**을 보고 reasoning + CadQuery 코드블록/종료토큰 출력. **compiler·runtime·렌더뷰 피드백**으로 generate-verify-refine. ← **RealCAD judge/loop의 정확한 학술판.**
- **PR-CAD / ChatCAD** ([arXiv 2604.19773](https://arxiv.org/pdf/2604.19773), 2026, A): **대화형 지시로 여러 턴에 걸쳐 CAD 모델을 다듬고 업데이트** — 단계 간 전이 처리, 단순 대화로 설계 수정 지원.
- **Text2CAD**: "초보자~전문가 프롬프트 전부" = 대화형 난이도 적응의 데이터셋 기반(§2.2).

> **"리모컨 만들어줘 → 버튼 5개 추가해줘" 구현 전략:** 위 연구들은 **CadQuery 코드 diff**로 반복한다 → TNP·코드 에러 리스크. **RealCAD는 "설계계약 JSON diff"로 반복** = LLM이 전체 코드가 아니라 **"무엇을 바꿀지"만** 계약 필드 patch로 뱉고(`holes += 5`, `profile.arms = 8`), 신뢰된 빌더가 재생성·재검증. 이게 더 안전하고 더 설명가능(explainable)하다.

### 6.2 초보-전문가 겸용 UX — 양 극단과 RealCAD의 중간해

| | Tinkercad | 전문 CAD(SolidWorks/Fusion) | **RealCAD 목표** |
|---|---|---|---|
| 진입 | 브라우저·즉시·블록조합(CSG) | 설치·툴바 과다·학습곡선 | 대화로 즉시 시작 |
| 정밀 | 낮음(필렛·정밀 약함) | 완전 파라메트릭·구속 | 파라메트릭 + 커널 검증 |
| 편집 | 블록 드래그 | 피처 트리·스케치 | **파라미터 칩/슬라이더 + 계약 diff 대화** |
| 한계 | 복잡·고디테일 불가 | 비전문가 이탈 | 모드 분리로 양쪽 |

출처: [Wikipedia, Tinkercad](https://en.wikipedia.org/wiki/Tinkercad) (C); [3DNatives, Tinkercad](https://www.3dnatives.com/en/tinkercad-all-you-need-to-know-120320204/amp/) (C) — CSG 기반이라 "깨끗한 watertight 모델" 산출, 교육용, 복잡/고디테일엔 부적합.

**RealCAD UX 원칙(ARCHITECTURE.md + 연구 반영):**
1. **되묻기 최소화(clarify, ProCAD식):** `agent/clarify.py`가 이미 "거의 아무것도 묻지 말라, 꼭 1개 치명적 정보만, 기본값 제안과 함께"로 구현. 유기형은 아예 안 묻고 retrieve로 넘김. **← 정설과 일치(질문 폭주 = 초보 이탈).**
2. **"무엇이 진짜고 무엇이 미리보기인지" 명확히:** text-to-cad의 최대 함정이 "편집 안 되는 비주얼 브리프"([Leo AI](https://www.getleo.ai/blog/how-text-to-cad-works), D) → RealCAD는 **검증 통과 + 진짜 STEP/STL = "실제로 조립/출력됨"을 리포트로 증명**.
3. **수정 = 재프롬프트가 아니라 파라미터 칩/슬라이더** (ARCHITECTURE.md): "실패 시 파라미터 dict 반환" 패턴과 직결 — 초보는 칩, 전문가는 수치 직접 입력.
4. **검증 리포트를 사람 말로:** "볼트가 벽에 닿아요 → 구멍 5mm 옮길까요?" — 자동수정 제안을 자연어로.

---

## ⑦ RealCAD 권장 아키텍처 + 단계별 로드맵

### 7.1 통합 아키텍처 (목표 상태)

```
사용자 프롬프트 (+사진/PDF/기준물)
  │
  ├─▶ [router]   요구 분류: 기능부품? 유기형? 혼합?
  │                  │
  │    ┌─────────────┼───────────────────────────┐
  │    ▼             ▼                           ▼
  │ [clarify]   기능부품 경로                 유기형 경로
  │ 꼭 필요한 1개만    │                           │
  │    │         [planner→DesignContract JSON]   [retrieve] 외부 라이브러리 검색
  │    │              │  (파라메트릭 레시피)       [generate3d] 메시 생성(Meshy/Tripo/Bernini류)
  │    │         [builder] build123d/OCC           │
  │    │              │  + 표준 볼트/피처           ▼
  │    │              │                      [mesh verify] watertight·벽두께만
  │    │         [verify] 커널 실측 ◀───────────────┘ (+선택: parametric graft = 기능 인터페이스 덧붙이기)
  │    │          간섭·연단·체결·동축·프린터빌리티
  │    │              │
  │    │         ┌────┴─── 실패 ─▶ [judge] 수정 지시 ─▶ 계약 patch(diff) ─▶ builder (루프 N회)
  │    │         └─ 통과 ─▶ [printability] 베드 초과시 [chopper] 분할+정렬조인트
  │    │                         │
  │    └──────────── 대화형 편집 ─┤  "버튼 5개 추가" → LLM이 계약 JSON diff만 생성 → 재빌드·재검증
  │                              ▼
  │                         [export] STEP + 3MF(단위·메타) + STL + BOM
  │                              │
  └─────────────────────────────┴─▶ 웹/앱: 3D 뷰어 + 자연어 검증 리포트 + 파라미터 칩/슬라이더
```

**설계 원칙 3가지(연구가 뒷받침):**
1. **"파라메트릭 레시피(설계계약) = 단일 진실원천"** — LLM은 코드/메시를 직접 뱉지 않고 검증 가능한 계약만 생성·수정. (Zoo "parametric recipe", DeepCAD "명령열", Text-to-CadQuery 선례)
2. **생성자 ≠ 판정자 분리 + verify-refine 루프** — 자기승인 편향 회피, 커널 실측으로 판정. (CADCodeVerify·IterCAD·MUSE가 같은 방향)
3. **편집은 "계약 diff"로** — face id 참조를 피해 TNP 구조적 우회. (FreeCAD TNP 교훈)

### 7.2 단계별 로드맵

> 범례: ✅=이미 있음 / 🔨=확장 / 🆕=신규. RealCAD 현 구조 기준(contract·builder·verify·fasteners·printing/chopper·retrieval·web 스캐폴드 존재).

**Phase 0 — 대화형 편집(계약 diff) [최우선, 차별화 즉효]**
- 🆕 `agent/editor.py`: 기존 `DesignContract` + 사용자 후속 지시("버튼 5개 추가") → **계약 JSON patch(diff)** 생성(전체 재생성 아님). judge/loop 재사용.
- 🔨 web/app.py에 세션 상태(현 계약 보관) + "수정" 엔드포인트. 뷰어에 **파라미터 칩/슬라이더**(계약 필드 바인딩).
- 🔨 검증 리포트를 자연어 수정 제안("구멍 5mm 옮길까요?")으로. 근거: IterCAD/PR-CAD, ARCHITECTURE UX.
- **산출 메시지:** "리모컨 만들어줘 → 버튼 5개 추가해줘"가 실제로 됨.

**Phase 1 — 프린터빌리티 자동수정 루프 완성 [해자 강화]**
- 🔨 `verify/printability.py`(또는 신규): 오버행>45°·최소벽두께(노즐 정수배)·watertight를 **프린터 프로파일(노즐·재료·베드) 파라미터**로 검증. 근거 §5.3.
- 🔨 실패 → judge가 **계약 파라미터 수정 지시**(벽두께↑, 필렛 추가)로 자동수정(기존 루프에 프린터빌리티 코드 추가).
- 🔨 `calibration/tolerance.py`: 구멍 2~4% 보정·클리어런스 오프셋을 계약에 반영.
- 🔨 export: **3MF 기본화**(단위·메타·어셈블리 — lxml 활용) + STEP + STL.

**Phase 2 — 하이브리드(retrieve + generate3d) [스코프 확장]**
- 🔨 `retrieval/library.py`: 검색 후보 반환 → **선택 모델 다운로드 → trimesh watertight 검증 → 베드 초과시 mesh_split**까지(현 TODO 구현).
- 🆕 `agent/generate3d.py`: 유기형 → text-to-3D 메시 생성 API 연동(Meshy/Tripo/Bernini류, §4.1). **치수·조립 검증 면제, 프린터빌리티만**.
- 🆕 (선택) **parametric graft**: 생성 메시 + 기능 인터페이스(나사보스·마운트)를 커널 합집합 → 하이브리드 부품. 근거 §4.3.

**Phase 3 — 피처 히스토리(계약 이력) & explainability**
- 🆕 설계계약을 **이력(버전 체인)**으로 보관 = 피처 타임라인의 의미론적 대체물. 각 편집이 계약 diff이므로 **롤백·분기·재생이 자연스럽다**(코드 replay 없이). TNP 무풍지대.
- 🔨 "왜 이 수치?"에 규격 근거(ASME B18.2.8 등) 추적 — 신뢰 강화.

**Phase 4 — 멀티파트 어셈블리 & 대형분할 프로덕션화 [Zoo 빈틈 공략]**
- 🔨 어셈블리 구속(맞물림 부품 구멍 동축·체결) — Zoo가 "단일 부품만"인 지점을 어셈블리로 추월(§2.3).
- 🔨 `printing/chopper.py` 프로덕션화: Chopper식 최적 분할 + 정렬 조인트(도브테일·핀·나사보스) 커널 생성 + 재조립 가이드. 근거 §5.4.
- 🔨 앱(React Native) — 동일 FastAPI 공유(ARCHITECTURE 플랫폼안).

### 7.3 RealCAD의 방어 가능한 차별점 (연구 대조 요약)

| 차별점 | 경쟁(Zoo/DeepCAD/Meshy 등) | 근거 |
|---|---|---|
| **커널 실측 조립성 검증** (볼트 간섭·연단·체결) | 대부분 Chamfer Distance 등 형상 유사도만 | MUSE가 뒤늦게 같은 축 제시(§2.2) |
| **설계계약 diff 편집** (TNP 우회) | 코드 diff(IterCAD) → TNP·에러 리스크 | FreeCAD TNP(§3.3), IterCAD(§6.1) |
| **하이브리드 경계 명시** (기능=파라메트릭/유기=메시) | 대개 한쪽만 | §4.3 정설 |
| **프린터빌리티+대형분할 통합** | text-to-cad는 거의 미지원 | Chopper(§5.4), DfAM(§5.3) |
| **어셈블리** | Zoo "단일 부품만" | §2.3 |

---

## ⑧ 참고문헌 (출처별 품질 A~E)

> **등급:** A=1차(peer-reviewed/arXiv·공식 스펙·공식 제품 문서) · B=공식 블로그/연구 페이지·신뢰 기술매체 · C=업계 매체/백과 · D=벤더·일반 블로그(이해상충 가능) · E=SEO/미검증. 상충 시 본문에 명시.

**A — 1차 (논문·공식 문서·공식 제품 API)**
- DeepCAD (Wu et al., ICCV 2021) — https://arxiv.org/abs/2105.09492
- Text2CAD (Khan et al., NeurIPS 2024) — https://arxiv.org/abs/2409.17106 · https://av.dfki.de/?p=14562
- CAD-GPT (AAAI 2025) — https://arxiv.org/abs/2412.19663
- Text-to-CadQuery (2025) — https://arxiv.org/html/2505.06507v1
- BenchCAD (2026 preprint) — https://arxiv.org/pdf/2605.10865
- MUSE: Manufacturable/Functional/Assemblable (2026 preprint) — https://arxiv.org/pdf/2605.28579
- Text2CAD-Bench (2026 preprint) — https://arxiv.org/pdf/2605.18430
- Zero-to-CAD (2026 preprint) — https://arxiv.org/pdf/2604.24479
- IterCAD (2026 preprint) — https://www.themoonlight.io/en/review/itercad-an-iterative-multimodal-agent-for-visually-grounded-cad-generation-and-editing (리뷰 경유; 원 arXiv 2606.13368)
- PR-CAD / ChatCAD (2026 preprint) — https://arxiv.org/pdf/2604.19773
- Chopper (SIGGRAPH Asia 2012, ACM TOG) — https://gfx.cs.princeton.edu/pubs/Luo_2012_CPM/chopper.pdf
- SolveSpace 공식(solver tech/constraints) — https://solvespace.com/tech.pl · https://solvespace.com/constraints.pl
- Zoo ML API 문서 — https://docs.zoo.dev/docs/developer-tools/api/ml/converts-a-proprietary-cad-format-to-kcl

**B — 공식 블로그/연구 페이지·신뢰 매체**
- Autodesk News, Project Bernini — https://adsknews.autodesk.com/en/?p=48194
- Adobe Research, Text to 3D 연구 — https://research.adobe.com/news/breakthrough-research-behind-text-to-3d
- FreeCAD Wiki, Topological naming problem — https://wiki.freecad.org/Topological_naming_problem/en
- Onshape, STL vs 3MF — https://www.onshape.com/en/resource-center/tech-tips/stl-vs-3mf-files-additive-manufacturing

**C — 업계 매체/백과**
- engineering.com, geometric modeling kernel — https://www.engineering.com/what-is-a-geometric-modeling-kernel/
- Wikipedia, ShapeManager — https://en.wikipedia.org/wiki/ShapeManager
- Wikipedia / 3DNatives, Tinkercad — https://en.wikipedia.org/wiki/Tinkercad · https://www.3dnatives.com/en/tinkercad-all-you-need-to-know-120320204/amp/
- MachineDesign, Autodesk/ACIS — https://www.machinedesign.com/archive/article/21812197/autodesk-to-shape-acis-kernel
- Novedge, 구속 솔버/커널 역사 — https://novedge.com/blogs/design-news/design-software-history-from-sketchpad-to-d-cubed-the-evolution-and-algorithms-of-constraint-based-sketchers
- develop3d, Zoo 생태계 — https://develop3d.com/cad/zoo-ecosystem-lays-foundation-for-modern-hardware-design-toolkit/
- Wevolver, 7 text-to-cad 테스트 — https://www.wevolver.com/article/we-tested-7-text-to-cad-tools-are-they-actually-useful-for-engineers
- Jon Peddie Research, Bernini — https://www.jonpeddie.com/news/bernini-grows-legs/
- itmedia, Adobe Project Neo — https://www.itmedia.co.jp/news/articles/2504/02/news093.html

**D — 벤더/일반 블로그 (이해상충 가능, 보조)**
- Zoo, "Why AI Must Generate Parametric CAD" — https://zoo.dev/blog/why-ai-must-generate-parametric-cad
- Leo AI, How Text-to-CAD Works / Zoo review / best for 3D printing — https://www.getleo.ai/blog/how-text-to-cad-works · https://www.getleo.ai/blog/zoo-text-to-cad-review · https://www.getleo.ai/blog/best-text-to-cad-tools-3d-printing
- CADExchanger, mesh-to-BRep — https://cadexchanger.com/blog/the-challenge-of-the-polygonal-to-brep-conversion/
- Spatial, CAD accuracy pipeline — https://blog.spatial.com/stop-losing-cad-accuracy-3d-printing-software-pipeline
- youngju.dev, Generative CAD: Mesh vs B-rep (2026) — https://www.youngju.dev/blog/2026-07-31-generative-cad-text-to-3d.en
- RunDiffusion / StraySpark / Scenario, 생성형 3D 비교 — https://learn.rundiffusion.com/ai-3d-model-generators/ · https://www.strayspark.studio/blog/generative-3d-tools-comparison-meshy-rodin-tripo-csm-2026 · https://help.scenario.com/en/articles/comparing-generative-3d-models/
- SimplyPrint, Bambu vs Orca 슬라이서 계보 — https://simplyprint.io/articles/bambu-studio-vs-orcaslicer
- DfAM 규칙: cadcrowd / printpal / core77 / grabcad / wevolver — https://www.cadcrowd.com/blog/design-for-3d-printing-dfam-rules-for-fdm-sla-and-sls-parts-that-actually-work/ · https://printpal.io/docs/3d-printing-design-guide · https://www.core77.com/posts/74401/Design-Rules-for-3D-Printing · https://cad.grabcad.com/tutorials/3d-printing-design-guidelines
- Ondsel, FreeCAD topological naming — https://ondsel.com/blog/freecad-topological-naming/
- Sovol3D, STL vs 3MF vs STEP — https://www.sovol3d.com/blogs/news/stl-vs-3mf-vs-step-which-3d-file-format-should-you-use-for-fdm-printing

**미해결/확인 필요 항목**
- CAD-GPT·Text-to-CadQuery·CADCodeVerify의 구체 수치(CD·recall·exact match)는 2차 요약 기반 → 원 논문 대조 필요.
- MUSE의 평가 모델명(GPT-5.5·Claude Opus 4.7·Gemini 3.1 Pro)·수치는 검색 2차요약 → 원 논문 확인.
- Fusion 360이 ShapeManager(ASM)를 쓰는지 1차 확정 출처 미발견(Inventor는 확정).
- Luban과 Chopper의 관계 미확인.
- CuraEngine·libslic3r 내부 모듈 구조 세부 미확인(저장소 직접 확인 필요).
- text-to-mesh vs B-rep 치수정확도/출력성공률 통제 실험 1차 연구 미발견.
- 2026-dated arXiv 프리프린트(2604~2606)는 검색 결과 기반으로 식별 — 개별 PDF 대조는 미수행.
