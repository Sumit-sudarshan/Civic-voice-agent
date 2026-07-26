// Set VITE_API_BASE_URL at build time. Empty string ("") means same-origin —
// the production build's intent, since Nginx serves the frontend and proxies
// the API from the same host. Unset (undefined) falls back to the local dev
// backend. Must be `??`, not `||` — "" is a deliberate, valid value here and
// `||` would incorrectly discard it in favor of the fallback.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

/**
 * FR9 concerned-person dropdown: leaders whose jurisdiction matches the
 * given city/pincode.
 */
export async function fetchLeaders({ city = '', pincode = '' } = {}) {
  const params = new URLSearchParams();
  if (city) params.set('city', city);
  if (pincode) params.set('pincode', pincode);
  const res = await fetch(`${API_BASE}/leaders?${params}`);
  if (!res.ok) throw new Error('Failed to fetch leaders');
  return res.json();
}

export async function fetchCategories() {
  const res = await fetch(`${API_BASE}/settings/categories`);
  if (!res.ok) throw new Error('Failed to fetch categories');
  return res.json();
}

export async function fetchStatsSummary() {
  const res = await fetch(`${API_BASE}/stats/summary`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

/**
 * Fetch ALL valid, non-duplicate issues (no top-N cap), sorted by most recent first.
 * @param {Object} params - { submissionType: 'complaint' | 'suggestion', archived, timeRange }
 */
export async function fetchIssues({ submissionType = 'complaint', archived = false, timeRange = '' } = {}) {
  const params = new URLSearchParams({ submission_type: submissionType });
  if (archived) params.set('archived', 'true');
  if (timeRange) params.set('time_range', timeRange);
  const res = await fetch(`${API_BASE}/stats/issues?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch issues');
  return res.json();
}

/**
 * Fetch the AI executive-briefing narrative for a time range.
 * @param {Object} params - { timeRange, submissionType: 'complaint' | 'suggestion', refresh }
 */
export async function fetchSummaryReport({ timeRange = '7d', submissionType = 'complaint', refresh = false } = {}) {
  const params = new URLSearchParams({ time_range: timeRange, submission_type: submissionType });
  if (refresh) params.set('refresh', 'true');
  const res = await fetch(`${API_BASE}/stats/summary-report?${params}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch summary report');
  return res.json();
}

export async function fetchTrends(timeRange = 'all') {
  const res = await fetch(`${API_BASE}/stats/trends?time_range=${encodeURIComponent(timeRange)}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch trends');
  return res.json();
}

/**
 * Fetch complaints with optional filter params.
 * @param {Object} params - { q, category, urgency, status, area, timeRange }
 */
export async function fetchComplaints(params = {}) {
  const p = new URLSearchParams();
  if (params.q)         p.set('q', params.q);
  if (params.category)  p.set('category', params.category);
  if (params.urgency)   p.set('urgency', params.urgency);
  if (params.status)    p.set('status', params.status);
  if (params.area)      p.set('area', params.area);
  if (params.timeRange) p.set('time_range', params.timeRange);
  const qs = p.toString();
  const res = await fetch(`${API_BASE}/complaints${qs ? '?' + qs : ''}`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch complaints');
  return res.json();
}

export async function fetchSuggestions() {
  const res = await fetch(`${API_BASE}/suggestions`, { credentials: 'include' });
  if (!res.ok) throw new Error('Failed to fetch suggestions');
  return res.json();
}

export async function updateComplaintStatus(id, status) {
  const res = await fetch(`${API_BASE}/complaints/${id}/status?status=${status}`, {
    method: 'PATCH',
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to update status');
  return res.json();
}

/**
 * FR12: unmask a citizen's phone number for one complaint — logged
 * server-side (who/when) on every call.
 */
export async function revealPhone(id) {
  const res = await fetch(`${API_BASE}/complaints/${id}/reveal-phone`, {
    method: 'POST',
    credentials: 'include',
  });
  if (!res.ok) throw new Error('Failed to reveal phone number');
  return res.json();
}

export async function fetchSubmissionStatus(type, id) {
  const endpoint = type === 'complaint' ? 'complaints' : 'suggestions';
  const res = await fetch(`${API_BASE}/${endpoint}/${id}`);
  if (res.status === 404) {
    const err = new Error('Submission not found');
    err.notFound = true;
    throw err;
  }
  if (!res.ok) throw new Error('Failed to fetch submission status');
  return res.json();
}

/**
 * Citizen's post-submission verdict on the AI's extraction (eval Layer 2).
 * @param {string} id - complaint id
 * @param {Object} body - { is_correct: boolean, correction?: string }
 */
export async function sendExtractionFeedback(id, body) {
  const res = await fetch(`${API_BASE}/complaints/${id}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error('Failed to submit feedback');
  return res.json();
}

export async function fetchEvalReport() {
  const res = await fetch(`${API_BASE}/eval/report`);
  if (!res.ok) throw new Error('Failed to fetch eval report');
  return res.json();
}

export async function runLiveEval() {
  const res = await fetch(`${API_BASE}/eval/live`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to run live eval');
  return res.json();
}

export async function fetchEvalTrends(limit = 20) {
  const res = await fetch(`${API_BASE}/eval/trends?limit=${limit}`);
  if (!res.ok) throw new Error('Failed to fetch eval trends');
  return res.json();
}

/**
 * Send one turn of the conversational intake flow (FR15 — consumed as
 * Server-Sent Events so the reply can be shown token-by-token). Not
 * EventSource (no POST-body/credentials support there) — plain fetch +
 * manual SSE frame parsing over the readable stream instead.
 * @param {Object} payload - { new_message, history, submission_type_hint,
 *   citizen_first_name, citizen_last_name, citizen_phone, concerned_leader_id }
 * @param {(text: string) => void} onChunk - called once per streamed text fragment.
 * @returns {Promise<Object>} the final ChatTurnResponse for this turn.
 */
export async function sendChatMessageStream(payload, onChunk) {
  const res = await fetch(`${API_BASE}/intake/message/stream`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalData = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    // SSE frames are separated by a blank line.
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let event = 'message';
      let data = '';
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7);
        else if (line.startsWith('data: ')) data = line.slice(6);
      }
      if (!data) continue;

      const parsed = JSON.parse(data);
      if (event === 'chunk') onChunk(parsed.text);
      else if (event === 'final') finalData = parsed;
    }
  }

  if (!finalData) throw new Error('Stream ended without a final response');
  return finalData;
}
