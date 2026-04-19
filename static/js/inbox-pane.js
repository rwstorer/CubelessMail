document.addEventListener('DOMContentLoaded', function () {
  const MOBILE_BREAKPOINT = 768;
  const LIST_PANE_MIN_WIDTH = 180;
  const DETAIL_PANE_MIN_WIDTH = 200;
  const STORAGE_KEY = 'cubelessmailListPaneWidth';

  const listPane = document.getElementById('inboxListPane');
  const detailPane = document.getElementById('inboxDetailPane');
  const resizer = document.getElementById('inboxPaneResizer');

  if (!listPane || !detailPane) {
    return;
  }

  // Restore saved list pane width
  const savedWidth = localStorage.getItem(STORAGE_KEY);
  if (savedWidth && window.innerWidth >= MOBILE_BREAKPOINT) {
    listPane.style.flex = '0 0 ' + savedWidth + 'px';
  }

  // Horizontal pane resizing
  if (resizer) {
    let isResizing = false;
    let startX = 0;
    let startWidth = 0;

    resizer.addEventListener('pointerdown', function (event) {
      if (window.innerWidth < MOBILE_BREAKPOINT) {
        return;
      }
      isResizing = true;
      startX = event.clientX;
      startWidth = listPane.getBoundingClientRect().width;
      resizer.classList.add('resizing');
      document.body.style.cursor = 'ew-resize';
      document.body.style.userSelect = 'none';
      window.addEventListener('pointermove', handlePointerMove);
      window.addEventListener('pointerup', stopResizing);
    });

    function handlePointerMove(event) {
      if (!isResizing) { return; }
      const containerWidth = listPane.parentElement.getBoundingClientRect().width;
      const resizerWidth = resizer.getBoundingClientRect().width;
      const maxWidth = containerWidth - resizerWidth - DETAIL_PANE_MIN_WIDTH;
      const delta = event.clientX - startX;
      const newWidth = Math.min(maxWidth, Math.max(LIST_PANE_MIN_WIDTH, startWidth + delta));
      listPane.style.flex = '0 0 ' + newWidth + 'px';
    }

    function stopResizing() {
      if (!isResizing) { return; }
      isResizing = false;
      resizer.classList.remove('resizing');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      const finalWidth = listPane.getBoundingClientRect().width;
      localStorage.setItem(STORAGE_KEY, Math.round(finalWidth));
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', stopResizing);
    }
  }

  let activeUid = null;
  let activeController = null;

  function clearSelection() {
    activeUid = null;
    listPane.querySelectorAll('.message-item').forEach(function (el) {
      el.classList.remove('selected');
    });
  }

  function getActiveRow() {
    if (!activeUid) {
      return null;
    }
    return listPane.querySelector('[data-uid="' + CSS.escape(String(activeUid)) + '"]');
  }

  function removeUnreadDot(row) {
    if (!row) {
      return;
    }
    const dot = row.querySelector('.message-unread-dot');
    if (dot) {
      dot.remove();
    }
  }

  function ensureUnreadDot(row) {
    if (!row) {
      return;
    }
    const sender = row.querySelector('.message-sender');
    if (!sender || sender.querySelector('.message-unread-dot')) {
      return;
    }
    const dot = document.createElement('span');
    dot.className = 'message-unread-dot';
    dot.setAttribute('aria-label', 'Unread');
    dot.setAttribute('title', 'Unread');
    sender.insertBefore(dot, sender.firstChild);
  }

  function removeStarMarker(row) {
    if (!row) {
      return;
    }
    const star = row.querySelector('.message-starred-marker');
    if (star) {
      star.remove();
    }
  }

  function ensureStarMarker(row) {
    if (!row) {
      return;
    }
    const sender = row.querySelector('.message-sender');
    if (!sender || sender.querySelector('.message-starred-marker')) {
      return;
    }
    const star = document.createElement('span');
    star.className = 'message-starred-marker';
    star.setAttribute('aria-label', 'Starred');
    star.setAttribute('title', 'Starred');
    star.innerHTML = '&#9733;';
    sender.appendChild(star);
  }

  // Intercept message row clicks on desktop/tablet
  listPane.addEventListener('click', function (event) {
    if (window.innerWidth < MOBILE_BREAKPOINT) {
      return; // Let normal navigation handle mobile
    }

    const item = event.target.closest('.message-item[data-fragment-url]');
    if (!item) {
      return;
    }

    event.preventDefault();

    const uid = item.dataset.uid;
    if (uid === activeUid) {
      return; // Already loaded
    }

    activeUid = uid;
    selectItem(item);
    loadFragment(item.dataset.fragmentUrl);
  });

  // Intercept pane-internal links with data-fragment-url (e.g. "Load remote images")
  detailPane.addEventListener('click', function (event) {
    if (window.innerWidth < MOBILE_BREAKPOINT) {
      return;
    }

    // Cancel button for the compose pane.
    if (event.target.closest('.js-compose-cancel')) {
      event.preventDefault();
      activeUid = null;
      detailPane.innerHTML = '<div class="detail-pane-empty"><p class="text-muted">Select a message to read it</p></div>';
      return;
    }

    const link = event.target.closest('[data-fragment-url]');
    if (!link) {
      return;
    }

    event.preventDefault();
    loadFragment(link.dataset.fragmentUrl);
  });

  // Intercept compose trigger links on desktop and load into the detail pane.
  // Only match interactive elements (a, button) — not form containers that carry the
  // attribute only to expose the URL for post-send "compose another" wiring.
  document.addEventListener('click', function (event) {
    const composeTrigger = event.target.closest('[data-compose-fragment-url]');
    if (!composeTrigger) {
      return;
    }

    const tag = composeTrigger.tagName;
    if (tag !== 'A' && tag !== 'BUTTON') {
      return;
    }

    if (window.innerWidth < MOBILE_BREAKPOINT) {
      // Allow normal navigation to full compose page on mobile.
      return;
    }

    event.preventDefault();
    clearSelection();
    loadFragment(composeTrigger.dataset.composeFragmentUrl);
  });

  // Keep compose form submission in the detail pane on desktop/tablet.
  detailPane.addEventListener('submit', function (event) {
    if (window.innerWidth < MOBILE_BREAKPOINT) {
      return;
    }

    const form = event.target.closest('form.js-compose-form');
    if (!form) {
      return;
    }

    event.preventDefault();

    const submitButton = form.querySelector('button[type="submit"]');
    const errorsBox = form.querySelector('.compose-errors');
    const composeFragmentUrl = form.dataset.composeFragmentUrl || '/compose/fragment/';

    if (errorsBox) {
      errorsBox.style.display = 'none';
      errorsBox.innerHTML = '';
    }

    if (submitButton) {
      submitButton.disabled = true;
    }

    if (window.CubelessCompose && typeof window.CubelessCompose.syncForm === 'function') {
      window.CubelessCompose.syncForm(form);
    }

    const syncedFormData = new FormData(form);

    fetch(form.action, {
      method: 'POST',
      body: syncedFormData,
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return {
            ok: response.ok,
            status: response.status,
            data: data
          };
        }).catch(function () {
          return {
            ok: false,
            status: response.status,
            data: { ok: false, errors: { send: ['Unexpected server response.'] } }
          };
        });
      })
      .then(function (result) {
        if (result.ok && result.data && result.data.ok) {
          detailPane.innerHTML = '<div class="detail-pane-status"><p class="text-muted">Email sent successfully.</p><p><a href="#" data-compose-fragment-url="' + composeFragmentUrl + '">Compose another message</a></p></div>';
          return;
        }

        const errors = (result.data && result.data.errors) || { send: ['Unable to send email.'] };
        const messages = [];

        Object.keys(errors).forEach(function (key) {
          const value = errors[key];
          if (Array.isArray(value)) {
            value.forEach(function (entry) {
              messages.push(String(entry));
            });
          } else if (value) {
            messages.push(String(value));
          }
        });

        if (!messages.length) {
          messages.push('Unable to send email.');
        }

        if (errorsBox) {
          errorsBox.style.display = 'block';
          errorsBox.style.marginBottom = '1rem';
          errorsBox.style.padding = '0.75rem';
          errorsBox.style.border = '1px solid var(--border-color)';
          errorsBox.style.borderRadius = '8px';
          errorsBox.style.background = 'var(--hover-bg)';
          errorsBox.innerHTML = messages.map(function (msg) {
            return '<p class="text-small text-muted" style="margin: 0 0 0.35rem 0;">' + msg + '</p>';
          }).join('');
        }
      })
      .catch(function () {
        showError();
      })
      .finally(function () {
        if (submitButton) {
          submitButton.disabled = false;
        }
      });
  }, true);

  // Keep message actions inside the detail pane on desktop/tablet.
  detailPane.addEventListener('submit', function (event) {
    if (window.innerWidth < MOBILE_BREAKPOINT) {
      return;
    }

    const form = event.target.closest('form.js-pane-action-form');
    if (!form) {
      return;
    }

    // Ignore empty move submissions.
    const moveSelect = form.querySelector('select[name="to_folder"]');
    if (moveSelect && !moveSelect.value) {
      event.preventDefault();
      return;
    }

    event.preventDefault();

    const actionMode = form.dataset.paneAction || 'stay';
    const formData = new FormData(form);
    if (actionMode === 'stay') {
      formData.set('next', 'fragment');
    } else if (actionMode === 'mark-unread') {
      formData.set('next', 'mark-unread');
    } else if (actionMode === 'toggle-flag') {
      formData.set('next', 'toggle');
    } else {
      formData.set('next', 'pane');
    }

    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
    }

    if (actionMode !== 'toggle-flag' && actionMode !== 'mark-unread') {
      showLoading();
    }

    fetch(form.action, {
      method: 'POST',
      body: formData,
      headers: {
        'X-Requested-With': 'XMLHttpRequest'
      }
    })
      .then(function (response) {
        if (actionMode === 'remove' && response.status === 204) {
          const toolbarUid = detailPane.querySelector('.message-actions-toolbar')?.dataset.uid || null;
          const uidToRemove = activeUid || toolbarUid;
          const selected = uidToRemove
            ? listPane.querySelector('[data-uid="' + CSS.escape(String(uidToRemove)) + '"]')
            : null;
          if (selected) {
            selected.remove();
          }
          activeUid = null;
          detailPane.innerHTML = '<div class="detail-pane-empty"><p class="text-muted">Select a message to read it</p></div>';
          return null;
        }
        if (!response.ok) {
          throw new Error('Bad response: ' + response.status);
        }
        if (actionMode === 'toggle-flag' || actionMode === 'mark-unread') {
          return response.json();
        }
        return response.text();
      })
      .then(function (payload) {
        if (payload === null) {
          return;
        }

        if (actionMode === 'toggle-flag') {
          const flagged = Boolean(payload.flagged);
          const activeRow = getActiveRow();
          const flaggedInput = form.querySelector('input[name="flagged"]');
          if (flaggedInput) {
            flaggedInput.value = flagged ? '0' : '1';
          }
          if (submitButton) {
            submitButton.classList.toggle('msg-action-btn--active', flagged);
            submitButton.innerHTML = flagged ? '&#9733; Flagged' : '&#9734; Flag';
            submitButton.title = flagged ? 'Remove flag' : 'Flag message';
          }

          if (flagged) {
            ensureStarMarker(activeRow);
          } else {
            removeStarMarker(activeRow);
          }

          // In the Starred virtual folder, unflagged messages should disappear immediately.
          if (!flagged && window.location.pathname.indexOf('/starred/') !== -1) {
            const selected = activeRow;
            if (selected) {
              selected.remove();
            }
            activeUid = null;
            detailPane.innerHTML = '<div class="detail-pane-empty"><p class="text-muted">Select a message to read it</p></div>';
          }

          return;
        }

        if (actionMode === 'mark-unread') {
          const readFilter = document.getElementById('readFilter');
          if (readFilter && readFilter.value === 'read') {
            const selected = getActiveRow();
            if (selected) {
              selected.remove();
            }
            activeUid = null;
            detailPane.innerHTML = '<div class="detail-pane-empty"><p class="text-muted">Select a message to read it</p></div>';
          } else {
            ensureUnreadDot(getActiveRow());
          }
          return;
        }

        detailPane.innerHTML = payload;
      })
      .catch(function () {
        showError();
      })
      .finally(function () {
        if (submitButton) {
          submitButton.disabled = false;
        }
      });
  }, true);

  function selectItem(item) {
    clearSelection();
    item.classList.add('selected');
  }

  function loadFragment(url) {
    if (activeController) {
      activeController.abort();
    }
    activeController = new AbortController();

    showLoading();

    fetch(url, { signal: activeController.signal })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Bad response: ' + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        detailPane.innerHTML = html;
        if (window.CubelessCompose && typeof window.CubelessCompose.initWithin === 'function') {
          window.CubelessCompose.initWithin(detailPane);
        }
        activeController = null;
        // Opening a message marks it read server-side; mirror that immediately in the row indicator.
        removeUnreadDot(getActiveRow());
      })
      .catch(function (error) {
        if (error.name === 'AbortError') {
          return;
        }
        showError();
      });
  }

  function showLoading() {
    detailPane.innerHTML = '<div class="detail-pane-status"><span class="text-muted">Loading\u2026</span></div>';
  }

  function showError() {
    const container = document.createElement('div');
    container.className = 'detail-pane-status';

    const p = document.createElement('p');
    p.className = 'text-muted';
    p.textContent = 'Failed to load message. ';

    const fallbackElem = activeUid
      ? listPane.querySelector('[data-uid="' + CSS.escape(String(activeUid)) + '"]')
      : null;

    if (fallbackElem) {
      const a = document.createElement('a');
      a.setAttribute('href', fallbackElem.href);
      a.textContent = 'Open full page';
      p.appendChild(a);
    }

    container.appendChild(p);
    detailPane.innerHTML = '';
    detailPane.appendChild(container);
  }
});
