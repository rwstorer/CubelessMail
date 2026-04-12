document.addEventListener('DOMContentLoaded', function () {
  const sidebar = document.getElementById('folderSidebar');
  const resizer = document.getElementById('sidebarResizer');
  const toggle = document.getElementById('sidebarToggle');
  const themeToggle = document.getElementById('themeToggle');
  const minWidth = 180;
  const maxWidth = 420;

  if (!sidebar || !resizer || !toggle) {
    return;
  }

  // Initialize sidebar state
  const storedWidth = localStorage.getItem('cubelessmailSidebarWidth');
  const storedCollapsed = localStorage.getItem('cubelessmailSidebarCollapsed');

  if (storedWidth) {
    sidebar.style.width = `${storedWidth}px`;
  }

  if (storedCollapsed === 'true') {
    sidebar.classList.add('collapsed');
    toggle.textContent = 'Show folders';
  }

  // Initialize theme
  const storedTheme = localStorage.getItem('cubelessmailTheme') || 'light';
  document.documentElement.setAttribute('data-theme', storedTheme);
  updateThemeButton(storedTheme);

  // Sidebar toggle
  toggle.addEventListener('click', function () {
    const isCollapsed = sidebar.classList.toggle('collapsed');
    toggle.textContent = isCollapsed ? 'Show folders' : 'Hide folders';
    localStorage.setItem('cubelessmailSidebarCollapsed', isCollapsed);
  });

  // Theme toggle
  if (themeToggle) {
    themeToggle.addEventListener('click', function () {
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
      const newTheme = currentTheme === 'light' ? 'dark' : 'light';

      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('cubelessmailTheme', newTheme);
      updateThemeButton(newTheme);
    });
  }

  function updateThemeButton(theme) {
    if (themeToggle) {
      themeToggle.textContent = theme === 'dark' ? '☀️' : '🌙';
      themeToggle.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
    }
  }

  // Sidebar resizing
  let isResizing = false;
  let startX = 0;
  let startWidth = 0;

  resizer.addEventListener('pointerdown', function (event) {
    if (sidebar.classList.contains('collapsed')) {
      return;
    }

    isResizing = true;
    startX = event.clientX;
    startWidth = sidebar.getBoundingClientRect().width;

    document.body.style.cursor = 'ew-resize';
    document.body.style.userSelect = 'none';

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', stopResizing);
  });

  function handlePointerMove(event) {
    if (!isResizing) {
      return;
    }

    const delta = event.clientX - startX;
    const newWidth = Math.min(maxWidth, Math.max(minWidth, startWidth + delta));
    sidebar.style.width = `${newWidth}px`;
  }

  function stopResizing() {
    if (!isResizing) {
      return;
    }

    isResizing = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';

    const width = sidebar.getBoundingClientRect().width;
    localStorage.setItem('cubelessmailSidebarWidth', Math.round(width));

    window.removeEventListener('pointermove', handlePointerMove);
    window.removeEventListener('pointerup', stopResizing);
  }
});
