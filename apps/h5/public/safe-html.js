(function installSafeHtml(global) {
  'use strict';

  const blockedTags = new Set([
    'ANIMATE',
    'ANIMATEMOTION',
    'ANIMATETRANSFORM',
    'BASE',
    'DISCARD',
    'EMBED',
    'FOREIGNOBJECT',
    'IFRAME',
    'LINK',
    'MATH',
    'META',
    'OBJECT',
    'SCRIPT',
    'SET',
    'STYLE',
    'TEMPLATE',
    'USE',
  ]);
  const urlAttributes = new Set(['action', 'formaction', 'href', 'src', 'xlink:href']);
  const safeProtocols = new Set(['http:', 'https:', 'mailto:', 'tel:']);
  const dangerousStyle = /(?:expression\s*\(|url\s*\(|@import|-moz-binding|javascript\s*:)/i;

  function isSafeUrl(value) {
    const candidate = String(value || '').trim();
    if (!candidate || candidate.startsWith('#') || candidate.startsWith('/') || candidate.startsWith('./') || candidate.startsWith('../') || candidate.startsWith('?')) {
      return true;
    }
    try {
      return safeProtocols.has(new URL(candidate, document.baseURI).protocol);
    } catch (_error) {
      return false;
    }
  }

  function sanitizeTree(root) {
    for (const element of [...root.querySelectorAll('*')]) {
      if (blockedTags.has(element.localName.toUpperCase())) {
        element.remove();
        continue;
      }
      for (const attribute of [...element.attributes]) {
        const name = attribute.name.toLowerCase();
        if (
          name.startsWith('on') ||
          name === 'srcdoc' ||
          name === 'srcset' ||
          (name === 'style' && dangerousStyle.test(attribute.value)) ||
          (urlAttributes.has(name) && !isSafeUrl(attribute.value))
        ) {
          element.removeAttribute(attribute.name);
        }
      }
      if (element.getAttribute('target') === '_blank') {
        element.setAttribute('rel', 'noopener noreferrer');
      }
    }
  }

  function safeFragment(html) {
    const parsed = new DOMParser().parseFromString(String(html ?? ''), 'text/html');
    sanitizeTree(parsed.body);
    const fragment = document.createDocumentFragment();
    while (parsed.body.firstChild) {
      fragment.appendChild(parsed.body.firstChild);
    }
    return fragment;
  }

  function requireElement(target, helperName) {
    if (!(target instanceof Element)) {
      throw new TypeError(`${helperName} target must be an Element`);
    }
  }

  global.zsSetSafeHtml = function zsSetSafeHtml(target, html) {
    requireElement(target, 'zsSetSafeHtml');
    const fragment = safeFragment(html);
    target.replaceChildren(fragment);
  };

  global.zsReplaceWithSafeHtml = function zsReplaceWithSafeHtml(target, html) {
    requireElement(target, 'zsReplaceWithSafeHtml');
    target.replaceWith(safeFragment(html));
  };

  document.addEventListener('click', (event) => {
    const trigger = event.target instanceof Element ? event.target.closest('[data-history-back]') : null;
    if (trigger) {
      event.preventDefault();
      history.back();
    }
  });
})(window);
