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

export interface ExportedFile {
  blob: Blob;
  filename: string | null;
}

// Document export runs as a background job on the server: queue it, poll until it has
// finished, then download the file. This keeps the request itself short and lets the
// server retry a failed generation without the browser holding a connection open.
export async function exportDocument(
  projectId: number,
  format: string,
  token: string,
  { pollIntervalMs = 1500, timeoutMs = 5 * 60 * 1000 }: { pollIntervalMs?: number; timeoutMs?: number } = {},
): Promise<ExportedFile> {
  const headers = { Authorization: `Bearer ${token}` };

  const queued = await fetch(
    `${API_BASE_URL}/api/projects/${projectId}/export-jobs?format=${encodeURIComponent(format)}`,
    { method: 'POST', headers },
  );
  if (!queued.ok) {
    throw new Error('Export request failed');
  }
  const { job_id: jobId } = await unwrapApiResponse<{ job_id: string }>(queued);

  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const res = await fetch(`${API_BASE_URL}/api/jobs/${jobId}`, { headers });
    if (!res.ok) {
      throw new Error('Could not read export status');
    }
    const job = await unwrapApiResponse<{ status: string; error?: string | null }>(res);
    if (job.status === 'completed') {
      break;
    }
    if (job.status === 'failed') {
      throw new Error(job.error || 'Export failed');
    }
    if (Date.now() > deadline) {
      throw new Error('Export timed out');
    }
    await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
  }

  const file = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/download`, { headers });
  if (!file.ok) {
    throw new Error('Could not download the exported file');
  }
  const match = /filename="?([^";]+)"?/i.exec(file.headers.get('Content-Disposition') || '');
  return { blob: await file.blob(), filename: match ? match[1] : null };
}
