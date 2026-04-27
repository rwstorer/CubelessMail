const themeToggle = document.getElementById('themeToggle');
const savedTheme = localStorage.getItem('docsTheme');
if (savedTheme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    themeToggle.textContent = '☀️';
}

themeToggle.addEventListener('click', function () {
    const current = document.documentElement.getAttribute('data-theme');
    if (current === 'dark') {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('docsTheme', 'light');
        themeToggle.textContent = '🌙';
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('docsTheme', 'dark');
        themeToggle.textContent = '☀️';
    }
});

// Mock message data
const messages = [
    {
        id: 1,
        sender: "Owner",
        flagged: true,
        subject: "Features",
        preview: "CubelessMail is my attempt to create a Python, Django, CSS3 version of RoundCube....",
        body: "<h1>CubelessMail</h1>\n<h2>Introduction</h2>\n<p>CubelessMail is my attempt to create a Python, Django, Tailwind version of RoundCube.</p>\n<h2>Project Goals</h2>\n<ul>\n  <li>Modern web user interface<ul>\n<li>threaded emails (maybe)</li>\n<li>right-click actions (maybe)</li>\n<li>end users choose color scheme (maybe)</li>\n</ul>\n</li>\n<li>IMAPS only</li>\n<li>SMTP (secure only)\n<ul>\n<li>Implicit TLS (SMTPS)</li>\n<li>STARTTLS</li>\n</ul>\n</li>\n<li>CALDAV calendar (eventually)</li>\n<li>Contact management (eventually)</li>\n</ul>",
        from: "owner@company.com",
        date: "Apr 14, 10:32 AM",
        unread: true
    },
    {
        id: 2,
        sender: "Someone",
        flagged: false,
        subject: "Code review: Feature branch",
        preview: "Thanks for submitting the PR. I've left some comments on the implementation. Overall looking good!",
        body: "Thanks for submitting the PR!\n\nI've reviewed your feature branch and left some comments. Overall the implementation looks solid. A few suggestions:\n\n1. Consider extracting the validation logic into a separate function\n2. Add unit tests for edge cases\n3. Update the documentation\n\nGreat work! Let me know if you have questions.\n\nCheers,\nSomeone",
        from: "someone@company.com",
        date: "Apr 14, 9:15 AM",
        unread: true
    },
    {
        id: 3,
        sender: "Design Team",
        flagged: true,
        subject: "Updated mockups for dashboard redesign",
        preview: "Check out the latest iteration of the dashboard UI. We've incorporated your feedback and made some refinements...",
        body: "Hi everyone,\n\nPlease review the updated mockups in Figma. We've incorporated feedback from the last review and made several refinements:\n\n- Improved navigation hierarchy\n- Better color contrast for accessibility\n- Refined typography scale\n\nPlease leave comments directly in Figma.\n\nThanks!",
        from: "design@company.com",
        date: "Apr 13, 4:22 PM",
        unread: true
    },
    {
        id: 4,
        sender: "Quarterly Reports",
        flagged: false,
        subject: "Q1 2026 performance review reminder",
        preview: "Reminder: Please complete your Q1 2026 performance review by Friday. Access the portal here...",
        body: "This is a reminder to complete your Q1 2026 performance review by Friday, April 18.\n\nPlease log into the employee portal to submit your self-assessment.\n\nIf you need assistance, contact HR@company.com.",
        from: "hr@company.com",
        date: "Apr 13, 2:00 PM",
        unread: false
    },
    {
        id: 5,
        sender: "Notifications",
        flagged: false,
        subject: "GitHub: Your pull request was merged",
        preview: "Your pull request #1247 'Add dark mode support' has been merged to main.",
        body: "Great news!\n\nYour pull request #1247 'Add dark mode support' was approved and merged to main by @reviewer.\n\nThank you for your contribution!",
        from: "noreply@github.com",
        date: "Apr 12, 6:45 PM",
        unread: false
    }
];

const appState = {
    selectedMessageId: null,
    activeFolder: 'inbox',
    composeQuill: null
};

function normalizeHtml(html) {
    if (!html) {
        return '';
    }
    const trimmed = String(html).trim();
    if (trimmed === '<p><br></p>') {
        return '';
    }
    return trimmed;
}

