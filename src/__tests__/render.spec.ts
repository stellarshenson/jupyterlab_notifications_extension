import { renderNotificationHtml } from '../render';

function renderInto(raw: string): HTMLElement {
  const container = document.createElement('div');
  container.innerHTML = renderNotificationHtml(raw);
  return container;
}

function query<T extends Element>(container: HTMLElement, selector: string): T {
  const element = container.querySelector<T>(selector);
  if (element === null) {
    throw new Error(`expected ${selector} in rendered output`);
  }
  return element;
}

function attributeNames(container: HTMLElement): string[] {
  const names: string[] = [];
  for (const element of Array.from(container.querySelectorAll('*'))) {
    for (const attribute of Array.from(element.attributes)) {
      names.push(attribute.name.toLowerCase());
    }
  }
  return names;
}

function expectNoEventHandlers(container: HTMLElement): void {
  for (const name of attributeNames(container)) {
    expect(name.startsWith('on')).toBe(false);
  }
}

describe('renderNotificationHtml markdown conversion', () => {
  it('renders **bold** as strong', () => {
    const container = renderInto('**bold**');
    expect(query<HTMLElement>(container, 'strong').textContent).toBe('bold');
  });

  it('renders *italic* as em', () => {
    const container = renderInto('*italic*');
    expect(query<HTMLElement>(container, 'em').textContent).toBe('italic');
  });

  it('renders `code` as code', () => {
    const container = renderInto('`inline code`');
    expect(query<HTMLElement>(container, 'code').textContent).toBe(
      'inline code'
    );
  });

  it('renders a fenced code block as pre > code', () => {
    const container = renderInto(['```ts', 'const x = 1;', '```'].join('\n'));
    const pre = query<HTMLElement>(container, 'pre');
    const code = query<HTMLElement>(pre, 'code');
    expect(code.textContent).toContain('const x = 1;');
  });

  it('renders a dash list as ul with li items', () => {
    const container = renderInto('- a\n- b');
    const items = container.querySelectorAll('ul > li');
    expect(Array.from(items, item => item.textContent)).toEqual(['a', 'b']);
  });

  it('renders an ordered list as ol with li items', () => {
    const container = renderInto('1. a\n2. b');
    const items = container.querySelectorAll('ol > li');
    expect(Array.from(items, item => item.textContent)).toEqual(['a', 'b']);
  });

  it('renders a blockquote as blockquote', () => {
    const container = renderInto('> quote');
    expect(query<HTMLElement>(container, 'blockquote').textContent).toContain(
      'quote'
    );
  });

  it('renders a markdown link as an anchor', () => {
    const container = renderInto('[Jupyter](https://jupyter.org)');
    const anchor = query<HTMLAnchorElement>(container, 'a');
    expect(anchor.getAttribute('href')).toBe('https://jupyter.org');
    expect(anchor.textContent).toBe('Jupyter');
  });

  it('renders a single newline as br', () => {
    const container = renderInto('a\nb');
    expect(container.querySelectorAll('br')).toHaveLength(1);
    expect(container.textContent?.trim()).toBe('ab');
  });

  it('renders GFM strikethrough as del', () => {
    const container = renderInto('~~gone~~');
    expect(query<HTMLElement>(container, 'del').textContent).toBe('gone');
  });
});

describe('renderNotificationHtml allowed inline styling', () => {
  it('keeps a colour keyword inside a span', () => {
    const span = query<HTMLSpanElement>(
      renderInto('<span style="color:red">x</span>'),
      'span'
    );
    expect(span.getAttribute('style')).toBe('color: red');
    expect(span.textContent).toBe('x');
  });

  it('keeps a hex colour inside a span', () => {
    const span = query<HTMLSpanElement>(
      renderInto('<span style="color:#ff0000">x</span>'),
      'span'
    );
    expect(span.getAttribute('style')).toBe('color: #ff0000');
  });

  it('keeps an rgb colour inside a span', () => {
    const span = query<HTMLSpanElement>(
      renderInto('<span style="color:rgb(255, 0, 0)">x</span>'),
      'span'
    );
    expect(span.getAttribute('style')).toBe('color: rgb(255, 0, 0)');
  });

  it('keeps a font size inside a span', () => {
    const span = query<HTMLSpanElement>(
      renderInto('<span style="font-size:12px">x</span>'),
      'span'
    );
    expect(span.getAttribute('style')).toBe('font-size: 12px');
  });

  it('keeps colour and font size together', () => {
    const span = query<HTMLSpanElement>(
      renderInto('<span style="color: red; font-size: 1.5em">x</span>'),
      'span'
    );
    expect(span.getAttribute('style')).toBe('color: red; font-size: 1.5em');
  });
});

