(async function initStudentPage() {
  const user = await requireRole(['student']);
  if (!user) return;
  document.querySelectorAll('a[href^="#"]').forEach((link) => link.addEventListener('click', () => {
    document.querySelectorAll('.side-link').forEach((item) => item.classList.remove('active'));
    link.classList.add('active');
  }));
  const form = document.getElementById('leave-form');
  const startInput = form.elements.start_date;
  const endInput = form.elements.end_date;
  const today = new Date();
  const minDate = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
  startInput.min = minDate; endInput.min = minDate;
  startInput.addEventListener('change', () => { endInput.min = startInput.value || minDate; if (endInput.value < startInput.value) endInput.value = startInput.value; });
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); hideAlert('alert');
    const button = form.querySelector('button[type="submit"]'); setButtonLoading(button, true, 'Submitting…');
    try {
      const result = await api('/api/leaves', { method: 'POST', body: new FormData(form) });
      showAlert('alert', `${result.message} Leave ID: ${result.leave.leave_id}`, 'success');
      form.reset(); startInput.min = minDate; endInput.min = minDate;
      await loadStudentData();
      document.getElementById('history').scrollIntoView({ behavior: 'smooth', block: 'start' });
    } catch (error) { showAlert('alert', error.message); }
    finally { setButtonLoading(button, false); }
  });
  document.getElementById('refresh-leaves').addEventListener('click', loadStudentData);
  await loadStudentData();
})();

async function loadStudentData() {
  try {
    const [stats, records] = await Promise.all([api('/api/dashboard/student'), api('/api/leaves/my')]);
    document.getElementById('stat-total').textContent = stats.total_leaves;
    document.getElementById('stat-pending').textContent = stats.pending;
    document.getElementById('stat-approved').textContent = stats.approved;
    document.getElementById('stat-outside').textContent = stats.outside;
    renderStudentLeaves(records.leaves || []);
  } catch (error) { showAlert('alert', error.message); }
}

function renderStudentLeaves(leaves) {
  const box = document.getElementById('leave-list');
  if (!leaves.length) { box.innerHTML = '<div class="empty-state">No leave applications yet. Use “Apply for leave” to submit your first request.</div>'; return; }
  box.innerHTML = leaves.map((leave) => {
    const pass = ['Approved', 'Outside', 'Completed'].includes(leave.status);
    const documentLink = leave.proof_filename ? `<a class="text-link" target="_blank" rel="noopener" href="/api/leaves/${encodeURIComponent(leave.leave_id)}/proof">View proof</a>` : '';
    const qr = pass ? `<div class="pass-preview"><img alt="QR code for ${escapeHtml(leave.leave_id)}" src="/api/leaves/${encodeURIComponent(leave.leave_id)}/qr"><small>Show this at the gate</small></div>` : '';
    const extensionPending = leave.extension_request?.status === 'Pending';
    const ext = ['Approved', 'Outside'].includes(leave.status) && !extensionPending ? `<button class="btn btn-secondary btn-small" data-extend="${escapeHtml(leave.leave_id)}">Request extension</button>` : '';
    const extensionNote = extensionPending ? `<div class="extension-note">Extension requested until ${formatDate(leave.extension_request.new_end_date)} · awaiting warden review.</div>` : '';
    const rejection = leave.status === 'Rejected' ? `<div class="rejection-note">Reason: ${escapeHtml(leave.rejection_reason || 'No reason provided.')}</div>` : '';
    return `<article class="leave-item"><div><div class="leave-id">${escapeHtml(leave.leave_id)}</div><h3>${escapeHtml(leave.reason)} leave</h3><div class="leave-meta"><span>↗ ${formatDate(leave.start_date)} – ${formatDate(leave.end_date)}</span><span>⏱ Return ${escapeHtml(leave.return_time || '—')}</span><span>Applied ${formatDateTime(leave.created_at)}</span></div>${leave.notes ? `<p class="leave-notes">${escapeHtml(leave.notes)}</p>` : ''}${rejection}${extensionNote}<div class="record-links">${documentLink} ${ext}</div>${qr}</div><div class="leave-item-right">${statusBadge(leave.status)}</div></article>`;
  }).join('');
  box.querySelectorAll('[data-extend]').forEach((button) => button.addEventListener('click', async () => {
    const newEnd = window.prompt('Enter the new return date (YYYY-MM-DD):');
    if (!newEnd) return;
    const reason = window.prompt('Why do you need an extension?') || '';
    try {
      const result = await api(`/api/leaves/${encodeURIComponent(button.dataset.extend)}/extension`, { method: 'POST', body: { new_end_date: newEnd, reason } });
      showAlert('alert', result.message, 'success'); await loadStudentData();
    } catch (error) { showAlert('alert', error.message); }
  }));
}
