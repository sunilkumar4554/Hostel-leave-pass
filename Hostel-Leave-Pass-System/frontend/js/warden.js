let wardenLeavesCache = [];
(async function initWardenPage() {
  const user = await requireRole(['warden']);
  if (!user) return;
  await loadWardenDashboard();
  await loadWardenLeaves();
  document.getElementById('status-filter').addEventListener('change', loadWardenLeaves);
  document.getElementById('refresh-approvals').addEventListener('click', loadWardenLeaves);
  document.getElementById('jump-pending').addEventListener('click', () => {
    document.getElementById('status-filter').value = 'Pending';
    document.getElementById('approvals').scrollIntoView({ behavior: 'smooth' });
    loadWardenLeaves();
  });
  document.getElementById('student-search-form').addEventListener('submit', async (event) => {
    event.preventDefault(); await searchStudents();
  });
  const now = new Date();
  document.getElementById('report-month').value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  document.getElementById('report-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const month = document.getElementById('report-month').value;
    window.location.href = `/api/warden/reports/monthly.xlsx?month=${encodeURIComponent(month)}`;
  });
  document.getElementById('import-form').addEventListener('submit', async (event) => {
    event.preventDefault(); hideAlert('alert');
    const file = document.getElementById('student-csv').files[0];
    if (!file) return showAlert('alert', 'Select a CSV file first.');
    const data = new FormData(); data.append('file', file); data.append('temporary_password', document.getElementById('import-password').value);
    const button = event.currentTarget.querySelector('button[type="submit"]'); setButtonLoading(button, true, 'Importing…');
    try {
      const result = await api('/api/warden/students/import', { method: 'POST', body: data });
      showAlert('alert', `${result.message} Added: ${result.added}; skipped: ${result.skipped}.`, 'success');
      event.currentTarget.reset(); await searchStudents(); await loadWardenDashboard();
    } catch (error) { showAlert('alert', error.message); }
    finally { setButtonLoading(button, false); }
  });
})();

async function loadWardenDashboard() {
  try {
    const stats = await api('/api/warden/dashboard');
    document.getElementById('stat-students').textContent = stats.total_students;
    document.getElementById('stat-pending').textContent = stats.pending;
    document.getElementById('stat-approved').textContent = stats.approved;
    document.getElementById('stat-outside').textContent = stats.outside;
  } catch (error) { showAlert('alert', error.message); }
}

async function loadWardenLeaves() {
  const box = document.getElementById('approval-list');
  box.innerHTML = '<div class="empty-state">Loading applications…</div>';
  const status = document.getElementById('status-filter').value;
  try {
    const result = await api(`/api/warden/leaves?status=${encodeURIComponent(status)}`);
    wardenLeavesCache = result.leaves || [];
    if (!wardenLeavesCache.length) { box.innerHTML = '<div class="empty-state">No applications found for this filter.</div>'; return; }
    box.innerHTML = `<table class="data-table"><thead><tr><th>Student</th><th>Leave details</th><th>Dates</th><th>Status</th><th>Action</th></tr></thead><tbody>${wardenLeavesCache.map((leave) => {
      const reviewStatus = leave.review_status || leave.status;
      const canReview = ['Pending', 'Extension Pending'].includes(reviewStatus);
      const action = canReview ? `<div class="row-actions"><button class="approve-btn" title="Approve" data-decision="approve" data-id="${escapeHtml(leave.leave_id)}">✓</button><button class="reject-btn" title="Reject" data-decision="reject" data-id="${escapeHtml(leave.leave_id)}">×</button></div>` : (['Approved','Outside','Completed'].includes(leave.status) ? `<a class="text-link" target="_blank" rel="noopener" href="/api/leaves/${encodeURIComponent(leave.leave_id)}/qr">View QR</a>` : '—');
      const extText = leave.review_status === 'Extension Pending' && leave.extension_request ? `<span class="table-sub">Extension to ${formatDate(leave.extension_request.new_end_date)}</span>` : '';
      return `<tr><td><span class="table-primary">${escapeHtml(leave.student_name)}</span><span class="table-sub">${escapeHtml(leave.registration_no)} · Room ${escapeHtml(leave.room_no)}</span><span class="table-sub">${escapeHtml(leave.branch || '')}</span></td><td><span class="table-primary">${escapeHtml(leave.reason)} leave</span><span class="table-sub">${escapeHtml(leave.leave_id)}</span>${leave.proof_filename ? `<a class="table-sub text-link" target="_blank" rel="noopener" href="/api/leaves/${encodeURIComponent(leave.leave_id)}/proof">View supporting document</a>` : ''}${extText}</td><td><span class="table-primary">${formatDate(leave.start_date)}</span><span class="table-sub">to ${formatDate(leave.end_date)}</span><span class="table-sub">Return ${escapeHtml(leave.return_time || '—')}</span></td><td>${statusBadge(reviewStatus)}</td><td>${action}</td></tr>`;
    }).join('')}</tbody></table>`;
    box.querySelectorAll('[data-decision]').forEach((button) => button.addEventListener('click', async () => {
      const leave = wardenLeavesCache.find((item) => item.leave_id === button.dataset.id);
      const decision = button.dataset.decision;
      let rejection_reason = '';
      if (decision === 'reject') {
        rejection_reason = window.prompt(`Why are you rejecting ${leave?.student_name || 'this'}'s leave request?`) || '';
        if (!window.confirm('Confirm rejection of this leave request?')) return;
      } else if (!window.confirm(`Approve leave request ${button.dataset.id}?`)) return;
      button.disabled = true;
      try {
        const result = await api(`/api/warden/leaves/${encodeURIComponent(button.dataset.id)}/decision`, { method: 'POST', body: { decision, rejection_reason } });
        showAlert('alert', result.message, 'success');
        await Promise.all([loadWardenLeaves(), loadWardenDashboard()]);
      } catch (error) { showAlert('alert', error.message); button.disabled = false; }
    }));
  } catch (error) { box.innerHTML = ''; showAlert('alert', error.message); }
}

