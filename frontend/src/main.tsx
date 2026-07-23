import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

// Intercept all fetch requests to transparently unwrap standardized successful API responses
const originalFetch = window.fetch;
window.fetch = async function(...args) {
  const response = await originalFetch(...args);
  const clone = response.clone();
  try {
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      const json = await clone.json();
      if (json && typeof json === "object" && "success" in json) {
        if (json.success && "data" in json) {
          return new Response(JSON.stringify(json.data), {
            status: response.status,
            statusText: response.statusText,
            headers: response.headers
          });
        } else if (!json.success) {
          return new Response(JSON.stringify({ detail: json.message || "An error occurred." }), {
            status: response.status >= 400 ? response.status : 400,
            statusText: response.statusText,
            headers: response.headers
          });
        }
      }
    }
  } catch (e) {
    // Pass through parsing failures (such as text/event-stream chunks) unchanged
  }
  return response;
};

createRoot(document.getElementById('root') as HTMLElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
