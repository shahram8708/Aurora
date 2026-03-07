document.addEventListener('DOMContentLoaded', () => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const getCookie = (name) => document.cookie.split('; ').find((row) => row.startsWith(`${name}=`))?.split('=')[1];

  const hasJwt = document.cookie.includes('access_token_cookie=') || document.cookie.includes('refresh_token_cookie=');
  const isAuthed = (window.isAuthenticated === true || window.isAuthenticated === 'true') || hasJwt;
  if (!isAuthed) return; // Skip realtime features for unauthenticated users

  const csrfHeader = () => getCookie('csrf_access_token') || csrfToken;

  const refreshJwt = async () => {
    const csrf = getCookie('csrf_refresh_token');
    const headers = csrf ? { 'X-CSRF-TOKEN': csrf } : {};
    const resp = await fetch('/refresh', {
      method: 'POST',
      credentials: 'same-origin',
      headers,
    });
    return resp.ok;
  };

  const getJSON = async (url, opts = {}, retry = true) => {
    const csrfJwt = getCookie('csrf_access_token');
    const headers = {
      'X-CSRF-TOKEN': csrfJwt || csrfToken,
      ...(opts.headers || {}),
    };
    const resp = await fetch(url, { headers, credentials: 'same-origin', ...opts });
    if (resp.status === 401 && retry) {
      const refreshed = await refreshJwt();
      if (refreshed) return getJSON(url, opts, false);
    }
    if (!resp.ok) throw new Error(`Request failed: ${resp.status}`);
    return resp.json();
  };

  // Notifications socket
  let notifSocket;
  const notifCountEl = document.getElementById('notif-count');
  const notifDropdown = document.getElementById('notif-dropdown');
  const notifToggle = document.getElementById('notif-toggle');

  const setDropdownMessage = (text, variant = 'secondary') => {
    if (!notifDropdown) return;
    const li = document.createElement('li');
    li.innerHTML = `<span class="dropdown-item text-${variant}">${text}</span>`;
    notifDropdown.innerHTML = '';
    notifDropdown.appendChild(li);
  };

  const resolveLink = (n) => {
    if (n.type === 'follow_request') {
      const target = n.meta?.requester_id || n.actor_id;
      if (target) return `/profile/${target}`;
    }
    if (n.type === 'follow') {
      if (n.actor_id) return `/profile/${n.actor_id}`;
    }
    return '/notifications/page';
  };

  const renderNotif = (n) => {
    const title = n.type?.replace(/_/g, ' ') || 'Notification';
    const detail = n.meta?.message_type || n.reference_id || '';
    const href = resolveLink(n);
    const li = document.createElement('li');
    li.innerHTML = `<a class="dropdown-item" href="${href}">${title}${detail ? ' - ' + detail : ''}</a>`;
    return li;
  };

  const updateUnreadBadge = (count) => {
    if (!notifCountEl) return;
    if (count > 0) {
      notifCountEl.style.display = 'inline-block';
      notifCountEl.textContent = count;
    } else {
      notifCountEl.style.display = 'none';
    }
  };

  const loadUnreadCount = async () => {
    try {
      const data = await getJSON('/notifications/unread-count');
      console.debug('unread-count', data);
      updateUnreadBadge(data.unread || 0);
    } catch (e) {
      console.warn('unread load failed', e);
      updateUnreadBadge(0);
    }
  };

  const loadNotifList = async () => {
    if (!notifDropdown) return;
    setDropdownMessage('Loading...');
    try {
      const data = await getJSON('/notifications/?limit=5');
      console.debug('notif list', data);
      notifDropdown.innerHTML = '';
      if (!Array.isArray(data) || data.length === 0) {
        setDropdownMessage('No notifications yet', 'muted');
        return;
      }
      data.forEach((n) => notifDropdown.appendChild(renderNotif(n)));
      const viewAll = document.createElement('li');
      viewAll.innerHTML = '<hr class="dropdown-divider">';
      notifDropdown.appendChild(viewAll);
      const linkAll = document.createElement('li');
      linkAll.innerHTML = '<a class="dropdown-item text-primary" href="/notifications/page">View all</a>';
      notifDropdown.appendChild(linkAll);
    } catch (e) {
      console.warn('notif list load failed', e);
      setDropdownMessage(`Failed to load: ${e.message}`, 'danger');
    }
  };

  const initNotifSocket = () => {
    if (!window.io || !notifDropdown) return;
    notifSocket = io('/ws/notifications', { transports: ['websocket', 'polling'], withCredentials: true });
    notifSocket.on('notification', (n) => {
      console.debug('socket notification', n);
      notifDropdown.prepend(renderNotif(n));
      loadUnreadCount();
    });
    notifSocket.on('connected', () => loadUnreadCount());
    notifSocket.on('connect_error', (err) => {
      console.warn('notif socket error', err);
      setDropdownMessage('Realtime connection failed', 'danger');
    });
  };

  if (notifToggle) {
    notifToggle.addEventListener('click', () => {
      loadNotifList();
      loadUnreadCount();
    });
    notifToggle.addEventListener('show.bs.dropdown', () => {
      loadNotifList();
      loadUnreadCount();
    });
  }

  // Messaging socket
  let msgSocket;
  const conversationView = document.getElementById('conversation-view');
  const conversationId = conversationView?.dataset?.conversationId;
  const chatMessages = document.getElementById('chat-messages');
  const chatForm = document.getElementById('chat-form');
  const chatText = document.getElementById('chat-text');
  const markReadBtn = document.getElementById('mark-read-btn');
  const gifModalEl = document.getElementById('gifModal');
  const gifModal = gifModalEl ? new bootstrap.Modal(gifModalEl) : null;
  const gifSearchInput = document.getElementById('gif-search');
  const gifResults = document.getElementById('gif-results');
  const gifLoading = document.getElementById('gif-loading');
  const gifEmpty = document.getElementById('gif-empty');

  const renderMessageContent = (m) => {
    const url = m.media_url;
    if (['image', 'video', 'file', 'voice', 'gif'].includes(m.message_type) && url) {
      const label = m.message_type === 'gif'
        ? 'GIF'
        : (m.message_type === 'voice' ? 'Voice message' : 'Attachment');
      return `<a href="${url}" target="_blank" class="text-info">${label}</a>`;
    }
    return m.content || url || 'Unsupported message';
  };

  const formatTime = (ts) => {
    const d = ts ? new Date(ts) : new Date();
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const hasMessageNode = (id) => !!chatMessages?.querySelector(`[data-message-id="${id}"]`);

  const appendMessage = (m) => {
    if (!chatMessages || !m || (m.id && hasMessageNode(m.id))) return;
    const div = document.createElement('div');
    div.className = `chat-bubble ${m.sender_id === window.currentUserId ? 'sent' : 'received'}`;
    div.dataset.messageId = m.id;
    div.innerHTML = `
      ${m.reply_to_id ? `<div class="reply-ref small text-muted">Reply to ${m.reply_to_id}</div>` : ''}
      <div class="content">${renderMessageContent(m)}</div>
      <div class="meta text-muted small d-flex gap-2 align-items-center">
        <span>${formatTime(m.created_at)}</span>
        <span class="reaction" data-reaction></span>
      </div>`;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    console.debug('Appended message', m);
  };

  const scrollToBottom = () => {
    if (!chatMessages) return;
    chatMessages.scrollTop = chatMessages.scrollHeight;
  };

  const markRead = () => {
    if (!conversationId || !msgSocket) return;
    msgSocket.emit('mark_read', { conversation_id: conversationId });
  };

  const initMsgSocket = () => {
    if (!window.io) return;
    msgSocket = io('/ws/messages', { transports: ['websocket', 'polling'], withCredentials: true });
    msgSocket.on('connected', () => {
      if (conversationId) {
        msgSocket.emit('join_conversation', { conversation_id: conversationId });
        markRead();
      }
    });
    msgSocket.on('connect_error', (err) => {
      console.warn('Message socket error', err);
    });
    msgSocket.on('message', (m) => {
      console.debug('Socket message received', m);
      appendMessage(m);
    });
    msgSocket.on('reaction', (p) => {
      if (!chatMessages) return;
      const node = chatMessages.querySelector(`[data-message-id="${p.message_id}"] [data-reaction]`);
      if (node) node.textContent = p.reaction_type || '';
    });
    window.addEventListener('focus', markRead);
  };

  const sendMessage = async (payload) => {
    const basePayload = { ...payload, conversation_id: payload.conversation_id || conversationId };
    if (!basePayload.conversation_id) return;
    console.debug('Sending message', basePayload);
    if (msgSocket && msgSocket.connected) {
      msgSocket.emit('send_message', basePayload);
      setTimeout(() => syncLatest(), 400); // fallback sync
      return;
    }
    try {
      const resp = await fetch('/messaging/messages', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfHeader(),
        },
        body: JSON.stringify(basePayload),
      });
      if (resp.ok) {
        const data = await resp.json();
        appendMessage(data);
      } else {
        console.warn('Send failed', resp.status);
      }
    } catch (err) {
      console.warn('Send failed', err);
    }
  };

  if (chatForm && conversationView) {
    chatForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = chatText.value.trim();
      if (!text) return;
      await sendMessage({ message_type: 'text', content: text });
      chatText.value = '';
      scrollToBottom();
    });
  }

  if (markReadBtn) {
    markReadBtn.addEventListener('click', () => markRead());
  }

  const attachmentInput = document.createElement('input');
  attachmentInput.type = 'file';
  attachmentInput.className = 'd-none';
  document.body.appendChild(attachmentInput);

  const uploadAttachment = async (file, typeHint) => {
    if (!file) return null;
    const form = new FormData();
    form.append('file', file);
    form.append('csrf_token', csrfToken);
    if (typeHint) form.append('type', typeHint);
    const resp = await fetch('/messaging/attachments', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrfHeader() },
      body: form,
    });
    if (!resp.ok) throw new Error(`Upload failed (${resp.status})`);
    return resp.json();
  };

  attachmentInput.addEventListener('change', async () => {
    const file = attachmentInput.files?.[0];
    const typeHint = attachmentInput.dataset.type || '';
    if (!file || !conversationId) return;
    try {
      const uploaded = await uploadAttachment(file, typeHint);
      if (!uploaded) return;
      await sendMessage({
        message_type: uploaded.message_type,
        media_url: uploaded.media_url,
        media_mime: uploaded.media_mime,
        media_size: uploaded.media_size,
      });
    } catch (err) {
      alert(err.message || 'Upload failed');
    } finally {
      attachmentInput.value = '';
      attachmentInput.dataset.type = '';
    }
  });

  const attachFileBtn = document.getElementById('attach-file');
  const attachVoiceBtn = document.getElementById('attach-voice');
  const attachGifBtn = document.getElementById('attach-gif');

  attachFileBtn?.addEventListener('click', () => {
    attachmentInput.accept = '*/*';
    attachmentInput.dataset.type = 'file';
    attachmentInput.click();
  });

  attachVoiceBtn?.addEventListener('click', () => {
    attachmentInput.accept = 'audio/*';
    attachmentInput.dataset.type = 'voice';
    attachmentInput.click();
  });

  const renderGifs = (items) => {
    if (!gifResults) return;
    gifResults.innerHTML = '';
    if (!items || items.length === 0) {
      gifEmpty?.classList.remove('d-none');
      return;
    }
    gifEmpty?.classList.add('d-none');
    items.forEach((item) => {
      const url = item?.media_formats?.tinygif?.url || item?.media_formats?.gif?.url;
      if (!url) return;
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'p-0 border-0 bg-transparent';
      btn.innerHTML = `<img src="${url}" alt="gif" class="gif-thumb">`;
      btn.addEventListener('click', async () => {
        if (!conversationId) return;
        try {
          await sendMessage({ message_type: 'gif', media_url: url, gif_provider: 'tenor' });
          gifModal?.hide();
        } catch (err) {
          alert('Unable to send GIF');
        }
      });
      gifResults.appendChild(btn);
    });
  };

  const setGifLoading = (state) => {
    if (gifLoading) gifLoading.classList.toggle('d-none', !state);
  };

  const loadGifs = async (term) => {
    if (!gifResults) return;
    try {
      setGifLoading(true);
      gifEmpty?.classList.add('d-none');
      const qs = term && term.trim() ? `?q=${encodeURIComponent(term.trim())}` : '';
      const resp = await fetch(`/messaging/gifs${qs}`, { credentials: 'same-origin' });
      if (!resp.ok) throw new Error('GIF fetch failed');
      const data = await resp.json();
      renderGifs(data?.results || []);
    } catch (err) {
      gifResults.innerHTML = '<div class="text-danger small">Failed to load GIFs</div>';
    } finally {
      setGifLoading(false);
    }
  };

  let gifSearchTimer;
  gifSearchInput?.addEventListener('input', (e) => {
    const term = e.target.value;
    clearTimeout(gifSearchTimer);
    gifSearchTimer = setTimeout(() => loadGifs(term), 320);
  });

  attachGifBtn?.addEventListener('click', async () => {
    if (!conversationId || !gifModal) return;
    gifModal.show();
    if (!gifResults || gifResults.children.length === 0) {
      loadGifs('trending');
    }
  });

  const syncLatest = async () => {
    if (!conversationId || !chatMessages) return;
    try {
      const resp = await fetch(`/messaging/conversations/${conversationId}/messages?limit=5`, {
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrfHeader() },
      });
      if (!resp.ok) return;
      const items = await resp.json();
      (items || []).forEach((m) => appendMessage(m));
      scrollToBottom();
    } catch (err) {
      console.debug('syncLatest failed', err);
    }
  };

  // Initial sync on load
  syncLatest();
  scrollToBottom();

  // Notification page loader
  const notifPage = document.getElementById('notification-page');
  if (notifPage) {
    const list = document.getElementById('notification-list');
    const btnMarkAll = document.getElementById('mark-all-read');
    const btnMarkSel = document.getElementById('mark-selected-read');
    const btnDelSel = document.getElementById('delete-selected');
    const btnDelAll = document.getElementById('delete-all');

    const buildCsrfHeaders = (extra = {}) => {
      const token = csrfHeader();
      if (!token) return { ...extra };
      // Flask-WTF accepts X-CSRFToken or X-CSRF-Token; send both to be safe
      return {
        'X-CSRFToken': token,
        'X-CSRF-Token': token,
        ...extra,
      };
    };

    const renderPageNotif = (n) => {
      const title = n.type?.replace(/_/g, ' ') || 'Notification';
      const detail = n.meta?.message_type || n.reference_id || '';
      const item = document.createElement('div');
      item.className = 'list-group-item d-flex align-items-center gap-3';
      item.dataset.id = n.id;
      item.innerHTML = `
        <input class="form-check-input" type="checkbox" data-check>
        <div class="flex-grow-1">
          <div class="d-flex justify-content-between align-items-center">
            <span class="fw-semibold">${title}</span>
            <small class="text-muted">${new Date(n.created_at).toLocaleString()}</small>
          </div>
          <div class="text-muted small">${detail}</div>
        </div>
        <div class="d-flex gap-2">
          ${n.is_read ? '<span class="badge bg-secondary">Read</span>' : '<span class="badge bg-primary">New</span>'}
          <button class="btn btn-sm btn-outline-secondary" data-action="mark-read">Mark read</button>
          <button class="btn btn-sm btn-outline-danger" data-action="delete">Delete</button>
        </div>`;
      return item;
    };

    const selectedIds = () => Array.from(list.querySelectorAll('[data-check]:checked')).map((c) => c.closest('[data-id]').dataset.id);

    const renderList = async () => {
      try {
        const data = await getJSON('/notifications/?limit=50');
        list.innerHTML = '';
        if (!Array.isArray(data) || data.length === 0) {
          list.innerHTML = '<div class="list-group-item text-muted">No notifications yet</div>';
          return;
        }
        data.forEach((n) => list.appendChild(renderPageNotif(n)));
      } catch (e) {
        list.innerHTML = `<div class="list-group-item text-danger">Failed to load: ${e.message}</div>`;
      }
    };

    list.addEventListener('click', async (e) => {
      const btn = e.target.closest('button[data-action]');
      if (!btn) return;
      const item = btn.closest('[data-id]');
      const nid = item?.dataset.id;
      if (!nid) return;
      const action = btn.dataset.action;
      if (action === 'mark-read') {
        await fetch(`/notifications/${nid}/read`, { method: 'POST', headers: buildCsrfHeaders() });
      }
      if (action === 'delete') {
        await fetch(`/notifications/${nid}/delete`, { method: 'POST', headers: buildCsrfHeaders() });
      }
      await renderList();
      await loadUnreadCount();
    });

    btnMarkAll?.addEventListener('click', async () => {
      await fetch('/notifications/read', { method: 'POST', headers: buildCsrfHeaders() });
      await renderList();
      await loadUnreadCount();
    });

    btnMarkSel?.addEventListener('click', async () => {
      const ids = selectedIds();
      if (ids.length === 0) return;
      await fetch('/notifications/read', { method: 'POST', headers: buildCsrfHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ ids }) });
      await renderList();
      await loadUnreadCount();
    });

    btnDelSel?.addEventListener('click', async () => {
      const ids = selectedIds();
      if (ids.length === 0) return;
      await fetch('/notifications/delete', { method: 'POST', headers: buildCsrfHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ ids }) });
      await renderList();
      await loadUnreadCount();
    });

    btnDelAll?.addEventListener('click', async () => {
      await fetch('/notifications/delete-all', { method: 'POST', headers: buildCsrfHeaders() });
      await renderList();
      await loadUnreadCount();
    });

    renderList();
  }

  loadUnreadCount();
  initNotifSocket();
  initMsgSocket();
});
