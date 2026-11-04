import DOMPurify from 'dompurify';
import { marked } from 'marked';

/**
 * Everything a sender may produce. `FORBID_TAGS` and `FORBID_ATTR` restate the
 * allowlist so widening it takes two deliberate edits.
 */
const PURIFY_CONFIG = {
  ALLOWED_TAGS: [
    'p',
    'br',
    'strong',
    'b',
    'em',
    'i',
    'u',
    's',
    'del',
    'code',
    'pre',
    'blockquote',
    'ul',
    'ol',
    'li',
    'a',
    'span'
  ],
  ALLOWED_ATTR: ['href', 'title', 'style', 'target', 'rel'],
  ALLOWED_URI_REGEXP: /^(?:https?|mailto):/i,
  ALLOW_UNKNOWN_PROTOCOLS: false,
  ALLOW_DATA_ATTR: false,
  ALLOW_ARIA_ATTR: false,
  FORBID_TAGS: [
    'script',
    'style',
    'iframe',
    'object',
    'embed',
    'form',
    'input',
    'button',
    'textarea',
    'select',
    'option',
    'img',
    'svg',
    'math',
    'template',
    'link',
    'meta',
    'base'
  ],
  FORBID_ATTR: ['id', 'name', 'class'],
  KEEP_CONTENT: true,
  RETURN_TRUSTED_TYPE: false as const
};

/**
 * The only style declarations kept, with the values each may carry. A Map
 * rather than an object literal so `constructor` and `__proto__` cannot reach
 * the prototype chain.
 */
const STYLE_GRAMMARS = new Map<string, RegExp>([
  [
    'color',
    /^(?:#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})|[a-z]{3,20}|(?:rgb|rgba|hsl|hsla)\((?:[-0-9.,%\s/]|deg|rad|grad|turn)*\))$/i
  ],
  [
    'font-size',
    /^(?:0|(?:[0-9]|[1-4][0-9])(?:\.[0-9]+)?px|[0-4](?:\.[0-9]+)?(?:em|rem)|(?:[0-9]{1,2}|[12][0-9]{2}|300)(?:\.[0-9]+)?%|xx-small|x-small|small|medium|large|x-large|xx-large|smaller|larger)$/i
  ]
]);

function cleanStyle(value: string): string {
  return value
    .split(';')
    .map(declaration => {
      const colon = declaration.indexOf(':');
      if (colon < 0) {
        return '';
      }
      const property = declaration.slice(0, colon).trim().toLowerCase();
      const propertyValue = declaration.slice(colon + 1).trim();
      const grammar = STYLE_GRAMMARS.get(property);
      return grammar && grammar.test(propertyValue)
        ? `${property}: ${propertyValue}`
        : '';
    })
    .filter(Boolean)
    .join('; ');
}

DOMPurify.addHook('afterSanitizeAttributes', node => {
  if (node.nodeName === 'A') {
    const href = node.getAttribute('href') ?? '';
    if (!/^(?:https?|mailto):/i.test(href)) {
      node.removeAttribute('href');
      node.removeAttribute('target');
      node.removeAttribute('rel');
    } else {
      node.setAttribute('target', '_blank');
      node.setAttribute('rel', 'noopener noreferrer');
    }
  }

  const style = node.getAttribute('style');
  if (style !== null) {
    const cleaned = cleanStyle(style);
    if (cleaned) {
      node.setAttribute('style', cleaned);
    } else {
      node.removeAttribute('style');
    }
  }
});

/**
 * Visible characters a rendered message may show, matching the 140-character
 * truncation JupyterLab applies to messages it renders itself.
 */
const MESSAGE_LIMIT = 140;

// Bound the markdown source before parsing; the visible preview is 140 characters.
const MESSAGE_SOURCE_LIMIT = 4096;

// A newline cut avoids splitting an inline construct where a clean line
// boundary exists near the bound.
function messageSource(raw: string): string {
  if (raw.length <= MESSAGE_SOURCE_LIMIT) {
    return raw;
  }
  const newline = raw.lastIndexOf('\n', MESSAGE_SOURCE_LIMIT);
  const floor = MESSAGE_SOURCE_LIMIT - 1024;
  return raw.slice(0, newline >= floor ? newline : MESSAGE_SOURCE_LIMIT);
}

interface ITextBudget {
  left: number;
  cut: boolean;
  lastText: Text | null;
}

function clipChildren(parent: Node, budget: ITextBudget): void {
  for (const child of Array.from(parent.childNodes)) {
    if (budget.cut) {
      parent.removeChild(child);
      continue;
    }
    if (child.nodeType === Node.TEXT_NODE) {
      const text = child.nodeValue ?? '';
      // Marked puts newlines between block elements; the browser does not
      // display them, so they must not consume the budget.
      if (text.trim().length === 0) {
        continue;
      }
      const chars = Array.from(text);
      budget.lastText = child as Text;
      if (chars.length > budget.left) {
        (child as Text).nodeValue = chars.slice(0, budget.left).join('');
        budget.left = 0;
        budget.cut = true;
      } else {
        budget.left -= chars.length;
      }
      continue;
    }
    if (child.nodeName === 'BR') {
      if (budget.left > 0) {
        budget.left -= 1;
      } else {
        parent.removeChild(child);
        budget.cut = true;
      }
      continue;
    }
    clipChildren(child, budget);
  }
}

function truncateRenderedHtml(html: string): string {
  const template = document.createElement('template');
  template.innerHTML = html;
  const budget: ITextBudget = {
    left: MESSAGE_LIMIT,
    cut: false,
    lastText: null
  };
  clipChildren(template.content, budget);
  if (budget.cut) {
    if (budget.lastText) {
      budget.lastText.nodeValue = `${budget.lastText.nodeValue ?? ''}…`;
    } else {
      template.content.appendChild(document.createTextNode('…'));
    }
  }
  return template.innerHTML;
}

/**
 * Render a notification message as sanitised HTML.
 *
 * Markdown is parsed, sanitised, then clipped to the 140-character preview
 * budget. Sanitising first means truncation cannot create markup.
 */
export function renderNotificationHtml(raw: string): string {
  const html = marked.parse(messageSource(raw), {
    gfm: true,
    breaks: true,
    async: false
  });
  return truncateRenderedHtml(DOMPurify.sanitize(html, PURIFY_CONFIG));
}
