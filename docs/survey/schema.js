// 설문 문항 정의 — 브라우저와 서버가 같은 파일을 읽는다.
// 클라이언트는 <script type="module"> 로, api/submit.js 는 상대경로 import 로 가져간다.
// 보기 값은 1부터. 한 번 배포한 뒤에는 값을 재배열하지 말 것 — 집계가 어긋난다.
// 문항을 고쳐야 하면 VERSION 을 올리고, 집계 시 v 로 분리한다.

export const VERSION = 1;

export const SECTIONS = {
  A: { label: '실태', note: '응답자 배경' },
  B: { label: '고통의 위치', note: '어느 작업이 시간을 먹는가' },
  C: { label: '사고 이력', note: '리스크 근거' },
  D: { label: '작업 환경', note: '배포 경로 판단' },
  E: { label: '수요', note: '' },
};

// Q3·Q10 이 공유하는 작업 목록. 두 문항의 보기 값이 같아야 교차 집계가 된다.
const TASKS = [
  '글머리 계층(□ → ㅇ → -) 맞추기',
  '서체 · 크기 · 줄간격 맞추기',
  '표 폭 · 정렬 맞추기',
  '각주 · 출처 표기',
  '붙임 배너 · 머리말',
  '목차 · 쪽번호',
  '예전에 찾은 자료를 다시 찾기',
  '인용한 수치의 근거 재확인',
  '문장 다듬기(문체 · 개조식화)',
];

export const QUESTIONS = [
  {
    id: 'q1', no: 1, section: 'A', type: 'single',
    text: '최근 3개월간 본인이 직접 작성해 제출한 기관 보고서(hwp · hwpx 제출본)는 몇 건입니까?',
    options: ['0건', '1~2건', '3~5건', '6~10건', '11건 이상'],
  },
  {
    id: 'q2', no: 2, section: 'A', type: 'single',
    text: '보고서 1건을 만들 때, 내용 작성을 제외한 서식 · 정리 작업에 평균 얼마나 쓰십니까?',
    hint: '글머리 계층 · 서체 · 표 · 각주 · 붙임 등 문서를 “모양대로” 만드는 데 드는 시간만.',
    options: ['30분 미만', '30분 ~ 1시간', '1 ~ 2시간', '2 ~ 3시간', '3시간 이상'],
  },
  {
    id: 'q3', no: 3, section: 'B', type: 'multi', min: 1, max: 3,
    text: '아래 중 가장 번거로운 작업을 최대 3개까지 골라 주십시오.',
    options: TASKS,
  },
  {
    id: 'q4', no: 4, section: 'B', type: 'single',
    text: '예전에 이미 조사했던 자료를 다시 찾는 일이 얼마나 자주 생깁니까?',
    options: ['거의 매번', '자주', '가끔', '거의 없다'],
  },
  {
    id: 'q5', no: 5, section: 'B', type: 'single',
    text: '기관 관련 검색어로 자료를 찾을 때, 엉뚱한 기관 · 업체 결과 때문에 시간을 버린 적이 있습니까?',
    hint: '“KCA” · “주요사업” · “전파진흥원” 등으로 검색했을 때.',
    options: ['자주 있다', '가끔 있다', '거의 없다', '그런 방식으로 검색하지 않는다'],
  },
  {
    id: 'q6', no: 6, section: 'C', type: 'multi', min: 1,
    text: '다음 중 경험한 것을 모두 골라 주십시오.',
    options: [
      '업무망 자료교환에서 파일이 반려됨',
      '서식 지적으로 문서가 반송됨',
      '“이 숫자 출처가 뭐냐”는 질문을 받아 근거를 다시 찾음',
      '서식 작업 때문에 마감 임박 · 초과근무',
    ],
    noneOption: '해당 없음',
  },
  {
    id: 'q7', no: 7, section: 'C', type: 'single',
    text: '보고서에 쓴 수치의 근거를 다시 확인해야 할 때 보통 얼마나 걸립니까?',
    options: [
      '즉시 — 파일 · 링크가 정리돼 있다',
      '10분 이내',
      '30분 이내',
      '30분 이상',
      '끝내 찾지 못한 적이 있다',
    ],
  },
  {
    id: 'q8', no: 8, section: 'D', type: 'multi', min: 1,
    text: '보고서 작성은 주로 어디에서 하십니까?',
    options: [
      '인터넷망 VDI',
      '업무망 PC',
      '업무용 노트북(프로그램 설치 권한 있음)',
      '그 밖의 환경',
    ],
  },
  {
    id: 'q9', no: 9, section: 'E', type: 'single',
    text: '정리한 내용을 붙여넣으면 기관 양식에 맞춘 hwpx 가 자동 생성되는 도구가 있다면, 사용해 보시겠습니까?',
    hint: '설치 · 계정 · API 키 · 교육 없이 VDI 브라우저에서 그대로 쓰는 형태를 가정합니다.',
    options: ['바로 쓰겠다', '조건이 맞으면 쓰겠다', '판단 보류', '쓰지 않겠다'],
  },
  {
    id: 'q9c', sub: true, section: 'E', type: 'single',
    showIf: { q9: [2] },
    text: '어떤 조건이 맞아야 쓰시겠습니까?',
    options: [
      '보안 · 망분리 관련 승인이 되면',
      '부서 표준 도구로 정해지면',
      '결과물 품질을 직접 확인한 뒤',
      '교육 없이 바로 쓸 수 있다면',
    ],
  },
  {
    id: 'q9r', sub: true, section: 'E', type: 'single',
    showIf: { q9: [4] },
    text: '쓰지 않으시는 이유는 무엇입니까?',
    options: [
      '지금 방식으로 충분하다',
      '보안 · 망분리가 걸릴 것 같다',
      '결과물을 신뢰하기 어렵다',
      '새로 익히는 부담이 크다',
    ],
  },
  {
    id: 'q10', no: 10, section: 'E', type: 'single',
    text: '보고서 작성 과정에서 가장 없애고 싶은 것 하나만 고른다면?',
    options: [...TASKS, '여기 없는 다른 것이 더 크다'],
  },
];

export const BY_ID = Object.fromEntries(QUESTIONS.map((q) => [q.id, q]));

/**
 * 제출 payload 검증. 클라이언트와 서버가 같은 규칙을 쓴다.
 * @returns {string[]} 위반 목록. 빈 배열이면 통과.
 */
export function validate(answers) {
  const errs = [];
  for (const q of QUESTIONS) {
    const shown = !q.showIf || Object.entries(q.showIf).every(([dep, vals]) => vals.includes(answers[dep]));
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
