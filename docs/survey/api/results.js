import { list, get } from '@vercel/blob';
import { timingSafeEqual } from 'node:crypto';
import { VERSION, QUESTIONS, SECTIONS } from '../schema.js';

// 집계 조회. ADMIN_KEY 없이는 아무것도 내주지 않는다 —
// 소표본이라 개별 응답이 새면 답변 조합으로 사람이 특정된다.
export const config = { runtime: 'nodejs' };

function keyOk(given) {
  const want = process.env.ADMIN_KEY;
  if (!want || !given) return false;
  const a = Buffer.from(String(given));
  const b = Buffer.from(want);
  return a.length === b.length && timingSafeEqual(a, b);
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ error: 'GET 만 허용됩니다' });
  }
  if (!process.env.ADMIN_KEY) {
    return res.status(503).json({ error: 'ADMIN_KEY 가 설정되지 않아 조회를 막았습니다' });
  }

  const url = new URL(req.url, 'http://localhost');
  if (!keyOk(url.searchParams.get('key') || req.headers['x-admin-key'])) {
    return res.status(401).json({ error: '인증 실패' });
  }

  // 응답 수집
  const records = [];
  let cursor;
  do {
    const page = await list({ prefix: 'responses/', cursor, limit: 1000 });
    // private 스토어라 URL 직접 fetch 는 통하지 않는다 — SDK 의 get 으로 읽는다.
    const fetched = await Promise.all(
      page.blobs.map((b) =>
        get(b.pathname, { access: 'private', useCache: false })
          .then((r) => (r?.stream ? new Response(r.stream).json() : null))
          .catch(() => null)
      )
    );
    records.push(...fetched.filter(Boolean));
    cursor = page.hasMore ? page.cursor : undefined;
  } while (cursor);

  const current = records.filter((r) => r.v === VERSION);

  // 문항별 도수
  const tally = {};
  for (const q of QUESTIONS) {
    const labels = [...q.options, ...(q.noneOption ? [q.noneOption] : [])];
    const counts = new Array(labels.length).fill(0);
    let shown = 0;
    for (const r of current) {
      const v = r[q.id];
      if (v === undefined) continue;
      shown++;
      for (const n of Array.isArray(v) ? v : [v]) if (n >= 1 && n <= counts.length) counts[n - 1]++;
    }
    tally[q.id] = {
      section: SECTIONS[q.section].label,
      no: q.no ?? null,
      text: q.text,
      type: q.type,
      shown, // 이 문항이 표시된 응답 수 (하위 문항은 전체보다 작다)
      options: labels.map((label, i) => ({
        n: i + 1,
        label,
        count: counts[i],
        pct: shown ? Math.round((counts[i] / shown) * 1000) / 10 : 0,
      })),
    };
  }

  // Q1(건수) × Q2(서식시간) 로 월 서식시간을 어림한다. 구간 중앙값 기준의 추정치다.
  const CASES = [0, 1.5, 4, 8, 13]; // 3개월 건수
  const HOURS = [0.25, 0.75, 1.5, 2.5, 3.5]; // 건당 시간
  let personMonthly = 0;
  let pairs = 0;
  for (const r of current) {
    if (!r.q1 || !r.q2) continue;
    personMonthly += (CASES[r.q1 - 1] / 3) * HOURS[r.q2 - 1];
    pairs++;
  }

  return res.status(200).json({
    generatedAt: new Date().toISOString(),
    version: VERSION,
    n: current.length,
    discardedOtherVersion: records.length - current.length,
    tally,
    derived: {
      note: '구간 중앙값으로 계산한 어림값. 보고서에 쓸 때는 반드시 추정치임을 밝힐 것.',
      respondentsUsed: pairs,
      formattingHoursPerMonth_total: Math.round(personMonthly * 10) / 10,
      formattingHoursPerMonth_avgPerPerson: pairs ? Math.round((personMonthly / pairs) * 10) / 10 : 0,
    },
    ...(url.searchParams.get('raw') === '1' ? { raw: current } : {}),
  });
}
