console.info('[engagement] main.js loaded');
window.addEventListener('error', (e) => {
  console.error('[engagement] window error', e.message, e.filename, e.lineno, e.colno, e.error);
});
window.addEventListener('unhandledrejection', (e) => {
  console.error('[engagement] unhandled promise rejection', e.reason);
});

document.addEventListener('DOMContentLoaded', () => {
  console.info('[engagement] DOMContentLoaded handler start');
  console.info('[engagement] attaching click listeners');

  // Capture-phase listener to verify clicks reach the page, even if bubbling is stopped.
  document.addEventListener('click', (e) => {
    const targetBtn = e.target.closest('.delete-comment-btn, .pin-comment-btn');
    if (targetBtn) {
      console.debug('[engagement] capture click seen', {
        className: targetBtn.className,
        commentId: targetBtn.dataset?.commentId,
        pinned: targetBtn.dataset?.pinned,
      });
    }
  }, true);
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach((a) => {
    const bsAlert = window.bootstrap?.Alert ? new bootstrap.Alert(a) : null;
    setTimeout(() => {
      if (bsAlert) {
        bsAlert.close();
      } else {
        a.classList.add('d-none');
        a.remove();
      }
    }, 5000);
  });

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';

  const getCookie = (name) => {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
  };

  const handle = async (url, options = {}) => {
    const jwtCsrf = getCookie('csrf_access_token') || getCookie('csrf_refresh_token');
    const baseHeaders = {
      'X-CSRFToken': csrfToken,
      'X-CSRF-Token': csrfToken,
      'X-CSRF-TOKEN': jwtCsrf || csrfToken,
      'X-Requested-With': 'XMLHttpRequest',
      'Accept': 'application/json',
    };
    const contentHeader = options.body ? { 'Content-Type': 'application/json' } : {};
    const method = options.method || 'GET';
    console.debug('[engagement] fetch start', method, url);
    const resp = await fetch(url, {
      credentials: 'same-origin',
      headers: { ...baseHeaders, ...contentHeader, ...(options.headers || {}) },
      ...options,
    });
    const data = await resp.json().catch(() => ({}));
    console.debug('[engagement] fetch done', method, url, resp.status, data);
    if (!resp.ok) {
      const msg = data?.error || data?.message || 'Request failed';
      const err = new Error(msg);
      err.status = resp.status;
      err.payload = data;
      throw err;
    }
    return data;
  };

  function movePinnedToTop(block) {
    const container = block.closest('.comment-thread, .replies');
    if (!container) return;
    const first = container.querySelector('.comment-block, .reply-block');
    if (first && first !== block) {
      container.insertBefore(block, first);
    }
  }

  function restorePinnedOrder(block) {
    // On unpin we leave the item in place; server render will restore canonical order on refresh.
    return block;
  }

  const escapeHtml = (unsafe = '') => String(unsafe)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');

  let dmShareModal;
  let dmShareList;
  let dmShareSearch;
  let dmShareStatus;
  let dmShareNote;
  let dmShareTarget = null; // { type: 'post' | 'reel', id: string }
  let dmSearchTimer = null;

  const setDmStatus = (msg, isError = false) => {
    if (!dmShareStatus) return;
    dmShareStatus.textContent = msg || '';
    dmShareStatus.classList.toggle('text-danger', !!isError);
  };

  const sharePostToUser = async (user) => {
    if (!dmShareTarget || !dmShareTarget.id || !user?.id) return;
    const endpoint = dmShareTarget.type === 'reel'
      ? `/reels/${dmShareTarget.id}/share/dm`
      : `/engagement/share/dm/${dmShareTarget.id}`;
    setDmStatus(`Sending to @${user.username}…`);
    try {
      const resp = await handle(endpoint, {
        method: 'POST',
        body: JSON.stringify({
          receiver_id: user.id,
          note: dmShareNote?.value || '',
        }),
      });
      setDmStatus('Sent! Opening chat…');
      if (resp?.conversation_id) {
        dmShareModal?.hide();
        window.location.href = `/messaging/conversations/${resp.conversation_id}/view`;
      } else {
        setDmStatus('Shared, but could not open chat.', true);
      }
    } catch (err) {
      setDmStatus(err.message || 'Unable to send right now', true);
    }
  };

  const buildRecipientRow = (user) => {
    const badgeLabel = user.is_following && user.is_follower ? 'Mutual' : user.is_following ? 'Following' : user.is_follower ? 'Follower' : '';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'list-group-item list-group-item-action d-flex align-items-center justify-content-between';
    const avatar = user.avatar
      ? `<img src="${escapeHtml(user.avatar)}" alt="" class="rounded-circle" style="width:36px;height:36px;object-fit:cover;">`
      : `<div class="rounded-circle bg-light border d-flex align-items-center justify-content-center" style="width:36px;height:36px;">
           <span class="text-muted fw-semibold">${escapeHtml((user.username || '?')[0] || '?').toUpperCase()}</span>
         </div>`;
    btn.innerHTML = `
      <div class="d-flex align-items-center gap-2">
        ${avatar}
        <div class="text-start">
          <div class="fw-semibold mb-0">${escapeHtml(user.name || user.username)}</div>
          <div class="text-muted small">@${escapeHtml(user.username)}</div>
        </div>
      </div>
      ${badgeLabel ? `<span class="badge bg-secondary">${badgeLabel}</span>` : ''}
    `;
    btn.addEventListener('click', () => sharePostToUser(user));
    return btn;
  };

  const ensureShareDmModal = () => {
    if (!document.getElementById('shareDmModal')) {
      document.body.insertAdjacentHTML('beforeend', `
        <div class="modal fade" id="shareDmModal" tabindex="-1" aria-hidden="true">
          <div class="modal-dialog modal-dialog-centered">
            <div class="modal-content">
              <div class="modal-header">
                <h5 class="modal-title d-flex align-items-center gap-2"><i class="bi bi-send"></i><span>Share via DM</span></h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
              </div>
              <div class="modal-body">
                <div class="mb-3">
                  <label class="form-label mb-1 small text-uppercase text-muted">Add a message (optional)</label>
                  <textarea class="form-control" id="share-dm-note" rows="2" placeholder="Say something about this post"></textarea>
                </div>
                <div class="input-group input-group-sm mb-2">
                  <span class="input-group-text"><i class="bi bi-search"></i></span>
                  <input type="search" class="form-control" id="share-dm-search" placeholder="Search followers">
                  <button class="btn btn-outline-secondary" type="button" id="share-dm-refresh" aria-label="Refresh list"><i class="bi bi-arrow-repeat"></i></button>
                </div>
                <div class="small text-muted mb-2" id="share-dm-status"></div>
                <div class="list-group" id="share-dm-list" style="max-height:320px;overflow-y:auto;">
                  <div class="text-center text-muted py-3">Loading followers…</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      `);
    }
    const modalEl = document.getElementById('shareDmModal');
    dmShareModal = dmShareModal || new bootstrap.Modal(modalEl);
    dmShareList = dmShareList || modalEl.querySelector('#share-dm-list');
    dmShareSearch = dmShareSearch || modalEl.querySelector('#share-dm-search');
    dmShareStatus = dmShareStatus || modalEl.querySelector('#share-dm-status');
    dmShareNote = dmShareNote || modalEl.querySelector('#share-dm-note');

    modalEl.addEventListener('shown.bs.modal', () => dmShareSearch?.focus());
    const refreshBtn = modalEl.querySelector('#share-dm-refresh');
    if (refreshBtn && !refreshBtn.dataset.bound) {
      refreshBtn.dataset.bound = 'true';
      refreshBtn.addEventListener('click', () => loadDmRecipients(dmShareSearch?.value || ''));
    }
    if (dmShareSearch && !dmShareSearch.dataset.bound) {
      dmShareSearch.dataset.bound = 'true';
      dmShareSearch.addEventListener('input', (e) => {
        const term = e.target.value || '';
        clearTimeout(dmSearchTimer);
        dmSearchTimer = setTimeout(() => loadDmRecipients(term), 200);
      });
    }
    return dmShareModal;
  };

  const loadDmRecipients = async (term = '') => {
    ensureShareDmModal();
    if (!dmShareList) return;
    dmShareList.innerHTML = '<div class="text-center text-muted py-3">Loading followers…</div>';
    try {
      const qs = term ? `?q=${encodeURIComponent(term)}` : '';
      const data = await handle(`/engagement/share/dm/recipients${qs}`, { method: 'GET' });
      const results = data?.results || [];
      if (!results.length) {
        dmShareList.innerHTML = '<div class="text-center text-muted py-3">No followers available yet.</div>';
        return;
      }
      dmShareList.innerHTML = '';
      results.forEach((u) => dmShareList.appendChild(buildRecipientRow(u)));
      setDmStatus('Tap a name to share.');
    } catch (err) {
      dmShareList.innerHTML = `<div class="text-center text-danger py-3">${escapeHtml(err.message || 'Unable to load followers')}</div>`;
    }
  };

  const openShareDmModal = (target) => {
    dmShareTarget = target;
    ensureShareDmModal();
    if (dmShareNote) dmShareNote.value = '';
    setDmStatus('Select a follower to share.');
    loadDmRecipients(dmShareSearch?.value || '');
    dmShareModal?.show();
  };

  document.body.addEventListener('click', async (e) => {
    console.debug('[engagement] body click handler running', { target: e.target?.className });
    const likeBtn = e.target.closest('.like-btn');
    const saveBtn = e.target.closest('.save-btn');
    const commentBtn = e.target.closest('.comment-btn');
    const postCard = e.target.closest('.post-card');
    const shareStoryBtn = e.target.closest('.share-story');
    const shareDmBtn = e.target.closest('.share-dm');
    const deleteCommentBtn = e.target.closest('.delete-comment-btn');
    const pinCommentBtn = e.target.closest('.pin-comment-btn');
    const messageBtn = e.target.closest('.message-btn');
    const replyBtn = e.target.closest('.reply-btn');
    const shareBtn = e.target.closest('.share-btn');
    const loadMoreCommentsBtn = e.target.closest('.load-more-comments');
    const loadMoreRepliesBtn = e.target.closest('.load-more-replies');
    const carouselControl = e.target.closest('[data-bs-slide]');
    const genericInteractive = e.target.closest('a, button, input, textarea, select, option');

    if (deleteCommentBtn || pinCommentBtn) {
      console.debug('[engagement] click detected', {
        deleteCommentBtn: !!deleteCommentBtn,
        pinCommentBtn: !!pinCommentBtn,
        commentId: deleteCommentBtn?.dataset?.commentId || pinCommentBtn?.dataset?.commentId,
        target: e.target?.className,
      });
    }
    if (likeBtn) {
      const postId = likeBtn.dataset.postId;
      const data = await handle(`/engagement/like/${postId}`, { method: 'POST' });
      const countEl = document.querySelector(`.like-count[data-post-id="${postId}"]`);
      if (countEl && data.like_count !== undefined) countEl.textContent = data.like_count;
      likeBtn.classList.toggle('btn-primary', data.liked);
      return;
    }
    if (saveBtn) {
      const postId = saveBtn.dataset.postId;
      const data = await handle(`/engagement/save/${postId}`, { method: 'POST' });
      saveBtn.classList.toggle('btn-primary', data.saved);
      return;
    }
    if (commentBtn) {
      const postId = commentBtn.dataset.postId;
      document.getElementById('submit-comment').dataset.postId = postId;
      document.getElementById('comment-list').innerHTML = '';
      const modal = new bootstrap.Modal(document.getElementById('commentModal'));
      modal.show();
      return;
    }
    if (shareStoryBtn) {
      const postId = shareStoryBtn.dataset.postId;
      try {
        const data = await handle(`/engagement/share/story/${postId}`, { method: 'POST' });
        shareStoryBtn.classList.add('btn-success');
        shareStoryBtn.textContent = 'Shared';
        shareStoryBtn.title = data?.story_id ? 'Shared to your stories' : 'Shared';
      } catch (err) {
        alert('Unable to share to story right now.');
      }
      return;
    }
    if (shareDmBtn) {
      e.preventDefault();
      const postId = shareDmBtn.dataset.postId;
      openShareDmModal({ type: 'post', id: postId });
      return;
    }
    if (deleteCommentBtn) {
      e.preventDefault();
      e.stopPropagation();
      const commentId = deleteCommentBtn.dataset.commentId;
      if (!commentId) return;
      if (!confirm('Delete this comment?')) return;
      try {
        console.info('Deleting comment', commentId);
        const data = await handle(`/engagement/comment/${commentId}`, { method: 'DELETE' });
        if (data.deleted) {
          const block = document.querySelector(`[data-comment-id="${commentId}"]`);
          if (block) block.remove();
          console.info('Deleted comment', commentId);
        }
      } catch (err) {
        console.error('Delete comment failed', commentId, err);
        alert(err.message || 'Unable to delete comment right now.');
      }
      return;
    }
    if (pinCommentBtn) {
      e.preventDefault();
      e.stopPropagation();
      const commentId = pinCommentBtn.dataset.commentId;
      if (!commentId) return;
      try {
        console.info('Toggling pin for comment', commentId);
        const data = await handle(`/engagement/comment/${commentId}/pin`, { method: 'POST' });
        const block = document.querySelector(`[data-comment-id="${commentId}"]`);
        if (block) {
          let badge = block.querySelector('.pinned-badge');
          if (data.pinned) {
            if (!badge) {
              badge = document.createElement('span');
              badge.className = 'badge bg-warning text-dark pinned-badge';
              badge.textContent = 'Pinned';
              const heading = block.querySelector('.comment-heading');
              if (heading) heading.appendChild(badge);
            }
            movePinnedToTop(block);
          } else if (badge) {
            badge.remove();
            restorePinnedOrder(block);
          }
        }
        pinCommentBtn.dataset.pinned = data.pinned ? 'true' : 'false';
        pinCommentBtn.setAttribute('aria-label', data.pinned ? 'Unpin comment' : 'Pin comment');
        const icon = pinCommentBtn.querySelector('i') || pinCommentBtn;
        if (icon.classList) {
          icon.classList.toggle('bi-pin', !data.pinned);
          icon.classList.toggle('bi-pin-angle-fill', !!data.pinned);
        } else {
          pinCommentBtn.innerHTML = data.pinned ? '<i class="bi bi-pin-angle-fill"></i>' : '<i class="bi bi-pin"></i>';
        }
      } catch (err) {
        console.error('Pin comment failed', commentId, err);
        alert(err.message || 'Unable to toggle pin right now.');
      }
      return;
    }
    if (replyBtn || shareBtn || loadMoreCommentsBtn || loadMoreRepliesBtn) {
      return;
    }
    if (carouselControl) {
      // Allow carousel controls to work without opening the post modal.
      e.stopPropagation();
      return;
    }
    if (genericInteractive && postCard) {
      return;
    }
    if (postCard && !likeBtn && !saveBtn && !commentBtn) {
      const postId = postCard.dataset.postId;
      const data = await handle(`/posts/${postId}/snippet`, { method: 'GET', headers: { 'X-CSRFToken': csrfToken } });
      if (data.html) {
        document.getElementById('post-modal-body').innerHTML = data.html;
        new bootstrap.Modal(document.getElementById('postModal')).show();
      }
    }
    if (messageBtn) {
      e.preventDefault();
      const userId = messageBtn.dataset.userId;
      if (!userId) return;
      const originalText = messageBtn.textContent;
      messageBtn.disabled = true;
      messageBtn.textContent = 'Opening...';
      try {
        const resp = await handle('/messaging/conversations/direct', { method: 'POST', body: JSON.stringify({ user_id: userId }) });
        if (resp && resp.conversation_id) {
          window.location.href = `/messaging/conversations/${resp.conversation_id}/view`;
          return;
        }
        const errMsg = (resp && (resp.error || resp.msg)) || 'Unable to start chat right now';
        alert(errMsg);
      } catch (err) {
        alert(err?.message || 'Unable to start chat right now');
      } finally {
        messageBtn.disabled = false;
        messageBtn.textContent = originalText;
      }
      return;
    }
    const openStory = e.target.closest('.open-story');
    if (openStory) {
      const storyId = openStory.dataset.storyId;
      const modalEl = document.getElementById('storyModal');
      if (storyId && modalEl) {
        const resp = await fetch(`/stories/viewer/${storyId}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' }});
        const html = await resp.text();
        document.getElementById('story-modal-body').innerHTML = html;
        new bootstrap.Modal(modalEl).show();
      }
    }
  });

  const submitCommentBtn = document.getElementById('submit-comment');
  if (submitCommentBtn) {
    submitCommentBtn.addEventListener('click', async () => {
      const postId = submitCommentBtn.dataset.postId;
      const content = document.getElementById('new-comment').value;
      if (!content) return;
      const data = await handle(`/engagement/comment/${postId}`, { method: 'POST', body: JSON.stringify({ content }) });
      const list = document.getElementById('comment-list');
      const div = document.createElement('div');
      div.className = 'mb-2';
      div.textContent = data.content;
      list.prepend(div);
      document.getElementById('new-comment').value = '';
    });
  }

  const loadMoreBtn = document.getElementById('load-more');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', async () => {
      const offset = parseInt(loadMoreBtn.dataset.offset || '0', 10);
      const data = await handle(`/feed/more?offset=${offset}`, { method: 'GET', headers: { 'X-CSRFToken': csrfToken } });
      if (data.html) {
        document.getElementById('feed-container').insertAdjacentHTML('beforeend', data.html);
        loadMoreBtn.dataset.offset = offset + 10;
      }
    });
  }

  const locationInput = document.getElementById('location-search');
  if (locationInput) {
    locationInput.addEventListener('input', async (e) => {
      const term = e.target.value.trim();
      const resultsEl = document.getElementById('location-results');
      resultsEl.innerHTML = '';
      if (term.length < 2) return;
      const res = await handle(`/posts/locations/search?q=${encodeURIComponent(term)}`, { method: 'GET', headers: { 'X-CSRFToken': csrfToken } });
      res.forEach((loc) => {
        const a = document.createElement('button');
        a.type = 'button';
        a.className = 'list-group-item list-group-item-action';
        a.textContent = loc.name;
        a.addEventListener('click', () => {
          document.getElementById('location-name').value = loc.name;
          document.getElementById('location_latitude').value = loc.lat || '';
          document.getElementById('location_longitude').value = loc.lng || '';
          bootstrap.Modal.getInstance(document.getElementById('locationModal')).hide();
        });
        resultsEl.appendChild(a);
      });
    });
  }

  // Reels viewer logic
  const reelViewport = document.getElementById('reel-viewport');
  if (reelViewport) {
    const loader = document.getElementById('reel-loader');
    const seen = new Set();
    let activeCard = null;
    let currentIndex = 0;
    let isFetching = false;
    let lastTap = 0;
    let hasMore = true;

    const cards = () => Array.from(reelViewport.querySelectorAll('.reel-item'));
    const setIndices = () => cards().forEach((card, idx) => { card.dataset.index = idx; });
    setIndices();

    const ensureVideoLoaded = (card) => {
      const video = card?.querySelector('video');
      if (video && !video.src && video.dataset.src) {
        video.src = video.dataset.src;
        video.load();
      }
      return video;
    };

    const unloadFar = (idx) => {
      cards().forEach((card, i) => {
        if (Math.abs(i - idx) > 3) {
          const v = card.querySelector('video');
          if (v && v.src) {
            if (!v.paused) v.pause();
            v.removeAttribute('src');
            v.load();
          }
        }
      });
    };

    const preloadNeighbors = (idx) => {
      [idx, idx + 1, idx + 2, idx - 1].forEach((i) => {
        const card = cards()[i];
        if (!card) return;
        const v = ensureVideoLoaded(card);
        if (v && v.readyState < 2) v.load();
      });
    };

    const sendView = (card) => {
      const reelId = card.dataset.reelId;
      if (reelId && !seen.has(reelId)) {
        seen.add(reelId);
        handle(`/reels/${reelId}/view`, { method: 'POST' });
      }
    };

    const recordWatch = (card) => {
      const reelId = card.dataset.reelId;
      const video = card.querySelector('video');
      if (reelId && video && !Number.isNaN(video.currentTime) && video.currentTime > 0.1) {
        handle(`/reels/${reelId}/watch`, { method: 'POST', body: JSON.stringify({ seconds: video.currentTime }) });
      }
    };

    const activate = (card) => {
      if (!card) return;
      if (activeCard && activeCard !== card) {
        recordWatch(activeCard);
        const oldVideo = activeCard.querySelector('video');
        if (oldVideo) oldVideo.pause();
      }
      activeCard = card;
      const idx = parseInt(card.dataset.index || '0', 10) || 0;
      currentIndex = idx;
      const video = ensureVideoLoaded(card);
      if (video) {
        video.muted = card.dataset.muted !== 'false';
        video.play().catch(() => {});
      }
      sendView(card);
      preloadNeighbors(idx);
      unloadFar(idx);
      if (idx >= cards().length - 3) fetchMore();
    };

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting && entry.intersectionRatio >= 0.7) {
          activate(entry.target);
        } else {
          if (entry.target === activeCard) {
            recordWatch(entry.target);
          }
          const video = entry.target.querySelector('video');
          if (video) video.pause();
        }
      });
    }, { threshold: [0.35, 0.7, 0.95] });

    const attach = () => cards().forEach((card) => observer.observe(card));
    attach();

    const hashtagUrl = (tag) => `/explore/search?q=${encodeURIComponent(`#${tag}`)}`;
    const linkifyCaptions = (scope) => {
      (scope || document).querySelectorAll('.reel-caption').forEach((el) => {
        const text = el.textContent || '';
        if (!text.includes('#')) return;
        const parts = text.split(/(#[\w]+)/g);
        el.innerHTML = '';
        parts.forEach((part) => {
          if (part.startsWith('#') && part.length > 1) {
            const tag = part.slice(1);
            const a = document.createElement('a');
            a.href = hashtagUrl(tag);
            a.className = 'text-info text-decoration-none';
            a.textContent = part;
            el.appendChild(a);
          } else if (part) {
            el.appendChild(document.createTextNode(part));
          }
        });
      });
    };
    linkifyCaptions(reelViewport);

    const scrollToIndex = (idx) => {
      const list = cards();
      const target = list[Math.max(0, Math.min(idx, list.length - 1))];
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const fetchMore = async () => {
      if (isFetching || !hasMore) return;
      isFetching = true;
      loader?.classList.add('show');
      const cursor = parseInt(reelViewport.dataset.cursor || String(cards().length), 10) || 0;
      const limit = parseInt(reelViewport.dataset.limit || '8', 10) || 8;
      try {
        const resp = await handle(`/reels/api/feed?cursor=${cursor}&limit=${limit}`, { method: 'GET', headers: { 'X-CSRFToken': csrfToken } });
        if (resp && resp.html) {
          reelViewport.insertAdjacentHTML('beforeend', resp.html);
          reelViewport.dataset.cursor = resp.next_cursor ?? cursor + limit;
          hasMore = resp.has_more !== false;
          setIndices();
          cards().slice(-limit - 2).forEach((card) => observer.observe(card));
          linkifyCaptions(reelViewport);
          preloadNeighbors(currentIndex);
        } else {
          hasMore = false;
        }
      } catch (err) {
        // ignore
      } finally {
        loader?.classList.remove('show');
        isFetching = false;
      }
    };

    let wheelLock = false;
    reelViewport.addEventListener('wheel', (e) => {
      if (wheelLock) return;
      if (Math.abs(e.deltaY) < 12) return;
      e.preventDefault();
      wheelLock = true;
      scrollToIndex(e.deltaY > 0 ? currentIndex + 1 : currentIndex - 1);
      setTimeout(() => { wheelLock = false; }, 260);
    }, { passive: false });

    let touchStartY = 0;
    let touchStartTime = 0;
    reelViewport.addEventListener('touchstart', (e) => {
      const t = e.touches[0];
      touchStartY = t.clientY;
      touchStartTime = Date.now();
    }, { passive: true });

    reelViewport.addEventListener('touchend', (e) => {
      const t = e.changedTouches[0];
      const deltaY = t.clientY - touchStartY;
      const dt = Date.now() - touchStartTime;
      if (Math.abs(deltaY) > 45 && dt < 600) {
        scrollToIndex(deltaY < 0 ? currentIndex + 1 : currentIndex - 1);
      }
      const now = Date.now();
      if (now - lastTap < 350) {
        const card = e.target.closest('.reel-item');
        if (card) triggerLike(card, true);
      }
      lastTap = now;
    }, { passive: true });

    window.addEventListener('keydown', (e) => {
      if (!['ArrowDown', 'ArrowUp', ' ', 'Spacebar'].includes(e.key)) return;
      e.preventDefault();
      if (e.key === 'ArrowDown') scrollToIndex(currentIndex + 1);
      if (e.key === 'ArrowUp') scrollToIndex(currentIndex - 1);
      if (e.key === ' ' || e.key === 'Spacebar') {
        const video = activeCard?.querySelector('video');
        if (video) {
          if (video.paused) video.play().catch(() => {}); else video.pause();
        }
      }
    });

    const commentModalEl = document.getElementById('reelCommentModal');
    const commentModal = commentModalEl ? new bootstrap.Modal(commentModalEl) : null;
    const commentsList = document.getElementById('reel-comments');
    const commentInput = document.getElementById('reel-comment-input');
    const commentSubmit = document.getElementById('reel-comment-submit');
    const likesModalEl = document.getElementById('reelLikesModal');
    const likesModal = likesModalEl ? new bootstrap.Modal(likesModalEl) : null;
    const likesList = document.getElementById('reel-likes-list');
    let commentsState = [];

    const renderComments = (comments = []) => {
      if (!commentsList) return;
      commentsList.innerHTML = '';
      commentsState = Array.isArray(comments) ? comments : [];
      if (!comments.length) {
        commentsList.innerHTML = '<p class="text-muted mb-0">No comments yet.</p>';
        return;
      }
      commentsState.forEach((c) => {
        const div = document.createElement('div');
        div.className = 'reel-comment-item d-flex align-items-start gap-2 py-2 border-bottom border-secondary';
        const avatar = document.createElement('div');
        avatar.className = 'reel-comment-avatar';
        if (c.avatar) {
          avatar.style.backgroundImage = `url(${c.avatar})`;
        } else if (c.user) {
          avatar.textContent = (c.user[0] || '').toUpperCase();
        }
        const body = document.createElement('div');
        body.className = 'flex-grow-1';
        const header = document.createElement('div');
        header.className = 'fw-semibold';
        const link = document.createElement('a');
        link.className = 'text-decoration-none text-white';
        link.textContent = `@${c.user || 'user'}`;
        link.href = c.user_id ? `/profile/${c.user_id}` : '#';
        link.addEventListener('click', (ev) => {
          if (!c.user_id) return;
          ev.preventDefault();
          window.location.href = `/profile/${c.user_id}`;
        });
        header.appendChild(link);
        const text = document.createElement('div');
        text.className = 'small';
        text.textContent = c.content || '';
        body.appendChild(header);
        body.appendChild(text);
        div.appendChild(avatar);
        div.appendChild(body);
        commentsList.appendChild(div);
      });
    };

    const loadComments = async (reelId) => {
      if (!reelId) return;
      try {
        const resp = await handle(`/reels/${reelId}/comments`, { method: 'GET', headers: { 'X-CSRFToken': csrfToken } });
        renderComments(resp.comments || []);
      } catch (err) {
        renderComments([]);
      }
    };

    if (commentSubmit) {
      commentSubmit.addEventListener('click', async () => {
        const reelId = commentSubmit.dataset.reelId;
        const content = (commentInput?.value || '').trim();
        if (!reelId || !content) return;
        commentSubmit.disabled = true;
        try {
          const resp = await handle(`/reels/${reelId}/comments`, { method: 'POST', body: JSON.stringify({ content }) });
          if (resp.comment) {
            commentsState = [resp.comment, ...commentsState].slice(0, 200);
            renderComments(commentsState);
            commentInput.value = '';
            const btn = cards().find((c) => c.dataset.reelId === reelId)?.querySelector('[data-action="comment"] span');
            if (btn) btn.textContent = commentsState.length.toString();
          }
        } finally {
          commentSubmit.disabled = false;
        }
      });
    }

    const triggerLike = (card, animate = false) => {
      const reelId = card.dataset.reelId;
      const btn = card.querySelector('[data-action="like"]');
      if (btn && btn.classList.contains('active')) return;
      if (btn) btn.classList.add('active');
      handle(`/reels/${reelId}/like`, { method: 'POST' });
      const countEl = btn?.querySelector('span');
      if (countEl) {
        const next = (parseInt(countEl.textContent || '0', 10) || 0) + 1;
        countEl.textContent = next.toString();
      }
      if (animate) {
        const burst = card.querySelector('.reel-like-burst');
        if (burst) {
          burst.classList.remove('show');
          // eslint-disable-next-line no-unused-expressions
          burst.offsetWidth;
          burst.classList.add('show');
          setTimeout(() => burst.classList.remove('show'), 650);
        }
      }
    };

    const renderLikes = (likes = []) => {
      if (!likesList) return;
      likesList.innerHTML = '';
      const list = Array.isArray(likes) ? likes : [];
      if (!list.length) {
        likesList.innerHTML = '<p class="text-muted mb-0">No likes yet.</p>';
        return;
      }
      list.forEach((u) => {
        const row = document.createElement('div');
        row.className = 'd-flex align-items-center gap-2 py-2 border-bottom border-secondary';
        const avatar = document.createElement('div');
        avatar.className = 'reel-comment-avatar';
        if (u.avatar) avatar.style.backgroundImage = `url(${u.avatar})`;
        const link = document.createElement('a');
        link.className = 'text-decoration-none text-white fw-semibold';
        link.href = u.user_id ? `/profile/${u.user_id}` : '#';
        link.textContent = u.username ? `@${u.username}` : 'user';
        link.addEventListener('click', (ev) => {
          if (!u.user_id) return;
          ev.preventDefault();
          window.location.href = `/profile/${u.user_id}`;
        });
        row.appendChild(avatar);
        row.appendChild(link);
        likesList.appendChild(row);
      });
    };

    const loadLikes = async (reelId) => {
      if (!reelId) return;
      try {
        const resp = await handle(`/reels/${reelId}/likes`, { method: 'GET', headers: { 'X-CSRFToken': csrfToken } });
        renderLikes(resp.likes || []);
      } catch (err) {
        renderLikes([]);
      }
    };

    reelViewport.addEventListener('click', (e) => {
      const actionBtn = e.target.closest('.reel-action');
      const usernameLink = e.target.closest('.reel-username-link');
      const likeCount = e.target.closest('.reel-like-count');
      const card = e.target.closest('.reel-item');
      if (!card) return;
      if (likeCount) {
        const reelId = likeCount.dataset.reelId || card.dataset.reelId;
        if (reelId && likesModal) {
          loadLikes(reelId);
          likesModal.show();
        }
        return;
      }
      if (usernameLink) {
        e.preventDefault();
        const userId = usernameLink.dataset.userId || card.dataset.userId;
        if (userId) window.location.href = `/profile/${userId}`;
        return;
      }
      if (actionBtn) {
        const action = actionBtn.dataset.action;
        const reelId = actionBtn.dataset.reelId;
        if (action === 'like') {
          if (actionBtn.dataset.liking === '1') return;
          actionBtn.dataset.liking = '1';
          handle(`/reels/${reelId}/like`, { method: 'POST' })
            .then((resp) => {
              const already = resp?.already_liked;
              if (!already) {
                triggerLike(card, true);
              } else {
                actionBtn.classList.add('active');
              }
            })
            .catch(() => triggerLike(card, true))
            .finally(() => { actionBtn.dataset.liking = '0'; });
        }
        if (action === 'share') {
          const shareUrl = `${window.location.origin}/reels/${reelId}`;
          handle(`/reels/${reelId}/share`, { method: 'POST' })
            .then((resp) => {
              actionBtn.classList.add('active');
              if (resp && resp.share_count !== undefined) {
                actionBtn.dataset.shareCount = resp.share_count;
              }
            })
            .catch(() => { actionBtn.classList.add('active'); });

          if (navigator.share) {
            navigator.share({ url: shareUrl }).catch(() => {});
          } else {
            window.open(shareUrl, '_blank', 'noopener');
            if (navigator.clipboard?.writeText) {
              navigator.clipboard.writeText(shareUrl).catch(() => {});
            }
          }
        }
        if (action === 'share-dm') {
          openShareDmModal({ type: 'reel', id: reelId });
        }
        if (action === 'comment' && commentModal) {
          commentSubmit.dataset.reelId = reelId;
          loadComments(reelId);
          commentModal.show();
        }
        if (action === 'save') {
          if (actionBtn.dataset.saving === '1') return;
          actionBtn.dataset.saving = '1';
          handle(`/reels/${reelId}/save`, { method: 'POST' })
            .then((resp) => {
              const saved = !!resp?.saved;
              actionBtn.classList.toggle('active', saved);
            })
            .catch(() => {
              actionBtn.classList.toggle('active');
            })
            .finally(() => { actionBtn.dataset.saving = '0'; });
        }
        if (action === 'mute') {
          const video = card.querySelector('video');
          if (video) {
            video.muted = !video.muted;
            const muteIcon = actionBtn.querySelector('[data-role="mute-icon"]');
            if (muteIcon) {
              muteIcon.classList.toggle('bi-volume-mute-fill', video.muted);
              muteIcon.classList.toggle('bi-volume-up-fill', !video.muted);
            } else {
              actionBtn.textContent = video.muted ? '🔇' : '🔊';
            }
          }
        }
      }
    });

    reelViewport.addEventListener('dblclick', (e) => {
      const card = e.target.closest('.reel-item');
      if (card) triggerLike(card, true);
    });

    if (!cards().length) {
      fetchMore();
    } else {
      setTimeout(() => activate(cards()[0] || null), 50);
    }
  }

  // Explore infinite scroll
  const exploreLoadMore = document.getElementById('explore-load-more');
  if (exploreLoadMore) {
    exploreLoadMore.addEventListener('click', async () => {
      const offset = parseInt(exploreLoadMore.dataset.offset || '0', 10);
      const resp = await handle(`/explore/more?offset=${offset}`);
      if (resp.html) {
        document.getElementById('explore-grid').insertAdjacentHTML('beforeend', resp.html);
        exploreLoadMore.dataset.offset = resp.next_offset || offset + 12;
      }
    });
  }

  // Search autocomplete
  const searchTerm = document.getElementById('search-term');
  const autocompleteList = document.getElementById('autocomplete-results');
  let autocompleteTimer;
  if (searchTerm && autocompleteList) {
    searchTerm.addEventListener('input', () => {
      const term = searchTerm.value.trim();
      clearTimeout(autocompleteTimer);
      if (term.length < 2) {
        autocompleteList.innerHTML = '';
        return;
      }
      autocompleteTimer = setTimeout(async () => {
        const res = await handle(`/explore/autocomplete?q=${encodeURIComponent(term)}`);
        autocompleteList.innerHTML = '';
        (res.suggestions || []).forEach((s) => {
          const suggestion = typeof s === 'string' ? { label: s } : s || {};
          if (!suggestion.label) return;
          const li = document.createElement('li');
          li.className = 'list-group-item bg-transparent p-0';
          const wrapper = document.createElement(suggestion.href ? 'a' : 'div');
          wrapper.className = 'd-block text-reset text-decoration-none py-2';
          if (suggestion.href) wrapper.href = suggestion.href;

          const title = document.createElement('div');
          title.className = 'fw-semibold';
          title.textContent = suggestion.label;
          wrapper.appendChild(title);

          const metaParts = [];
          if (suggestion.type) metaParts.push(String(suggestion.type).toUpperCase());
          if (suggestion.secondary) metaParts.push(suggestion.secondary);
          if (metaParts.length) {
            const meta = document.createElement('div');
            meta.className = 'text-muted small';
            meta.textContent = metaParts.join(' • ');
            wrapper.appendChild(meta);
          }

          li.appendChild(wrapper);
          autocompleteList.appendChild(li);
        });
      }, 180);
    });
  }
});
