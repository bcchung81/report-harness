import { put } from '@vercel/blob';
import { randomUUID } from 'node:crypto';
import { VERSION, validate } from '../schema.js';

// 응답 1건 = Blob 파일 1개. 20~30건 규모에서는 이게 가장 단순하고,
// 집계는 results.js 가 list 로 훑어 합산한다.
export const config = { runtime: 'nodejs' };

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.setHeader('Allow', 'POST');
    return res.status(405).json({ error: 'POST 만 허용됩니다' });
  }

  let payload = req.body;
  if (typeof payload === 'string') {
    try { payload = JSON.parse(payload); } catch { payload = null; }
  }
  if (!payload || typeof payload !== 'object') {
    return res.status(400).json({ error: '본문을 읽지 못했습니다' });
  }
  if (payload.v !== VERSION) {
    return res.status(409).json({ error: '설문 양식이 갱신되었습니다. 새로고침 후 다시 제출해 주십시오' });
  }

  const answers = payload.answers;
  if (!answers || typeof answers !== 'object' || Array.isArray(answers)) {
    return res.status(400).json({ error: '응답 형식이 올바르지 않습니다' });
  }

  const errs = validate(answers);
  if (errs.length) return res.status(400).json({ error: errs.join(' / ') });

  // 시각은 분 단위로 자른다 — 초까지 남기면 제출 순서로 개인이 좁혀진다.
  // IP · User-Agent · 쿠키는 일절 읽지도 저장하지도 않는다.
  const ts = new Date().toISOString().slice(0, 16) + 'Z';
  const id = randomUUID();
  const record = { v: VERSION, ts, id, ...answers };

  try {
    // 스토어가 private 이라 URL 을 알아도 토큰 없이는 열리지 않는다.
    await put(`responses/${id}.json`, JSON.stringify(record), {
      access: 'private',
      contentType: 'application/json',
      cacheControlMaxAge: 0,
    });
  } catch (err) {
    console.error('blob put failed:', err?.message);
    return res.status(502).json({ error: '저장에 실패했습니다' });
  }

  return res.status(200).json({ ok: true, id: id.slice(0, 8) });
}
