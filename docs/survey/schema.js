// 설문 문항 정의 — 브라우저와 서버가 같은 파일을 읽는다.
// 클라이언트는 <script type="module"> 로, api/submit.js 는 상대경로 import 로 가져간다.
// 보기 값은 1부터. 한 번 배포한 뒤에는 값을 재배열하지 말 것 — 집계가 어긋난다.
// 문항을 고쳐야 하면 VERSION 을 올리고, 집계 시 v 로 분리한다.
//
// v2 — LLM 으로 보고서를 쓸 때 생기는 문제를 측정 대상에 넣었다.
//      v1 은 "손으로 쓰는 사람"만 전제해 근거 추적·기관 맥락·재검증 비용을 전혀 묻지 못했다.
// v3 — 두 가지 제약을 동시에 맞췄다.
//      ① 모든 문항의 보기를 5개 이하로 ("해당 없음" 포함).
//         보기가 길어질수록 뒤쪽이 덜 선택되는 순서 편향이 커진다.
//      ② 어느 경로로 들어와도 정확히 10문항.
//         공통 8 + 경로별 2 로 짰다. Q2 가 분기 게이트다.
//           · LLM 을 쓰거나 써본 사람  → Q4 · Q5  (되돌리는 비용 · 실패 유형)
//           · 써본 적 없는 사람        → Q2n · Q2m (안 쓰는 이유 · 남의 LLM 문서를 검토한 경험)
//      압축하며 잃은 세부는 하위 문항으로 내렸다 — 서식이 1위로 나오면 그때 다시 쪼개 묻는다.

export const VERSION = 3;

export const SECTIONS = {
  A: { label: '배경', note: '응답자 · LLM 사용 여부' },
  B: { label: 'LLM 과 보고서', note: '쓰든 안 쓰든' },
  C: { label: '현행 부담', note: '어디에 시간이 드는가' },
  D: { label: '작업 환경', note: '배포 경로 판단' },
  E: { label: '수요', note: '' },
};

// 쓰거나 써본 사람 / 한 번도 안 써본 사람. 둘을 합치면 항상 2문항이 붙는다.
const HAS_USED = { q2: [1, 2, 3, 4] };
const NEVER_USED = { q2: [5] };

