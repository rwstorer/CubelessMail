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

    const link = event.target.closest('[data-fragment-url]');
    if (!link) {
      return;
    }

    event.preventDefault();
    loadFragment(link.dataset.fragmentUrl);
  });

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
    } else if (actionMode === 'toggle-flag') {
      formData.set('next', 'toggle');
    } else {
      formData.set('next', 'pane');
    }

    const submitButton = form.querySelector('button[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
    }

    if (actionMode !== 'toggle-flag') {
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
          const selected = activeUid
            ? listPane.querySelector('[data-uid="' + CSS.escape(String(activeUid)) + '"]')
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
        if (actionMode === 'toggle-flag') {
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
          const flaggedInput = form.querySelector('input[name="flagged"]');
          if (flaggedInput) {
            flaggedInput.value = flagged ? '0' : '1';
          }
          if (submitButton) {
            submitButton.classList.toggle('msg-action-btn--active', flagged);
            submitButton.innerHTML = flagged ? '&#9733; Flagged' : '&#9734; Flag';
            submitButton.title = flagged ? 'Remove flag' : 'Flag message';
          }

          // In the Starred virtual folder, unflagged messages should disappear immediately.
          if (!flagged && window.location.pathname.indexOf('/starred/') !== -1) {
            const selected = activeUid
              ? listPane.querySelector('[data-uid="' + CSS.escape(String(activeUid)) + '"]')
              : null;
            if (selected) {
              selected.remove();
            }
            activeUid = null;
            detailPane.innerHTML = '<div class="detail-pane-empty"><p class="text-muted">Select a message to read it</p></div>';
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
    listPane.querySelectorAll('.message-item').forEach(function (el) {
      el.classList.remove('selected');
    });
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
        activeController = null;
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
