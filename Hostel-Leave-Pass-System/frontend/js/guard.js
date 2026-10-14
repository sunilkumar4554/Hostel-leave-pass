let lastValidation = null;
let html5Scanner = null;
(async function initGuardPage() {
  const user = await requireRole(['guard']);
  if (!user) return;
  document.getElementById('validate-form').addEventListener('submit', async (event) => {
    event.preventDefault(); await validatePass(document.getElementById('leave-id-input').value);
  });
  document.getElementById('refresh-outside').addEventListener('click', loadOutside);
  document.getElementById('start-scan').addEventListener('click', startScanner);
  await loadOutside();
  await loadActivity();
})();

async function validatePass(leaveId) {
  hideAlert('alert');
  const box = document.getElementById('validation-result');
  const content = document.getElementById('validation-content');
  box.classList.remove('hidden'); content.innerHTML = '<div class="empty-state">Validating pass…</div>';
  try {
    const result = await api('/api/guard/validate', { method: 'POST', body: { leave_id: leaveId } });
    lastValidation = result;
    const leave = result.leave;
    content.innerHTML = `<div class="result-banner"><div class="result-symbol">✓</div><div><h3>Valid pass</h3><p>${escapeHtml(result.message)}</p></div>${statusBadge(leave.status)}</div><div class="result-details"><div><span>Student</span><strong>${escapeHtml(leave.student_name)}</strong></div><div><span>Registration number</span><strong>${escapeHtml(leave.registration_no)}</strong></div><div><span>Room / Hostel</span><strong>${escapeHtml(leave.room_no)} · ${escapeHtml(leave.hostel_name)}</strong></div><div><span>Leave ID</span><strong>${escapeHtml(leave.leave_id)}</strong></div><div><span>Approved dates</span><strong>${formatDate(leave.start_date)} – ${formatDate(leave.end_date)}</strong></div><div><span>Expected return</span><strong>${formatDate(leave.end_date)} · ${escapeHtml(leave.return_time || '—')}</strong></div></div><div class="result-actions">${result.action === 'Check-Out' ? `<button class="btn btn-primary" id="confirm-checkout">Confirm Check-Out ↗</button>` : `<button class="btn btn-primary" id="confirm-checkin">Confirm Check-In ✓</button>`}<button class="btn btn-secondary" id="clear-validation">Clear</button></div>`;
    if (result.action === 'Check-Out') document.getElementById('confirm-checkout').addEventListener('click', () => commitGateAction('checkout', leave.leave_id));
    if (result.action === 'Check-In') document.getElementById('confirm-checkin').addEventListener('click', () => commitGateAction('checkin', leave.leave_id));
    document.getElementById('clear-validation').addEventListener('click', () => { box.classList.add('hidden'); document.getElementById('leave-id-input').value = ''; document.getElementById('leave-id-input').focus(); });
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) {
    lastValidation = null;
    content.innerHTML = `<div class="danger-message"><strong>Pass verification failed</strong><br>${escapeHtml(error.message)}</div><div class="result-actions" style="margin-top:14px"><button class="btn btn-secondary" id="clear-invalid">Clear</button></div>`;
    document.getElementById('clear-invalid').addEventListener('click', () => { box.classList.add('hidden'); document.getElementById('leave-id-input').value = ''; });
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}

async function commitGateAction(action, leaveId) {
  if (!window.confirm(`Confirm ${action === 'checkout' ? 'student check-out from the hostel' : 'student return / check-in'} for ${leaveId}?`)) return;
  try {
    const result = await api(`/api/guard/${action}`, { method: 'POST', body: { leave_id: leaveId } });
    showAlert('alert', result.message, 'success');
    document.getElementById('validation-result').classList.add('hidden');
    document.getElementById('leave-id-input').value = '';
    await Promise.all([loadOutside(), loadActivity()]);
  } catch (error) { showAlert('alert', error.message); }
}

async function startScanner() {
  const button = document.getElementById('start-scan');
  if (html5Scanner) {
    try { await html5Scanner.stop(); await html5Scanner.clear(); } catch (_) {}
    html5Scanner = null; button.textContent = 'Start camera scanner';
    document.getElementById('reader').innerHTML = '<div class="scanner-placeholder"><span class="scanner-symbol">⌗</span><strong>QR scanner</strong><small>Start the camera to scan a student\'s pass.</small></div>';
    return;
  }
  if (typeof Html5Qrcode === 'undefined') {
    showAlert('alert', 'The QR scanner library could not load. Use manual Leave ID entry or connect to the internet and refresh.'); return;
  }
  button.disabled = true; button.textContent = 'Opening camera…';
  try {
    document.getElementById('reader').innerHTML = '';
    html5Scanner = new Html5Qrcode('reader');
    await html5Scanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 220, height: 220 } }, async (decodedText) => {
      const leaveId = String(decodedText).trim().toUpperCase();
      document.getElementById('leave-id-input').value = leaveId;
      try { await html5Scanner.stop(); await html5Scanner.clear(); } catch (_) {}
      html5Scanner = null; button.disabled = false; button.textContent = 'Start camera scanner';
      await validatePass(leaveId);
    }, () => {});
    button.disabled = false; button.textContent = 'Stop camera scanner';
  } catch (error) {
    html5Scanner = null; button.disabled = false; button.textContent = 'Start camera scanner';
    document.getElementById('reader').innerHTML = '<div class="scanner-placeholder"><span class="scanner-symbol">⌗</span><strong>Camera not available</strong><small>Check browser camera permission, or enter the Leave ID manually.</small></div>';
    showAlert('alert', `Could not start the camera: ${error.message || error}`);
  }
}

async function loadOutside() {
  const box = document.getElementById('outside-list');
  try {
    const result = await api('/api/guard/outside');
    const leaves = result.leaves || [];
    box.innerHTML = leaves.length ? `<table class="data-table"><thead><tr><th>Student</th><th>Leave ID</th><th>Expected return</th><th>Checked out</th></tr></thead><tbody>${leaves.map((leave) => `<tr><td><span class="table-primary">${escapeHtml(leave.student_name)}</span><span class="table-sub">${escapeHtml(leave.registration_no)} · Room ${escapeHtml(leave.room_no)}</span></td><td>${escapeHtml(leave.leave_id)}</td><td><span class="table-primary">${formatDate(leave.end_date)}</span><span class="table-sub">${escapeHtml(leave.return_time || '—')}</span></td><td>${formatDateTime(leave.checked_out_at)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty-state">No students are currently marked outside.</div>';
  } catch (error) { box.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`; }
}

async function loadActivity() {
  const box = document.getElementById('gate-log-list');
  try {
    const result = await api('/api/guard/activity');
    const events = result.events || [];
    box.innerHTML = events.length ? `<table class="data-table"><thead><tr><th>Event</th><th>Student</th><th>Leave ID</th><th>Time</th></tr></thead><tbody>${events.map((item) => `<tr><td>${item.event === 'check_out' ? '<span class="status-badge status-outside">↗ Check-Out</span>' : '<span class="status-badge status-completed">✓ Check-In</span>'}</td><td><span class="table-primary">${escapeHtml(item.student_name)}</span><span class="table-sub">${escapeHtml(item.registration_no)} · Room ${escapeHtml(item.room_no)}</span></td><td>${escapeHtml(item.leave_id)}</td><td>${formatDateTime(item.created_at)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty-state">No gate events recorded yet.</div>';
  } catch (error) { box.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`; }
}