describe('renderNotificationHtml security matrix', () => {
  it('S1 removes script elements and their content', () => {
    const container = renderInto('<script>alert(1)</script>');
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).not.toContain('alert(1)');
  });

  it('S2 removes img and its onerror handler', () => {
    const container = renderInto('<img src=x onerror=alert(1)>');
    expect(container.querySelector('img')).toBeNull();
    expect(attributeNames(container)).not.toContain('onerror');
  });

  it('S3 removes a javascript: href and the link attributes', () => {
    const container = renderInto('<a href="javascript:alert(1)">go</a>');
    const anchor = query<HTMLAnchorElement>(container, 'a');
    expect(anchor.hasAttribute('href')).toBe(false);
    expect(anchor.hasAttribute('target')).toBe(false);
    expect(anchor.hasAttribute('rel')).toBe(false);
    expect(anchor.textContent).toBe('go');
  });

  it('S4 removes a mixed-case JaVaScRiPt: href', () => {
    const container = renderInto('<a href="JaVaScRiPt:alert(1)">go</a>');
    const anchor = query<HTMLAnchorElement>(container, 'a');
    expect(anchor.hasAttribute('href')).toBe(false);
    expect(anchor.hasAttribute('target')).toBe(false);
    expect(anchor.hasAttribute('rel')).toBe(false);
  });

  it('S5 removes an entity-obfuscated java&#x09;script: href', () => {
    const container = renderInto('<a href="java&#x09;script:alert(1)">go</a>');
    const anchor = query<HTMLAnchorElement>(container, 'a');
    expect(anchor.hasAttribute('href')).toBe(false);
    expect(anchor.hasAttribute('target')).toBe(false);
    expect(anchor.hasAttribute('rel')).toBe(false);
  });

  it('S6 removes a data: href carrying a script payload', () => {
    const container = renderInto(
      '<a href="data:text/html,<script>alert(1)</script>">go</a>'
    );
    const anchor = query<HTMLAnchorElement>(container, 'a');
    expect(anchor.hasAttribute('href')).toBe(false);
    expect(container.querySelector('script')).toBeNull();
  });

  it('S7 removes a vbscript: href', () => {
    const container = renderInto('<a href="vbscript:msgbox(1)">go</a>');
    const anchor = query<HTMLAnchorElement>(container, 'a');
    expect(anchor.hasAttribute('href')).toBe(false);
    expect(anchor.hasAttribute('target')).toBe(false);
    expect(anchor.hasAttribute('rel')).toBe(false);
  });

  it('S8 removes a protocol-relative href', () => {
    const container = renderInto('<a href="//evil.example/x">go</a>');
    expect(query<HTMLAnchorElement>(container, 'a').hasAttribute('href')).toBe(
      false
    );
  });

  it('S9 removes a relative href', () => {
    const container = renderInto('<a href="/relative">go</a>');
    expect(query<HTMLAnchorElement>(container, 'a').hasAttribute('href')).toBe(
      false
    );
  });

  it('S10 overrides a sender supplied target and rel', () => {
    const container = renderInto(
      '<a href="https://example.com" target="_top" rel="opener">go</a>'
    );
    const anchor = query<HTMLAnchorElement>(container, 'a');
    expect(anchor.getAttribute('href')).toBe('https://example.com');
    expect(anchor.getAttribute('target')).toBe('_blank');
    expect(anchor.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('S11 keeps a mailto: href and hardens the link', () => {
    const container = renderInto('<a href="mailto:ops@example.com">mail</a>');
    const anchor = query<HTMLAnchorElement>(container, 'a');
    expect(anchor.getAttribute('href')).toBe('mailto:ops@example.com');
    expect(anchor.getAttribute('target')).toBe('_blank');
    expect(anchor.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('S12 removes SVG payloads and their handlers', () => {
    const container = renderInto(
      '<svg onload="alert(1)"><circle r="10"/></svg>'
    );
    expect(container.querySelector('svg')).toBeNull();
    expect(container.querySelector('circle')).toBeNull();
    expect(attributeNames(container)).not.toContain('onload');
  });

  it('S13 removes MathML payloads and xlink attributes', () => {
    const container = renderInto(
      '<math><mi xlink:href="javascript:alert(1)">x</mi></math>'
    );
    expect(container.querySelector('math')).toBeNull();
    expect(container.querySelector('mi')).toBeNull();
    expect(attributeNames(container)).not.toContain('xlink:href');
  });

  it('S14 removes an iframe and its srcdoc payload', () => {
    const container = renderInto(
      '<iframe srcdoc="<script>alert(1)</script>"></iframe>'
    );
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).not.toContain('alert');
  });

  it('S15 removes object and embed elements', () => {
    const container = renderInto(
      '<object data="javascript:alert(1)"></object><embed src="data:text/html,x">'
    );
    expect(container.querySelector('object')).toBeNull();
    expect(container.querySelector('embed')).toBeNull();
  });

  it('S16 removes form controls and their action attributes', () => {
    const container = renderInto(
      '<form action="javascript:alert(1)"><input formaction="javascript:alert(1)"></form>'
    );
    expect(container.querySelector('form')).toBeNull();
    expect(container.querySelector('input')).toBeNull();
    expect(attributeNames(container)).not.toContain('action');
    expect(attributeNames(container)).not.toContain('formaction');
  });

  it('S17 removes a style element and its @import text', () => {
    const container = renderInto(
      '<style>@import "https://evil.example/x.css";</style>'
    );
    expect(container.querySelector('style')).toBeNull();
    expect(container.textContent).not.toContain('@import');
  });

  it('S18 drops position and offset declarations', () => {
    const span = query<HTMLSpanElement>(
      renderInto(
        '<span style="color:red;position:fixed;top:0;left:0">x</span>'
      ),
      'span'
    );
    expect(span.getAttribute('style')).toBe('color: red');
  });

  it('S19 keeps a valid font size declaration', () => {
    const span = query<HTMLSpanElement>(
      renderInto('<span style="font-size:12px">x</span>'),
      'span'
    );
    expect(span.getAttribute('style')).toBe('font-size: 12px');
  });

  it('S20 removes a style containing url()', () => {
    const container = renderInto(
      '<span style="background:url(javascript:alert(1))">x</span>'
    );
    const span = query<HTMLSpanElement>(container, 'span');
    expect(span.hasAttribute('style')).toBe(false);
    expect(span.textContent).toBe('x');
  });

  it('S21 removes a style containing expression()', () => {
    const span = query<HTMLSpanElement>(
      renderInto('<span style="font-size:expression(alert(1))">x</span>'),
      'span'
    );
    expect(span.hasAttribute('style')).toBe(false);
  });

  it('S22 removes a var() colour', () => {
    const span = query<HTMLSpanElement>(
      renderInto('<span style="color:var(--x)">x</span>'),
      'span'
    );
    expect(span.hasAttribute('style')).toBe(false);
  });

  it('S23 removes id, name, class and data-* attributes', () => {
    const container = renderInto(
      '<div id="jupyter" name="getElementById" class="x" data-y="z">t</div>'
    );
    expect(container.querySelector('div')).toBeNull();
    expect(container.querySelector('[id]')).toBeNull();
    expect(container.querySelector('[name]')).toBeNull();
    expect(container.querySelector('[class]')).toBeNull();
    expect(container.querySelector('[data-y]')).toBeNull();
    expect(container.textContent).toBe('t');
  });

  it('S24 removes event-handler attributes', () => {
    const container = renderInto(
      '<p onclick="alert(1)" onmouseover="alert(1)">t</p>'
    );
    const paragraph = query<HTMLParagraphElement>(container, 'p');
    expect(paragraph.attributes).toHaveLength(0);
    expect(paragraph.textContent).toBe('t');
    expectNoEventHandlers(container);
  });

  it('S25 removes an HTML comment carrying a script', () => {
    const container = renderInto('<!--<script>alert(1)</script>-->');
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).not.toContain('alert(1)');
  });

  it('S26 does not resolve a noscript mutation-XSS payload', () => {
    const container = renderInto(
      '<noscript><p title="</noscript><img src=x onerror=alert(1)>">x</p></noscript>'
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(attributeNames(container)).not.toContain('onerror');
  });

  it('S27 removes a template and its script content', () => {
    const container = renderInto(
      '<template><script>alert(1)</script></template>'
    );
    expect(container.querySelector('template')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).not.toContain('alert(1)');
  });

  it('S28 returns an empty string for empty input', () => {
    expect(renderNotificationHtml('')).toBe('');
  });

  it('S29 clips a very long message to 140 characters plus an ellipsis', () => {
    const container = renderInto('a'.repeat(100000));
    expect(container.textContent).toHaveLength(141);
    expect(container.textContent?.endsWith('…')).toBe(true);
  });

  it('S30 renders bold, italic and inline code together', () => {
    const container = renderInto('**bold** *italic* `code`');
    expect(container.querySelector('strong')).not.toBeNull();
    expect(container.querySelector('em')).not.toBeNull();
    expect(container.querySelector('code')).not.toBeNull();
  });

  it('S31 hardens both a markdown link and an autolink', () => {
    const container = renderInto('[x](https://e.example) <https://e.example>');
    const anchors = Array.from(container.querySelectorAll('a'));
    expect(anchors).toHaveLength(2);
    for (const anchor of anchors) {
      expect(anchor.getAttribute('target')).toBe('_blank');
      expect(anchor.getAttribute('rel')).toBe('noopener noreferrer');
    }
  });

  it('S32 removes a markdown image and its src', () => {
    const container = renderInto('![alt](https://e.example/x.png)');
    expect(container.querySelector('img')).toBeNull();
    expect(attributeNames(container)).not.toContain('src');
  });

  it('S33 strips a heading element and keeps its text', () => {
    const container = renderInto('# Heading');
    expect(container.querySelector('h1')).toBeNull();
    expect(container.textContent).toContain('Heading');
  });

  it('S34 renders a list', () => {
    const container = renderInto('- a\n- b');
    expect(container.querySelectorAll('ul > li')).toHaveLength(2);
  });

  it('S35 renders a blockquote', () => {
    expect(renderInto('> quote').querySelector('blockquote')).not.toBeNull();
  });

  it('S36 renders a line break', () => {
    const container = renderInto('a\nb');
    expect(container.querySelectorAll('br')).toHaveLength(1);
    expect(container.textContent?.trim()).toBe('ab');
  });

  it('S37 shows escaped script tags as text only', () => {
    const container = renderInto('&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(container.querySelector('script')).toBeNull();
    expect(container.textContent).toContain('alert(1)');
  });

  it('S38 clips by code point without splitting an emoji', () => {
    const container = renderInto(`${'a'.repeat(139)}😀b`);
    const text = container.textContent ?? '';
    expect(text).not.toContain('�');
    expect(Array.from(text).length).toBeLessThanOrEqual(141);
    expect(text).toContain('😀');
  });

  it('S39 cuts a long source at a line boundary and keeps a link inside the bound', () => {
    const raw = `[Jupyter](https://jupyter.org)\n${'a'.repeat(3100)}\n${'b'.repeat(2000)}`;
    const anchor = query<HTMLAnchorElement>(renderInto(raw), 'a');
    expect(anchor.getAttribute('href')).toBe('https://jupyter.org');
    expect(anchor.textContent).toBe('Jupyter');
  });
});

describe('renderNotificationHtml link contract', () => {
  it('keeps an http link, opens it in a new tab and severs opener', () => {
    const anchor = query<HTMLAnchorElement>(
      renderInto('<a href="http://example.com/page">http</a>'),
      'a'
    );
    expect(anchor.getAttribute('href')).toBe('http://example.com/page');
    expect(anchor.getAttribute('target')).toBe('_blank');
    expect(anchor.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('keeps an https link with its query and fragment', () => {
    const anchor = query<HTMLAnchorElement>(
      renderInto('[https](https://example.com/path?q=1#frag)'),
      'a'
    );
    expect(anchor.getAttribute('href')).toBe(
      'https://example.com/path?q=1#frag'
    );
    expect(anchor.getAttribute('target')).toBe('_blank');
    expect(anchor.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('keeps a mailto link and sets target and rel', () => {
    const anchor = query<HTMLAnchorElement>(
      renderInto('[mail](mailto:ops@example.com)'),
      'a'
    );
    expect(anchor.getAttribute('href')).toBe('mailto:ops@example.com');
    expect(anchor.getAttribute('target')).toBe('_blank');
    expect(anchor.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('never keeps target and rel on a rejected href', () => {
    const anchor = query<HTMLAnchorElement>(
      renderInto(
        '<a href="javascript:alert(1)" target="_blank" rel="opener">go</a>'
      ),
      'a'
    );
    expect(anchor.hasAttribute('href')).toBe(false);
    expect(anchor.hasAttribute('target')).toBe(false);
    expect(anchor.hasAttribute('rel')).toBe(false);
  });
});
