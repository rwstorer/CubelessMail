document.addEventListener('DOMContentLoaded', function () {
  const MOBILE_BREAKPOINT = 768;

  const listPane = document.getElementById('inboxListPane');
  const detailPane = document.getElementById('inboxDetailPane');

  if (!listPane || !detailPane) {
    return;
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
