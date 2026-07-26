const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

async function authFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: 'include', // session lives in an httpOnly cookie, never localStorage
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  if (!res.ok) {
    let detail = 'Request failed';
    try {
      const body = (await res.json()).detail;
      // FastAPI/pydantic validation errors (422) come back as a list of
      // {msg, loc, ...} objects, not a plain string like our own
      // HTTPException(detail=...) calls — surface the first one's message.
      detail = Array.isArray(body) ? (body[0]?.msg || detail) : (body || detail);
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.json();
}

export function citizenSignup({ firstName, lastName, phone, email, password }) {
  return authFetch('/auth/citizen/signup', {
    method: 'POST',
    body: JSON.stringify({ first_name: firstName, last_name: lastName || null, phone, email, password }),
  });
}

export function leaderSignup({ name, phone, email, password, city, pincode }) {
  return authFetch('/auth/leader/signup', {
    method: 'POST',
    body: JSON.stringify({ name, phone, email, password, city, pincode }),
  });
}

export function login({ email, password }) {
  return authFetch('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
}

export function logout() {
  return authFetch('/auth/logout', { method: 'POST' });
}

export function getMe() {
  return authFetch('/auth/me');
}
