import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://api.shop.svc.cluster.local:8080';   // по DNS-имени Service

export const options = {
  noConnectionReuse: true,      // новое TCP-соединение на каждый запрос → каждый раз заново выбирается backend
  scenarios: {
    steady: { executor: 'constant-arrival-rate', rate: 20, timeUnit: '1s',
              duration: __ENV.DURATION || '10m', preAllocatedVUs: 20, maxVUs: 100 },
  },
  thresholds: { http_req_failed: ['rate==0'] },
};

export default function () {
  const r = http.get(`${BASE}/orders`, { timeout: '5s' });
  check(r, { '200': (x) => x.status === 200 });
}