async function searchStudents() {
  const query = document.getElementById('student-query').value.trim();
  const box = document.getElementById('student-results');
  box.innerHTML = '<div class="empty-state">Searching…</div>';
  try {
    const result = await api(`/api/warden/students?q=${encodeURIComponent(query)}`);
    if (!result.students.length) { box.innerHTML = '<div class="empty-state">No students found for this search.</div>'; return; }
    box.innerHTML = `<table class="data-table"><thead><tr><th>Student</th><th>Registration / Branch</th><th>Hostel / Room</th><th>Leave records</th><th>Action</th></tr></thead><tbody>${result.students.map((student) => `<tr><td><span class="table-primary">${escapeHtml(student.name)}</span><span class="table-sub">${escapeHtml(student.email)}</span></td><td><span class="table-primary">${escapeHtml(student.registration_no || '—')}</span><span class="table-sub">${escapeHtml(student.branch || '—')}</span></td><td><span class="table-primary">${escapeHtml(student.hostel_name || '—')}</span><span class="table-sub">Room ${escapeHtml(student.room_no || '—')} · ${escapeHtml(student.hostel_type || '')}</span></td><td><span class="table-primary">${student.leave_count}</span><span class="table-sub">${student.outside ? '<span class="status-badge status-outside">Currently outside</span>' : 'No active outside pass'}</span></td><td><button class="btn btn-secondary btn-small" data-history="${escapeHtml(student._id)}">View history</button></td></tr>`).join('')}</tbody></table>`;
    box.querySelectorAll('[data-history]').forEach((button) => button.addEventListener('click', () => loadStudentHistory(button.dataset.history)));
  } catch (error) { box.innerHTML = ''; showAlert('alert', error.message); }
}

async function loadStudentHistory(studentId) {
  const panel = document.getElementById('student-history');
  panel.classList.remove('hidden'); panel.innerHTML = '<div class="empty-state">Loading student history…</div>';
  try {
    const result = await api(`/api/warden/students/${encodeURIComponent(studentId)}/leaves`);
    const student = result.student;
    panel.innerHTML = `<div class="card-heading"><div><div class="section-kicker">STUDENT PROFILE</div><h3>${escapeHtml(student.name)}</h3><p class="muted">${escapeHtml(student.registration_no)} · ${escapeHtml(student.branch)} · Hostel ${escapeHtml(student.hostel_name)} · Room ${escapeHtml(student.room_no)}</p></div><button id="close-student-history" class="btn btn-secondary btn-small">Close</button></div>${result.leaves.length ? `<div class="table-wrap"><table class="data-table"><thead><tr><th>Leave ID</th><th>Reason / Dates</th><th>Status</th><th>Gate times</th></tr></thead><tbody>${result.leaves.map((leave) => `<tr><td>${escapeHtml(leave.leave_id)}</td><td><span class="table-primary">${escapeHtml(leave.reason)}</span><span class="table-sub">${formatDate(leave.start_date)} – ${formatDate(leave.end_date)}</span></td><td>${statusBadge(leave.status)}</td><td><span class="table-sub">Out: ${formatDateTime(leave.checked_out_at)}</span><span class="table-sub">In: ${formatDateTime(leave.checked_in_at)}</span></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty-state">No leave history yet.</div>'}`;
    document.getElementById('close-student-history').addEventListener('click', () => panel.classList.add('hidden'));
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) { panel.innerHTML = `<div class="alert">${escapeHtml(error.message)}</div>`; }
}
