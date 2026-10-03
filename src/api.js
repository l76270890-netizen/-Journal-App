const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

async function request(path, { token, method = 'GET', body, form } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: form ? new URLSearchParams(form) : body === undefined ? undefined : JSON.stringify(body),
  });
  const result = response.status === 204 ? null : await response.json();

  if (!response.ok) {
    const detail = result?.detail;
    throw new Error(Array.isArray(detail) ? detail.map((item) => item.msg).join(', ') : detail || 'The server could not complete the request.');
  }

  return result;
}

export async function authenticate({ name, email, password, mode }) {
  const normalizedEmail = email.trim().toLowerCase();
  if (mode === 'signup') {
    await request('/register', {
      method: 'POST',
      body: { name: name.trim(), email: normalizedEmail, password },
    });
  }

  const session = await request('/login', {
    method: 'POST',
    form: { username: normalizedEmail, password },
  });

  return {
    name: session.name,
    email: session.email,
    token: session.access_token,
  };
}

export function getNotes(token) {
  return request('/notes', { token });
}

export function createNote(token, note) {
  return request('/notes', { token, method: 'POST', body: note });
}

export function updateNote(token, id, note) {
  return request(`/notes/${id}`, { token, method: 'PUT', body: note });
}

export function deleteNote(token, id) {
  return request(`/notes/${id}`, { token, method: 'DELETE' });
}

export function updateProfile(token, name) {
  return request('/users/me', { token, method: 'PUT', body: { name } });
}