export const QUESTIONS = [
  /* ── A. 배경 (공통 2) ────────────────────────────── */
  {
    id: 'q1', section: 'A', type: 'single',
    text: '최근 3개월간 본인이 직접 작성해 제출한 기관 보고서(hwp · hwpx 제출본)는 몇 건입니까?',
    hint: '결재를 올린 문서 기준입니다 — 검토보고 · 계획보고 · 결과보고 · 회의자료 등.',
    options: ['0건', '1~2건', '3~5건', '6~10건', '11건 이상'],
  },
  {
    id: 'q2', section: 'A', type: 'single',
    text: '보고서를 만들 때 LLM(ChatGPT · Claude · Gemini 등)을 쓰십니까?',
    hint: '이 답에 따라 이후 문항이 달라집니다. 어느 쪽이든 문항 수는 10개로 같습니다.',
    options: [
      '거의 매번 쓴다',
      '자주 쓴다',
      '가끔 쓴다',
      '써봤지만 지금은 쓰지 않는다',
      '써본 적 없다',
    ],
  },

  /* ── B. LLM 과 보고서 (경로별 2) ─────────────────── */
  {
    id: 'q4', section: 'B', type: 'single', showIf: HAS_USED,
    text: 'LLM 이 내놓은 결과를 그대로 쓰지 못하고 확인 · 수정하는 데 보고서 1건당 얼마나 걸립니까?',
    hint: '“얼마나 아꼈나”가 아니라 “얼마나 되돌렸나”를 묻는 문항입니다.',
    options: [
      '거의 없다 — 대체로 그대로 쓴다',
      '30분 미만',
      '30분 ~ 1시간',
      '1 ~ 2시간',
      '2시간 이상 — 직접 쓰는 편이 빠를 때도 있다',
    ],
  },
  {
    id: 'q5', section: 'B', type: 'multi', min: 1, showIf: HAS_USED,
    text: 'LLM 결과에서 겪은 문제를 모두 골라 주십시오.',
    options: [
      '없는 수치 · 사실을 지어내거나, 출처를 대지 못했다',
      '우리 기관 · 업무 맥락을 몰라 매번 다시 설명해야 했다 — “KCA” 를 한국소비자원으로 아는 식',
      '개조식(□ · ㅇ · -) · 기관 문투 · 표 서식에 맞지 않아 손봐야 했다',
      '보안 · 망분리 때문에 필요한 내부 자료를 넣지 못했다',
    ],
    noneOption: '별다른 문제는 없었다',
  },
  {
    id: 'q2n', section: 'B', type: 'single', showIf: NEVER_USED,
    text: '쓰지 않으시는 가장 큰 이유는 무엇입니까?',
    options: [
      '보안 · 규정 위반이 걱정된다',
      '결과를 믿기 어렵다 — 확인하는 게 더 일이다',
      '업무망 · VDI 에서 접근이 막혀 있다',
      '어떻게 써야 할지 모르겠다',
      '지금 방식으로 충분하다',
    ],
  },
  {
    id: 'q2m', section: 'B', type: 'multi', min: 1, showIf: NEVER_USED,
    text: 'LLM 으로 작성된 것으로 보이는 문서를 검토 · 결재하며 겪은 일을 모두 골라 주십시오.',
    options: [
      '수치 · 사실이 틀려 되돌려 보냈다',
      '출처를 물었더니 대지 못했다',
      '문체 · 형식이 어색해 손봐야 했다',
      '겉으로는 알아채기 어려웠다',
    ],
    noneOption: '그런 문서를 검토한 적 없다',
  },

  /* ── C. 현행 부담 (공통 4) ───────────────────────── */
  {
    id: 'q6', section: 'C', type: 'single',
    text: '보고서에 인용한 수치 · 사실의 근거를 어떻게 확인하십니까?',
    options: [
      '모든 수치 · 인용을 원문에서 직접 확인한다',
      '중요해 보이는 것만 골라 확인한다',
      '자료를 그대로 옮겨 적으므로 따로 확인하지 않는다',
      '확인하고 싶어도 원본을 다시 찾기 어렵다',
      '따로 확인하지 않는다',
    ],
  },
  {
    id: 'q7', section: 'C', type: 'single',
    text: '보고서 1건을 만들 때, 내용 작성을 제외한 서식 · 정리 작업에 평균 얼마나 쓰십니까?',
    hint: '글머리 계층 · 서체 · 표 · 각주 · 붙임 등 문서를 “모양대로” 만드는 데 드는 시간만.',
    options: ['30분 미만', '30분 ~ 1시간', '1 ~ 2시간', '2 ~ 3시간', '3시간 이상'],
  },
  {
    id: 'q8', section: 'C', type: 'single',
    text: '보고서 한 건에서 가장 많은 시간을 잡아먹는 일 하나만 고른다면?',
    hint: '여러 개가 떠오르셔도 가장 큰 것 하나만 골라 주십시오.',
    options: [
      '자료 조사 · 근거 확인 — 예전에 찾은 것을 다시 찾는 일 포함',
      '초안 문장 쓰기 · 다듬기',
      'LLM 이 준 결과를 검수 · 수정하기',
      '한글 서식 맞추기 — 계층 · 서체 · 표 · 각주 · 붙임',
      '여기 없는 다른 것이 더 크다',
    ],
  },
  {
    // q8 에서 서식을 고른 사람에게만. 5개 상한 때문에 q8 에서 뭉갠 세부를 여기서 되찾는다.
    id: 'q8b', sub: true, section: 'C', type: 'single', showIf: { q8: [4] },
    text: '그 서식 작업 중에서도 가장 오래 걸리는 것은 무엇입니까?',
    options: [
      '글머리 계층(□ → ㅇ → -) 맞추기',
      '표 폭 · 정렬 맞추기',
      '서체 · 크기 · 줄간격 맞추기',
      '각주 · 출처 표기',
      '붙임 배너 · 머리말 · 목차 · 쪽번호',
    ],
  },
  {
    id: 'q9', section: 'C', type: 'multi', min: 1,
    text: '다음 중 경험한 것을 모두 골라 주십시오.',
    options: [
      '업무망 자료교환에서 파일이 반려됨 — 예: hwpx 를 일반 압축파일로 판정',
      '서식 때문에 반송되거나 마감을 넘김',
      '출처 · 사실관계를 다시 대라는 요구를 받음',
      '“AI 로 쓴 것 아니냐”는 지적을 받음',
    ],
    noneOption: '해당 없음',
  },

  /* ── D. 작업 환경 (공통 1) ───────────────────────── */
  {
    id: 'q10', section: 'D', type: 'multi', min: 1,
    text: '보고서 작성은 주로 어디에서 하십니까?',
    options: [
      '인터넷망 VDI',
      '업무망 PC',
      '업무용 노트북(프로그램 설치 권한 있음)',
      '그 밖의 환경',
    ],
  },

  /* ── E. 수요 (공통 1) ────────────────────────────── */
  {
    id: 'q11', section: 'E', type: 'single',
    text: '내용을 붙여넣으면 인용마다 출처가 따라붙고, 기관 양식에 맞춘 hwpx 까지 나오는 도구가 있다면 쓰시겠습니까?',
    hint: '설치 · 계정 · API 키 · 교육 없이 VDI 브라우저에서 그대로 쓰는 형태를 가정합니다.',
    options: ['바로 쓰겠다', '조건이 맞으면 쓰겠다', '판단 보류', '쓰지 않겠다'],
  },
  {
    id: 'q11c', sub: true, section: 'E', type: 'single', showIf: { q11: [2] },
    text: '어떤 조건이 맞아야 쓰시겠습니까?',
    options: [
      '보안 · 망분리 관련 승인이 되면',
      '부서 표준 도구로 정해지면',
      '결과물 품질을 직접 확인한 뒤',
      '교육 없이 바로 쓸 수 있다면',
    ],
  },
  {
    id: 'q11r', sub: true, section: 'E', type: 'single', showIf: { q11: [4] },
    text: '쓰지 않으시는 이유는 무엇입니까?',
    options: [
      '지금 방식으로 충분하다',
      '보안 · 망분리가 걸릴 것 같다',
      '결과물을 신뢰하기 어렵다',
      '새로 익히는 부담이 크다',
    ],
  },
];