function syncComposeBody() {
    const plainInput = document.getElementById('composeBody');
    const htmlInput = document.getElementById('composeBodyHtml');

    if (!plainInput || !htmlInput) {
        return;
    }

    if (!appState.composeQuill) {
        htmlInput.value = '';
        return;
    }

    const html = normalizeHtml(appState.composeQuill.root.innerHTML);
    const text = appState.composeQuill.getText().replace(/\s+$/g, '');

    plainInput.value = text;
    htmlInput.value = html;
}

function initComposeEditor() {
    appState.composeQuill = null;

    const editorHost = document.getElementById('composeEditor');
    const plainInput = document.getElementById('composeBody');
    const htmlInput = document.getElementById('composeBodyHtml');

    if (!editorHost || !plainInput || !htmlInput) {
        return;
    }

    if (typeof window.Quill !== 'function') {
        return;
    }

    editorHost.style.display = 'block';

    const quill = new window.Quill(editorHost, {
        theme: 'snow',
        modules: {
            toolbar: [
                [{ header: [1, 2, 3, false] }],
                ['bold', 'italic', 'underline', 'strike'],
                [{ list: 'ordered' }, { list: 'bullet' }],
                [{ indent: '-1' }, { indent: '+1' }],
                ['link', 'blockquote', 'code-block'],
                ['clean']
            ]
        },
        placeholder: 'Write your message...'
    });

    if (plainInput.value) {
        quill.setText(plainInput.value);
    }

    plainInput.style.display = 'none';
    appState.composeQuill = quill;

    quill.on('text-change', function () {
        syncComposeBody();
    });

    syncComposeBody();
}

function parseDemoDate(value) {
    return new Date('2026 ' + value.replace(',', ''));
}

function getFilterState() {
    const query = (document.getElementById('searchQuery').value || '').trim().toLowerCase();
    const scope = document.getElementById('searchScope').value;
    const readFilter = document.getElementById('readFilter').value;
    const sortBy = document.getElementById('sortBy').value;

    return { query, scope, readFilter, sortBy };
}

function getFilteredMessages() {
    const { query, scope, readFilter, sortBy } = getFilterState();

    let result = messages.slice();

    if (query) {
        result = result.filter(msg => {
            const headers = `${msg.subject} ${msg.sender} ${msg.from}`.toLowerCase();
            const fullText = `${headers} ${msg.preview} ${msg.body}`.toLowerCase();
            return scope === 'text' ? fullText.includes(query) : headers.includes(query);
        });
    }

    if (readFilter === 'unread') {
        result = result.filter(msg => msg.unread);
    } else if (readFilter === 'read') {
        result = result.filter(msg => !msg.unread);
    }

    if (sortBy === 'from_asc' || sortBy === 'from_desc') {
        const dir = sortBy === 'from_desc' ? -1 : 1;
        result.sort((a, b) => a.sender.localeCompare(b.sender) * dir);
    } else {
        const dir = sortBy === 'date_asc' ? 1 : -1;
        result.sort((a, b) => (parseDemoDate(a.date) - parseDemoDate(b.date)) * dir);
    }

    return result;
}

function setFolderActive(folder) {
    appState.activeFolder = folder;
    document.querySelectorAll('.folder-item').forEach((item) => {
        item.classList.toggle('active', item.dataset.folder === folder);
    });
}

function setComposeActive(active) {
    const composeTrigger = document.getElementById('composeTrigger');
    composeTrigger.classList.toggle('active', active);
}

function showInboxPane() {
    const pane = document.querySelector('.message-list-pane');
    pane.classList.remove('is-hidden');
}

function showFolderPlaceholder(folderName) {
    const detail = document.getElementById('detailPane');
    detail.replaceChildren();

    const empty = document.createElement('div');
    empty.className = 'detail-empty';
    empty.textContent = `${folderName} is shown in the full app. This docs demo highlights Inbox + Compose behavior.`;

    detail.appendChild(empty);
}

