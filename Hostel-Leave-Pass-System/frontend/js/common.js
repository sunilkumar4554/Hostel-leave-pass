const API_BASE = '';

async function api(path, options = {}) {
  const config = { credentials: 'same-origin', ...options };
  if (config.body && !(config.body instanceof FormData) && typeof config.body !== 'string') {
    config.headers = { ...(config.headers || {}), 'Content-Type': 'application/json' };
    config.body = JSON.stringify(config.body);
  }
  const response = await fetch(`${API_BASE}${path}`, config);
  const contentType = response.headers.get('content-type') || '';
  let body;
  if (contentType.includes('application/json')) body = await response.json();
  else body = await response.blob();
  if (!response.ok) {
    const message = body && body.error ? body.error : `Request failed (${response.status}).`;
    const error = new Error(message);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
}

function showAlert(elementId, message, type = 'error') {
  const element = typeof elementId === 'string' ? document.getElementById(elementId) : elementId;
  if (!element) return;
  element.textContent = message;
  element.className = `alert ${type === 'success' ? 'success' : type === 'info' ? 'info' : ''}`;
  element.classList.remove('hidden');
  if (type === 'success') window.setTimeout(() => element.classList.add('hidden'), 5000);
}

function hideAlert(elementId) {
  const element = document.getElementById(elementId);
  if (element) element.classList.add('hidden');
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { day: '2-digit', month: 'short', year: 'numeric' }).format(date);
}

function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(date);
}

function statusClass(status) {
  return `status-${String(status || 'unknown').toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

function statusBadge(status) {
  return `<span class="status-badge ${statusClass(status)}">${escapeHtml(status || 'Unknown')}</span>`;
}

function destinationForRole(role) {
  return ({ student: '/student-dashboard.html', warden: '/warden-dashboard.html', guard: '/guard-dashboard.html' })[role] || '/';
}

async function requireRole(roles) {
  try {
    const result = await api('/api/me');
    if (!roles.includes(result.user.role)) {
      window.location.href = destinationForRole(result.user.role);
      return null;
    }
    updateUserChrome(result.user);
    return result.user;
  } catch (error) {
    window.location.href = '/';
    return null;
  }
}

function updateUserChrome(user) {
  const name = user?.name || 'User';
  const sideName = document.getElementById('side-name');
  const avatar = document.getElementById('user-avatar');
  const greeting = document.getElementById('greeting-name');
  const today = document.getElementById('today-label');
  if (sideName) sideName.textContent = name;
  if (avatar) avatar.textContent = name.trim().charAt(0).toUpperCase() || 'U';
  if (greeting) greeting.textContent = name.split(' ')[0];
  if (today) today.textContent = new Intl.DateTimeFormat(undefined, { weekday: 'short', day: '2-digit', month: 'short' }).format(new Date());
  const logout = document.getElementById('logout-button');
  if (logout) logout.addEventListener('click', async () => {
    try { await api('/api/logout', { method: 'POST' }); } catch (_) {}
    window.location.href = '/';
  }, { once: true });
}

function setButtonLoading(button, loading, label = 'Please wait…') {
  if (!button) return;
  if (loading) {
    button.dataset.originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> ${label}`;
  } else {
    button.disabled = false;
    if (button.dataset.originalText) button.innerHTML = button.dataset.originalText;
  }
}

window.HostelPass = { api, escapeHtml, showAlert, hideAlert, formatDate, formatDateTime, statusBadge, statusClass, requireRole, updateUserChrome, setButtonLoading };
