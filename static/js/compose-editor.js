(function () {
  function normalizeHtml(html) {
    if (!html) {
      return '';
    }
    var trimmed = String(html).trim();
    if (trimmed === '<p><br></p>') {
      return '';
    }
    return trimmed;
  }

  function syncForm(form) {
    if (!form) {
      return;
    }

    var editor = form._composeQuill || null;
    var plainInput = form.querySelector('.js-compose-plain');
    var htmlInput = form.querySelector('.js-html-body-input');

    if (!editor || !plainInput || !htmlInput) {
      return;
    }

    var html = normalizeHtml(editor.root.innerHTML);
    var text = editor.getText().replace(/\s+$/g, '');

    plainInput.value = text;
    htmlInput.value = html;
  }

  function initForm(form) {
    if (!form || form.dataset.quillReady === '1') {
      return;
    }

    form.dataset.quillReady = '1';

    var editorHost = form.querySelector('.js-compose-editor');
    var plainInput = form.querySelector('.js-compose-plain');
    var htmlInput = form.querySelector('.js-html-body-input');

    if (!editorHost || !plainInput || !htmlInput) {
      return;
    }

    if (typeof window.Quill !== 'function') {
      return;
    }

    editorHost.style.display = 'block';

    var quill = new window.Quill(editorHost, {
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

    var initialHtml = normalizeHtml(editorHost.dataset.initialHtml || htmlInput.value);
    if (initialHtml) {
      quill.clipboard.dangerouslyPasteHTML(initialHtml);
    } else if (plainInput.value) {
      quill.setText(plainInput.value);
    }

    plainInput.style.display = 'none';
    form._composeQuill = quill;

    quill.on('text-change', function () {
      syncForm(form);
    });

    form.addEventListener('submit', function () {
      syncForm(form);
    });

    syncForm(form);
  }

  function initWithin(root) {
    var scope = root || document;
    scope.querySelectorAll('form.js-compose-form').forEach(initForm);
  }

  window.CubelessCompose = {
    initWithin: initWithin,
    syncForm: syncForm
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initWithin(document);
    });
  } else {
    initWithin(document);
  }
})();