function renderComposePane() {
    appState.composeQuill = null;
    const detail = document.getElementById('detailPane');
    detail.innerHTML = `
        <div class="compose-fragment">
            <h2>Compose</h2>
            <p class="text-small text-muted">From: owner@company.com</p>

            <form id="demoComposeForm" class="compose-form">
                <div id="composeStatus" class="compose-status success" style="display:none;" role="status" aria-live="polite"></div>

                <div class="form-group">
                    <label for="composeTo">To</label>
                    <input id="composeTo" class="compose-input" type="text" required placeholder="someone@example.com">
                </div>

                <div class="form-group">
                    <label for="composeCc">Cc</label>
                    <input id="composeCc" class="compose-input" type="text" placeholder="">
                </div>

                <div class="form-group">
                    <label for="composeBcc">Bcc</label>
                    <input id="composeBcc" class="compose-input" type="text" placeholder="">
                </div>

                <div class="form-group">
                    <label for="composeSubject">Subject</label>
                    <input id="composeSubject" class="compose-input" type="text" maxlength="255" placeholder="Subject">
                </div>

                <div class="form-group">
                    <label for="composeBody">Message</label>
                    <div id="composeEditor" class="compose-rich-editor" style="display:none;"></div>
                    <textarea id="composeBody" class="compose-textarea" rows="10" placeholder="Write your message..." required></textarea>
                    <input id="composeBodyHtml" type="hidden" value="">
                    <p class="text-small text-muted">Rich formatting is enabled when the editor loads. Fallback is plain text.</p>
                </div>

                <div class="form-group">
                    <label for="composeAttachments">Attachments</label>
                    <input id="composeAttachments" class="compose-file-input" type="file" multiple>
                    <p class="text-small text-muted">Demo only. Files are not uploaded from this page.</p>
                </div>

                <div class="message-actions-toolbar" style="margin-top: 1rem; padding-left: 0;">
                    <button type="submit" class="msg-action-btn msg-action-btn--active">Send</button>
                    <button type="button" id="composeCancel" class="msg-action-btn">Cancel</button>
                </div>
            </form>
        </div>
    `;
}

function openComposeView() {
    setComposeActive(true);
    setFolderActive('inbox');
    showInboxPane();
    document.querySelectorAll('.message-item').forEach((el) => {
        el.classList.remove('selected');
    });
    renderComposePane();
    initComposeEditor();
}

// Render message list
function renderMessageList() {
    const list = document.getElementById('messageList');
    const searchActive = document.getElementById('searchActive');
    const { query, scope } = getFilterState();
    const filtered = getFilteredMessages();
    const meta = document.getElementById('messageListMeta');
    meta.textContent = `owner@company.com • ${filtered.length} message${filtered.length === 1 ? '' : 's'}`;

    if (query) {
        const inLabel = scope === 'text' ? 'all fields' : 'subject & from';
        searchActive.hidden = false;
        searchActive.innerHTML = '';

        searchActive.appendChild(document.createTextNode('Searching '));

        const em = document.createElement('em');
        em.textContent = inLabel;
        searchActive.appendChild(em);

        searchActive.appendChild(document.createTextNode(' for '));

        const strong = document.createElement('strong');
        strong.textContent = query;
        searchActive.appendChild(strong);

        searchActive.appendChild(document.createTextNode(' — '));

        const clearLink = document.createElement('a');
        clearLink.href = '#';
        clearLink.textContent = 'Clear';
        clearLink.addEventListener('click', function (event) {
            event.preventDefault();
            clearSearchQuery();
        });
        searchActive.appendChild(clearLink);
    } else {
        searchActive.hidden = true;
        searchActive.innerHTML = '';
    }

    if (!filtered.length) {
        const emptyText = query ? 'No results found.' : 'No messages in INBOX';
        list.innerHTML = `<p class="text-muted" style="padding: 1rem;">${emptyText}</p>`;
        return;
    }

    list.innerHTML = filtered.map(msg => `
        <div class="message-item" onclick="selectMessage(${msg.id}, this)">
            <div class="message-item-header">
                <div class="message-item-sender">
                    ${msg.unread ? '<span class="message-unread-dot" aria-label="Unread" title="Unread"></span>' : ''}
                    <span>${msg.sender}</span>
                    ${msg.flagged ? '<span class="message-starred-marker" aria-label="Starred" title="Starred">&#9733;</span>' : ''}
                </div>
                <div class="message-item-time">${msg.date}</div>
            </div>
            <div class="message-item-subject">${msg.subject}</div>
            <div class="message-item-preview">${msg.preview}</div>
        </div>
    `).join('');
}

function clearSearchQuery() {
    document.getElementById('searchQuery').value = '';
    renderMessageList();
}