export const BY_ID = Object.fromEntries(QUESTIONS.map((q) => [q.id, q]));

/** 이 응답 상태에서 해당 문항이 화면에 뜨는가. */
export function isShown(q, answers) {
  return !q.showIf || Object.entries(q.showIf).every(([dep, vals]) => vals.includes(answers[dep]));
}

/**
 * 제출 payload 검증. 클라이언트와 서버가 같은 규칙을 쓴다.
 * @returns {string[]} 위반 목록. 빈 배열이면 통과.
 */
export function validate(answers) {
  const errs = [];
  for (const q of QUESTIONS) {
    const shown = isShown(q, answers);
    const v = answers[q.id];

    if (!shown) {
      if (v !== undefined) errs.push(`${q.id}: 표시되지 않는 문항에 응답`);
      continue;
    }

    if (q.type === 'single') {
      const max = q.options.length + (q.noneOption ? 1 : 0);
      if (!Number.isInteger(v) || v < 1 || v > max) errs.push(`${q.id}: 보기 범위를 벗어남`);
      continue;
    }

    // multi
    const noneVal = q.noneOption ? q.options.length + 1 : null;
    if (!Array.isArray(v)) { errs.push(`${q.id}: 배열이 아님`); continue; }
    if (new Set(v).size !== v.length) errs.push(`${q.id}: 중복 선택`);
    if (v.some((n) => !Number.isInteger(n) || n < 1 || n > q.options.length + (noneVal ? 1 : 0))) {
      errs.push(`${q.id}: 보기 범위를 벗어남`);
    }
    if (noneVal && v.includes(noneVal) && v.length > 1) errs.push(`${q.id}: “해당 없음”은 단독 선택`);
    if (q.min && v.length < q.min) errs.push(`${q.id}: 최소 ${q.min}개 선택`);
    if (q.max && v.length > q.max) errs.push(`${q.id}: 최대 ${q.max}개 선택`);
  }

  const known = new Set(QUESTIONS.map((q) => q.id));
  for (const k of Object.keys(answers)) if (!known.has(k)) errs.push(`${k}: 알 수 없는 항목`);

  return errs;
}
