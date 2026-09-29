export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

// The backend's standardize_responses_middleware wraps every successful JSON response
// as { success, data, message }. Call this instead of response.json() directly so call
// sites get the actual payload; falls back to the raw JSON for anything unwrapped
// (e.g. /health, /api/mock-predict, which the middleware explicitly skips).
export async function unwrapApiResponse<T = any>(response: Response): Promise<T> {
  const json = await response.json();
  if (json && typeof json === 'object' && 'success' in json && 'data' in json) {
    return json.data as T;
  }
  return json as T;
}