// Show detail pane
function selectMessage(id, element) {
    const msg = messages.find(m => m.id === id);
    if (!msg) return;
    appState.selectedMessageId = id;
    setComposeActive(false);
    setFolderActive('inbox');
    showInboxPane();

    const detail = document.getElementById('detailPane');
    detail.innerHTML = `
        <div class="message-actions-toolbar">
            <div class="msg-action-group">
                <form>
                    <button type="button" class="msg-action-btn" title="Reply">Reply</button>
                </form>
                <form>
                    <button type="button" class="msg-action-btn" title="Forward">Forward</button>
                </form>
                <form>
                    <button type="button" class="msg-action-btn" title="Mark as unread">Mark unread</button>
                </form>
                <form>
                    <button type="button" class="msg-action-btn ${msg.flagged ? 'msg-action-btn--active' : ''}" title="${msg.flagged ? 'Remove flag' : 'Flag message'}">${msg.flagged ? '&#9733; Flagged' : '&#9734; Flag'}</button>
                </form>
            </div>
            <div class="msg-action-group msg-action-group--right">
                <form>
                    <button type="button" class="msg-action-btn" title="Archive">&#128451; Archive</button>
                </form>
                <form>
                    <button type="button" class="msg-action-btn msg-action-btn--destructive" title="Delete">&#128465; Delete</button>
                </form>
            </div>
        </div>
        <div class="detail-content">
            <div class="detail-header">
                <div class="detail-subject">${msg.subject}</div>
                <div class="detail-meta">
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">From</div>
                        <div>${msg.sender} &lt;${msg.from}&gt;</div>
                    </div>
                    <div class="detail-meta-item">
                        <div class="detail-meta-label">Date</div>
                        <div>${msg.date}</div>
                    </div>
                </div>
            </div>
            <div class="detail-body">${msg.body}</div>
        </div>
    `;

    // Highlight selected message
    document.querySelectorAll('.message-item').forEach(el => {
        el.classList.remove('selected');
    });
    if (element) {
        element.classList.add('selected');
    }
}

document.getElementById('composeTrigger').addEventListener('click', function () {
    openComposeView();
});

document.querySelectorAll('.folder-item').forEach((item) => {
    item.addEventListener('click', function () {
        const folder = item.dataset.folder;
        setComposeActive(false);
        setFolderActive(folder);

        if (folder === 'inbox') {
            showInboxPane();
            if (appState.selectedMessageId) {
                const selectedEl = Array.from(document.querySelectorAll('.message-item')).find((el) => {
                    return el.getAttribute('onclick') === `selectMessage(${appState.selectedMessageId}, this)`;
                });
                selectMessage(appState.selectedMessageId, selectedEl || null);
            } else {
                document.getElementById('detailPane').innerHTML = '<div class="detail-empty">Select a message to read it</div>';
            }
            return;
        }

        showFolderPlaceholder(item.textContent.trim());
    });
});

document.getElementById('detailPane').addEventListener('submit', function (event) {
    if (event.target.id !== 'demoComposeForm') {
        return;
    }

    event.preventDefault();
    syncComposeBody();

    const to = document.getElementById('composeTo').value.trim();
    const body = document.getElementById('composeBody').value.trim();
    if (!to || !body) {
        return;
    }

    const status = document.getElementById('composeStatus');
    status.style.display = 'block';
    status.textContent = 'Demo mode: message queued for sending in the production app.';
});

document.getElementById('detailPane').addEventListener('click', function (event) {
    if (event.target.id !== 'composeCancel') {
        return;
    }

    setComposeActive(false);
    setFolderActive('inbox');
    showInboxPane();

    if (appState.selectedMessageId) {
        const selectedEl = Array.from(document.querySelectorAll('.message-item')).find((el) => {
            return el.getAttribute('onclick') === `selectMessage(${appState.selectedMessageId}, this)`;
        });
        selectMessage(appState.selectedMessageId, selectedEl || null);
    } else {
        document.getElementById('detailPane').innerHTML = '<div class="detail-empty">Select a message to read it</div>';
    }
});

// Initial render
renderMessageList();

const demoFilterForm = document.getElementById('demoFilterForm');
demoFilterForm.addEventListener('submit', function (event) {
    event.preventDefault();
    renderMessageList();
});

document.getElementById('readFilter').addEventListener('change', renderMessageList);
document.getElementById('sortBy').addEventListener('change', renderMessageList);