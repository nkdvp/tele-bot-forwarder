// ── Delete confirmation modal ──────────────────────────────────────────────

const deleteModal = document.getElementById('delete-modal');
const modalPairName = document.getElementById('modal-pair-name');
const modalConfirmBtn = document.getElementById('modal-confirm');

function openDeleteModal(name) {
  if (!deleteModal) return;
  modalPairName.textContent = name;
  deleteModal.dataset.pairName = name;
  deleteModal.classList.add('open');
}

function closeDeleteModal() {
  if (!deleteModal) return;
  deleteModal.classList.remove('open');
}

if (modalConfirmBtn) {
  modalConfirmBtn.addEventListener('click', async () => {
    const name = deleteModal.dataset.pairName;
    try {
      const res = await fetch(`/api/pairs/${encodeURIComponent(name)}`, { method: 'DELETE' });
      if (res.ok) {
        const row = document.querySelector(`tr[data-pair="${name}"]`);
        if (row) row.remove();
        closeDeleteModal();
        showToast(`Pair "${name}" deleted`, 'success');
      } else {
        closeDeleteModal();
        showToast('Delete failed', 'error');
      }
    } catch {
      closeDeleteModal();
      showToast('Request failed', 'error');
    }
  });
}

// Close modal on overlay click
if (deleteModal) {
  deleteModal.addEventListener('click', (e) => {
    if (e.target === deleteModal) closeDeleteModal();
  });
}

// ── Enable/disable toggle ──────────────────────────────────────────────────

async function togglePairEnabled(name, checkbox) {
  const originalState = !checkbox.checked;
  try {
    const listRes = await fetch(`/api/pairs?q=${encodeURIComponent(name)}`);
    if (!listRes.ok) throw new Error('fetch failed');
    const listData = await listRes.json();
    const pair = listData.pairs.find(p => p.name === name);
    if (!pair) throw new Error('pair not found');

    pair.enabled = checkbox.checked;
    const res = await fetch(`/api/pairs/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pair),
    });

    if (!res.ok) throw new Error('update failed');

    const badge = document.querySelector(`[data-enabled-badge="${name}"]`);
    if (badge) {
      badge.textContent = checkbox.checked ? 'Enabled' : 'Disabled';
      badge.className = `badge ${checkbox.checked ? 'badge-success' : 'badge-danger'}`;
    }
  } catch {
    checkbox.checked = originalState;
    showToast('Could not update pair', 'error');
  }
}

// ── Mask alias suggestions ────────────────────────────────────────────────

const telegramUserInput = document.getElementById('telegram_user_id');
const aliasSuggestions = document.getElementById('alias-suggestions');
const maskModeInput = document.getElementById('mode');
const aliasFieldGroup = document.getElementById('alias-field-group');
const aliasInput = document.getElementById('alias');

function syncMaskAliasVisibility() {
  if (!maskModeInput || !aliasFieldGroup || !aliasInput) return;
  const useAlias = maskModeInput.value === 'alias';
  aliasFieldGroup.style.display = useAlias ? '' : 'none';
  aliasInput.disabled = !useAlias;
  aliasInput.required = useAlias;
  if (!useAlias) {
    aliasInput.value = '';
    if (aliasSuggestions) aliasSuggestions.innerHTML = '';
  }
}

if (maskModeInput) {
  syncMaskAliasVisibility();
  maskModeInput.addEventListener('change', syncMaskAliasVisibility);
}

if (telegramUserInput && aliasSuggestions) {
  telegramUserInput.addEventListener('change', async () => {
    if (maskModeInput && maskModeInput.value !== 'alias') return;
    const userId = telegramUserInput.value.trim();
    aliasSuggestions.innerHTML = '';
    if (!userId) return;
    try {
      const res = await fetch(`/api/mask-aliases?telegram_user_id=${encodeURIComponent(userId)}`);
      if (!res.ok) return;
      const data = await res.json();
      for (const alias of data.aliases || []) {
        const option = document.createElement('option');
        option.value = alias;
        aliasSuggestions.appendChild(option);
      }
    } catch {
      // Suggestions are optional; keep the form usable if the lookup fails.
    }
  });
}

// ── Backup trigger ─────────────────────────────────────────────────────────

const backupBtn = document.getElementById('backup-btn');

if (backupBtn) {
  backupBtn.addEventListener('click', async () => {
    backupBtn.disabled = true;
    backupBtn.textContent = 'Creating…';
    try {
      const res = await fetch('/api/backup', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        const filename = data.backup_path.split('/').pop();
        showToast(`Backup created: ${filename}`, 'success');
        setTimeout(() => location.reload(), 1500);
      } else {
        showToast(data.error || 'Backup failed', 'error');
        backupBtn.disabled = false;
        backupBtn.textContent = 'Create backup now';
      }
    } catch {
      showToast('Request failed', 'error');
      backupBtn.disabled = false;
      backupBtn.textContent = 'Create backup now';
    }
  });
}

// ── Toast notification ─────────────────────────────────────────────────────

function showToast(message, type) {
  const toast = document.createElement('div');
  toast.className = `alert alert-${type}`;
  toast.style.cssText = [
    'position:fixed',
    'bottom:24px',
    'right:24px',
    'z-index:999',
    'max-width:320px',
    'animation:fadeIn 0.2s ease',
    'pointer-events:none',
  ].join(';');
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}
