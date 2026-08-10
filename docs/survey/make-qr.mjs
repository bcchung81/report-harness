// 설문 QR 생성기 — 개발용. 배포에는 올라가지 않는다(.vercelignore).
//
//   npm i --no-save qrcode && node make-qr.mjs
//
// 외부 QR 생성 서비스에 URL 을 보내지 않는다. 사내 조사 링크를 제3자 로그에 남길 이유가 없다.
// 주소가 바뀌면 SURVEY_URL 만 고치고 다시 돌리면 된다.
import QRCode from 'qrcode';
import { writeFile } from 'node:fs/promises';

const SURVEY_URL = 'https://report-harness-survey.vercel.app';

// errorCorrectionLevel 'Q'(25%) — 게시판에 붙였다 떼며 생기는 훼손·구겨짐을 견디게.
// margin 2 는 QR 규격 최소 여백(4)보다 좁지만, 인쇄물에서 흰 여백이 더 붙으므로 실측상 문제 없다.
const base = { errorCorrectionLevel: 'Q', margin: 2 };
const BW = { dark: '#000000', light: '#ffffff' };

await writeFile('qr.svg', await QRCode.toString(SURVEY_URL, { ...base, type: 'svg', color: BW }));
await QRCode.toFile('qr.png', SURVEY_URL, { ...base, type: 'png', width: 1200, color: BW });

// 어두운 배경(덱 슬라이드)에 얹을 때 쓰는 흰 모듈 · 투명 바탕 판본
await writeFile(
  'qr-dark.svg',
  await QRCode.toString(SURVEY_URL, { ...base, type: 'svg', color: { dark: '#F4F6FA', light: '#0000' } })
);

console.log('생성 완료 — qr.svg · qr.png(1200px) · qr-dark.svg');
console.log('대상 URL :', SURVEY_URL);
