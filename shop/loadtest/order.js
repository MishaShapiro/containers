import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://api.shop.svc.cluster.local:8080';

export const options = {
  scenarios: {
    orders: {
      executor: 'constant-arrival-rate',   // фиксированный RPS: задержка не влияет на нагрузку
      rate: Number(__ENV.RATE || 30),
      timeUnit: '1s',
      duration: __ENV.DURATION || '10m',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<300'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const r = http.post(`${BASE}/order`, JSON.stringify({ item: 'book', qty: 1 }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'order' } });
  check(r, { 'created': (x) => x.status === 201 });
}
