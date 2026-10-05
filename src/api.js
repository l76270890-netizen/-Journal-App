const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

async function request(path, { token, method = 'GET', body, form } = {}) {
  const headers = {};
  if (form !== undefined) {
    headers['Content-Type'] = 'application/x-www-form-urlencoded;charset=UTF-8';
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: form ? new URLSearchParams(form) : body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 204) return null;

  const raw = await response.text();
  let result = null;
  if (raw) {
    try {
      result = JSON.parse(raw);
    } catch {
      result = raw;
    }
  }

  if (!response.ok) {
    const detail = result?.detail ?? result;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join(', ')
      : typeof detail === 'string'
        ? detail
        : 'The server could not complete the request.';
    throw new Error(message);
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

export function getAppLock(token) {
  return request('/users/me/app-lock', { token });
}

export function setAppLock(token, lockType, secret) {
  return request('/users/me/app-lock', {
    token,
    method: 'PUT',
    body: { lock_type: lockType, secret },
  });
}

export async function verifyAppLock(token, lockType, secret) {
  const result = await request('/users/me/app-lock/verify', {
    token,
    method: 'POST',
    body: { lock_type: lockType, secret },
  });
  return result.verified;
}

export function deleteAppLock(token) {
  return request('/users/me/app-lock', { token, method: 'DELETE' });
}
