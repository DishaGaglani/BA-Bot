import { API_BASE_URL } from './config';

// Trace correlation with the backend.
//
// Every request to the API carries a W3C `traceparent` header. The backend adopts that
// trace id for its logs, error bodies, Sentry events and OpenTelemetry spans, and echoes
// it back as `X-Trace-Id`, so one id joins this browser request to everything the server
// did for it. Failed requests are logged here with that id: quote it when reporting a bug.

const hex = (bytes: number): string => {
  const buf = new Uint8Array(bytes);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('');
};

export const newTraceparent = (): string => `00-${hex(16)}-${hex(8)}-01`;

// API_BASE_URL is '' in the Docker build (same-origin), and ''.startsWith-style checks would
// match every URL, so only add the header to same-origin paths or the configured API origin.
const isApiCall = (url: string): boolean =>
  (API_BASE_URL !== '' && url.startsWith(API_BASE_URL)) || (url.startsWith('/') && !url.startsWith('//'));

// Returns [input, init] with a traceparent header added (an existing one is kept).
export function withTraceHeaders(input: RequestInfo | URL, init?: RequestInit): [RequestInfo | URL, RequestInit | undefined] {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  if (!isApiCall(url)) {
    return [input, init];
  }
  const headers = new Headers(init?.headers ?? (typeof input !== 'string' && !(input instanceof URL) ? input.headers : undefined));
  if (!headers.has('traceparent')) {
    headers.set('traceparent', newTraceparent());
  }
  return [input, { ...init, headers }];
}

export function reportFailedRequest(input: RequestInfo | URL, response: Response): void {
  if (response.status < 500) {
    return;
  }
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  console.error(`[api] ${response.status} ${url} traceId=${response.headers.get('X-Trace-Id') ?? 'unknown'}`);
}
