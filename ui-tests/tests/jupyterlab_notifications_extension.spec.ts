import { expect, test } from '@jupyterlab/galata';

/**
 * Don't load JupyterLab webpage before running the tests.
 * This is required to ensure we capture all log messages.
 */
test.use({ autoGoto: false });

test('should emit an activation console message', async ({ page }) => {
  const logs: string[] = [];

  page.on('console', message => {
    logs.push(message.text());
  });

  await page.goto();

  expect(
    logs.filter(
      s =>
        s ===
        'JupyterLab extension @stellarshenson/jupyterlab-notifications-extension is activated!'
    )
  ).toHaveLength(1);
});

test('should launch notification dialog from command', async ({ page }) => {
  await page.goto();
  const dialog = await openSendDialog(page);

  // Verify form elements exist within dialog
  await expect(
    dialog.locator('input[placeholder="Enter notification message"]')
  ).toBeVisible();
  await expect(dialog.locator('select')).toBeVisible();

  // Close dialog
  await page.click('button:has-text("Cancel")');
});

/**
 * Opens the send dialog through the command palette and returns it. The
 * command's own promise resolves only when the dialog CLOSES, so it is never
 * awaited here.
 */
async function openSendDialog(page: any) {
  await page.keyboard.press('Control+Shift+c');
  await page.waitForSelector('.lm-CommandPalette');
  await page.keyboard.type('Send Notification');
  await page.waitForTimeout(300);
  await page.keyboard.press('Enter');
  const dialog = page.locator('.jp-Dialog');
  await expect(dialog.locator('.jp-Dialog-header')).toContainText(
    'Send Notification',
    { timeout: 5000 }
  );
  return dialog;
}

/**
 * A greyed Send button used to be the whole signal for an invalid field, so an
 * operator who typed a value the field rejects had nothing on screen to act on.
 * Both constrained fields now sit inside JupyterLab's own inputWrapper, whose
 * :invalid rule paints the field at fault.
 *
 * The seconds field takes the min-underflow case because 0 is a value the CLI
 * and README both document as meaningful, so an operator really does type it.
 */
test('should mark the field at fault, not only grey out Send', async ({
  page
}) => {
  await page.goto();
  const dialog = await openSendDialog(page);

  await dialog.locator('#jp-notify-message').fill('Marked field probe');
  const seconds = dialog.locator('#jp-notify-seconds');

  // The Dialog recomputes its button state from an `input` event only.
  const stateFor = async (value: string) => {
    await seconds.fill(value);
    await seconds.dispatchEvent('input');
    return seconds.evaluate((el: HTMLInputElement) => ({
      invalid: !el.checkValidity(),
      background: getComputedStyle(el).backgroundColor
    }));
  };

  const accepted = await stateFor('5');
  const rejected = await stateFor('0');

  expect(accepted.invalid).toBe(false);
  expect(rejected.invalid).toBe(true);
  // The field's own appearance must change. Comparing it against the same
  // field when valid is what makes this fail if the wrapper stops matching
  // the stylesheet: an unstyled input has a background either way, so
  // asserting the colour is merely non-transparent proves nothing.
  expect(rejected.background).not.toBe(accepted.background);

  // Inside the wrapper, which is what makes the stylesheet's :invalid rule
  // apply at all.
  await expect(
    dialog.locator('.jp-InputDialog-inputWrapper > #jp-notify-seconds')
  ).toHaveCount(1);

  await expect(
    dialog.locator('.jp-Dialog-button.jp-mod-accept')
  ).toBeDisabled();

  await page.click('button:has-text("Cancel")');
});

/**
 * The command's caption said who receives a notification, and Lumino renders
 * captions into a node JupyterLab sets to display:none - so the fix reached
 * nobody. This asserts the sentence is on screen with a non-zero box, not that
 * the string exists somewhere in the bundle.
 */
test('should tell the sender who receives the notification', async ({
  page
}) => {
  await page.goto();
  const dialog = await openSendDialog(page);

  const audience = dialog.locator('.jp-notify-dialog > div', {
    hasText: 'Other users are not reached'
  });
  await expect(audience).toBeVisible();

  // toBeVisible already requires a non-empty box, so asserting width and
  // height here could not fail. Position is what it cannot check.
  const box = await audience.boundingBox();

  // Above the field the operator types into, not below the buttons.
  const messageBox = await dialog.locator('#jp-notify-message').boundingBox();
  expect(box!.y).toBeLessThan(messageBox!.y);

  await page.click('button:has-text("Cancel")');
});

/**
 * Wrapping the two constrained inputs in JupyterLab's inputWrapper is what
 * paints the field at fault, but it also brings two of that stylesheet's
 * values that do not survive the move: the error background is the same pale
 * pink in both themes while the font colour follows the theme, and the
 * suppression rule for an untouched required field sets border and background
 * to `unset`, which compute to currentcolor and transparent. style/base.css
 * corrects both, scoped to this dialog. Measured in both themes because the
 * dark one is where each defect was visible.
 */
for (const theme of ['JupyterLab Light', 'JupyterLab Dark']) {
  test(`should keep the dialog legible in ${theme}`, async ({ page }) => {
    await page.goto();
    await page.evaluate(async (name: string) => {
      await (window as any).jupyterapp.commands.execute(
        'apputils:change-theme',
        { theme: name }
      );
    }, theme);
    await page.waitForTimeout(1200);

    const dialog = await openSendDialog(page);

    // The field the dialog opens on must not render as a bare outline in the
    // text colour, which is what `unset` computes to. Read twice: the dialog
    // focuses this field on open, so reading it only while focused let the
    // :focus rule supply the border and both of the rules below survived
    // deletion with this test green.
    const message = dialog.locator('#jp-notify-message');
    const chromeOf = () =>
      message.evaluate((el: HTMLInputElement) => {
        const style = getComputedStyle(el);
        return {
          border: style.borderTopColor,
          background: style.backgroundColor,
          color: style.color
        };
      });

    // Asserted, not assumed: openSendDialog waits only for the header text,
    // and reading the focused style before focus lands made this test fail
    // intermittently inside the full suite while passing in isolation.
    await expect(message).toBeFocused();
    const focused = await chromeOf();
    await dialog.locator('#jp-notify-type').focus();
    const blurred = await chromeOf();

    expect(blurred.background).not.toBe('rgba(0, 0, 0, 0)');
    // `unset` on border-color computes to currentcolor, so the defect is
    // exactly the border matching the text colour.
    expect(blurred.border).not.toBe(blurred.color);
    // And the focus indicator has to be a visible change, not the same border.
    expect(focused.border).not.toBe(blurred.border);

    // The value the operator has to correct must stay readable on the error
    // background, which is theme-invariant, so the text colour must be too.
    const seconds = dialog.locator('#jp-notify-seconds');
    await seconds.fill('0');
    await seconds.dispatchEvent('input');
    const marked = await seconds.evaluate((el: HTMLInputElement) => {
      const style = getComputedStyle(el);
      return { color: style.color, background: style.backgroundColor };
    });
    expect(marked.background).toBe('rgb(255, 205, 210)');
    expect(marked.color).toBe('rgb(183, 28, 28)');

    await page.click('button:has-text("Cancel")');
  });
}

/**
 * `required` is satisfied by a single space, so Send stayed live, the dialog
 * closed, and the trim afterwards rejected the message - taking the type, the
 * seconds and the dismiss choice with it. A pattern makes the field invalid
 * while it holds only whitespace, so the destructive path cannot be reached.
 */
test('should refuse a whitespace-only message before the form is lost', async ({
  page
}) => {
  await page.goto();
  const dialog = await openSendDialog(page);

  const message = dialog.locator('#jp-notify-message');
  await message.fill('   ');
  await message.dispatchEvent('input');

  const backgroundOf = () =>
    message.evaluate(
      (el: HTMLInputElement) => getComputedStyle(el).backgroundColor
    );

  expect(
    await message.evaluate((el: HTMLInputElement) => el.checkValidity())
  ).toBe(false);
  await expect(
    dialog.locator('.jp-Dialog-button.jp-mod-accept')
  ).toBeDisabled();

  // The message field's own mark had no assertion, so deleting its wrapper
  // class passed the whole suite. Compared against the same field holding a
  // valid value, as the seconds test does.
  const whitespaceBackground = await backgroundOf();
  await expect(
    dialog.locator('.jp-InputDialog-inputWrapper > #jp-notify-message')
  ).toHaveCount(1);
  await message.fill('A real message');
  await message.dispatchEvent('input');
  expect(whitespaceBackground).not.toBe(await backgroundOf());
  await message.fill('   ');
  await message.dispatchEvent('input');

  // Still open, so nothing typed has been discarded.
  await expect(dialog.locator('.jp-Dialog-header')).toContainText(
    'Send Notification'
  );

  await page.click('button:has-text("Cancel")');
});

test('should display time-ago indicator on notification', async ({ page }) => {
  await page.goto();

  // POST a notification via the API
  const baseUrl = page.url().replace(/\/lab.*$/, '');
  await page.request.post(
    `${baseUrl}/jupyterlab-notifications-extension/ingest`,
    {
      data: {
        message: 'Time-ago test notification',
        type: 'info',
        autoClose: false
      }
    }
  );

  // Wait for the polling cycle to pick up the notification (max 35s)
  const toast = page.locator('.jp-toast-message', {
    hasText: 'Time-ago test notification'
  });
  await expect(toast).toBeVisible({ timeout: 35000 });

  // Verify time-ago element was injected
  const timeAgo = toast.locator('.jp-toast-time-ago');
  await expect(timeAgo).toBeVisible({ timeout: 2000 });

  // Verify it shows a valid time label
  const text = await timeAgo.textContent();
  expect(text).toMatch(/^(just now|\d+[smhd] ago)$/);
});

test('should place time-ago inline with action buttons', async ({ page }) => {
  await page.goto();

  // POST a notification with an action button
  const baseUrl = page.url().replace(/\/lab.*$/, '');
  await page.request.post(
    `${baseUrl}/jupyterlab-notifications-extension/ingest`,
    {
      data: {
        message: 'Button time-ago test',
        type: 'success',
        autoClose: false,
        actions: [
          { label: 'Dismiss', caption: 'Close', displayType: 'default' }
        ]
      }
    }
  );

  // Wait for the notification toast
  const toast = page.locator('.Toastify__toast', {
    hasText: 'Button time-ago test'
  });
  await expect(toast).toBeVisible({ timeout: 35000 });

  // Time-ago should be inside the button bar, not inside jp-toast-message
  const buttonBar = toast.locator('.jp-toast-buttonBar');
  await expect(buttonBar).toBeVisible();

  const timeAgo = buttonBar.locator('.jp-toast-time-ago');
  await expect(timeAgo).toBeVisible({ timeout: 2000 });

  // Verify the action button is also present on the same bar
  const button = buttonBar.locator('.jp-toast-button');
  await expect(button).toBeVisible();
});

/**
 * The --now path and the poll path have different delivery guarantees, and the
 * difference is the reason the WebSocket exists. These three tests hold the
 * distinction: a push reaches every open tab promptly, a polled notification
 * reaches exactly one, because the fetch is a destructive single-consumer drain.
 */

/** Wait until the lab shell is up and the extension's socket has had time to open. */
async function labReady(target: any): Promise<void> {
  await target.waitForSelector('#jp-main-dock-panel', { timeout: 60000 });
  // The socket opens on activation; without this the push has no listener and
  // the test would silently fall through to the 30-second poll.
  await target.waitForTimeout(2000);
}

test('should show an --now notification without waiting for the poll', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  const baseUrl = page.url().replace(/\/lab.*$/, '');
  await page.request.post(
    `${baseUrl}/jupyterlab-notifications-extension/ingest`,
    {
      data: { message: 'Push speed probe', immediate: true, autoClose: false }
    }
  );

  // 3s, an order of magnitude under the 30s poll: only the push can meet it.
  await expect(
    page.locator('.jp-toast-message', { hasText: 'Push speed probe' })
  ).toBeVisible({ timeout: 3000 });
});

test('should show an --now notification in every open tab', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  const url = page.url();
  const second = await page.context().newPage();
  await second.goto(url);
  await labReady(second);

  const baseUrl = url.replace(/\/lab.*$/, '');
  await page.request.post(
    `${baseUrl}/jupyterlab-notifications-extension/ingest`,
    {
      data: { message: 'Broadcast probe', immediate: true, autoClose: false }
    }
  );

  await expect(
    page.locator('.jp-toast-message', { hasText: 'Broadcast probe' })
  ).toBeVisible({ timeout: 5000 });
  await expect(
    second.locator('.jp-toast-message', { hasText: 'Broadcast probe' })
  ).toBeVisible({ timeout: 5000 });

  await second.close();
});

test('should hand a polled notification to exactly one tab', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  const url = page.url();
  const second = await page.context().newPage();
  await second.goto(url);
  await labReady(second);

  // No immediate flag, so this one travels only by the poll fetch, which
  // empties the queue for whichever tab asks first.
  const baseUrl = url.replace(/\/lab.*$/, '');
  await page.request.post(
    `${baseUrl}/jupyterlab-notifications-extension/ingest`,
    { data: { message: 'Drain probe', autoClose: false } }
  );

  const count = async (target: any) =>
    target.locator('.jp-toast-message', { hasText: 'Drain probe' }).count();

  // One full poll cycle plus margin, so both tabs have certainly fetched.
  await page.waitForTimeout(35000);

  const seen = (await count(page)) + (await count(second));
  expect(seen).toBe(1);

  await second.close();
});

/**
 * Both ways the stream can be unavailable - a server too old to serve the route,
 * and a rotated token the handshake rejects - land on the same onclose path. The
 * requirement is that the 30-second poll keeps working and the retry backs off
 * instead of reconnecting every few seconds for the life of the tab.
 *
 * There is no give-up to assert: the client retries at the 60s ceiling for as
 * long as the tab is open, because a tab that stops reconnecting loses --now
 * notifications outright rather than degrading to poll-only.
 */
for (const mode of ['closed by the server', 'rejected as forbidden']) {
  test(`should keep delivering by poll when the stream is ${mode}`, async ({
    page
  }) => {
    let attempts = 0;
    await page
      .context()
      .routeWebSocket(
        /jupyterlab-notifications-extension\/stream/,
        (ws: any) => {
          attempts += 1;
          ws.close({ code: mode === 'rejected as forbidden' ? 1008 : 1006 });
        }
      );

    await page.goto();
    await labReady(page);

    const label = `Degraded poll probe ${mode}`;
    const baseUrl = page.url().replace(/\/lab.*$/, '');
    await page.request.post(
      `${baseUrl}/jupyterlab-notifications-extension/ingest`,
      { data: { message: label, autoClose: false } }
    );

    // The poll is the only route left, so this is the graceful-degradation claim.
    await expect(
      page.locator('.jp-toast-message', { hasText: label })
    ).toBeVisible({ timeout: 40000 });

    // Backoff, not a hammer: 5s, 10s, 20s puts about three attempts in this
    // window, where a fixed 5s retry would put seven or more.
    expect(attempts).toBeGreaterThan(0);
    expect(attempts).toBeLessThanOrEqual(5);
  });
}

/** POST one notification through this extension's ingest route. */
async function postNotification(
  page: any,
  data: Record<string, unknown>
): Promise<void> {
  const baseUrl = page.url().replace(/\/lab.*$/, '');
  const response = await page.request.post(
    `${baseUrl}/jupyterlab-notifications-extension/ingest`,
    { data }
  );
  expect(response.ok()).toBe(true);
}

/**
 * Formatting reaches the operator only if the rendered elements are on screen,
 * so these cases read the toast DOM rather than the message string.
 */
test('should render Markdown and an allowed inline style in a toast', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  await postNotification(page, {
    message:
      'Formatting probe **bold** and `inline code`\n\n- first item\n- second item\n\n<span style="color: #e91e63; font-size: 18px">styled span</span>',
    autoClose: false,
    immediate: true
  });

  const message = page.locator('.jp-toast-message', {
    hasText: 'Formatting probe'
  });
  await expect(message).toBeVisible({ timeout: 10000 });

  await expect(message.locator('strong')).toHaveText('bold');
  await expect(message.locator('code')).toHaveText('inline code');
  await expect(message.locator('li')).toHaveText(['first item', 'second item']);

  // Computed values, not the attribute text: a sanitised but inert attribute
  // would look identical in the markup and leave the operator nothing to read.
  const span = message.locator('span');
  await expect(span).toHaveText('styled span');
  await expect(span).toHaveCSS('color', 'rgb(233, 30, 99)');
  await expect(span).toHaveCSS('font-size', '18px');
});

test('should render a link that opens in a new tab without an opener', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  await postNotification(page, {
    message: 'Link probe [example docs](https://example.com/docs)',
    autoClose: false,
    immediate: true
  });

  const message = page.locator('.jp-toast-message', { hasText: 'Link probe' });
  const link = message.locator('a', { hasText: 'example docs' });
  await expect(link).toBeVisible({ timeout: 10000 });
  await expect(link).toHaveAttribute('href', 'https://example.com/docs');
  await expect(link).toHaveAttribute('target', '_blank');
  await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
});

test('should render the same markup in the notification centre', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  await postNotification(page, {
    message:
      'Centre probe **bold** and `inline code` [centre link](https://example.com/centre)',
    autoClose: false,
    immediate: true
  });

  await expect(
    page.locator('.jp-toast-message', { hasText: 'Centre probe' })
  ).toBeVisible({ timeout: 10000 });

  await page.evaluate(async () => {
    await (window as any).jupyterapp.commands.execute(
      'apputils:display-notifications'
    );
  });

  const row = page.locator('.jp-Notification-List-Item', {
    hasText: 'Centre probe'
  });
  await expect(row).toBeVisible({ timeout: 10000 });

  const message = row.locator('.jp-toast-message');
  await expect(message.locator('strong')).toHaveText('bold');
  await expect(message.locator('code')).toHaveText('inline code');
  const link = message.locator('a', { hasText: 'centre link' });
  await expect(link).toHaveAttribute('href', 'https://example.com/centre');
  await expect(link).toHaveAttribute('target', '_blank');
  await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
});

/**
 * A transient notification is a toast and nothing else: its entry must leave
 * the notification centre when the toast auto-closes. The non-transient
 * notification posted afterwards is the control that proves the centre is
 * rendering its list - an empty centre would satisfy the absence check alone.
 */
test('should keep a transient notification out of the notification centre', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  const transientMessage = 'Transient centre probe';
  await postNotification(page, {
    message: transientMessage,
    transient: true,
    immediate: true,
    autoClose: 1000
  });

  const toast = page.locator('.jp-toast-message', {
    hasText: transientMessage
  });
  await expect(toast).toBeVisible({ timeout: 5000 });

  // autoClose removes the toast; the extension then dismisses the entry.
  await expect(toast).toBeHidden({ timeout: 10000 });

  await page.evaluate(async () => {
    await (window as any).jupyterapp.commands.execute(
      'apputils:display-notifications'
    );
  });
  await expect(page.locator('.jp-Notification-Center')).toBeVisible({
    timeout: 10000
  });

  const transientRow = page.locator('.jp-Notification-List-Item', {
    hasText: transientMessage
  });
  await expect(transientRow).toHaveCount(0);

  const persistentMessage = 'Persistent centre probe';
  await postNotification(page, {
    message: persistentMessage,
    immediate: true,
    autoClose: false
  });

  await expect(
    page.locator('.jp-Notification-List-Item', { hasText: persistentMessage })
  ).toBeVisible({ timeout: 10000 });
  // Re-checked after the list rendered a row, so the absence is measured on a
  // centre that is demonstrably showing its contents.
  await expect(transientRow).toHaveCount(0);
});

/**
 * JupyterLab creates no toast for a notification that arrives while the centre
 * is open - its toast listener returns early for the open list popup - so the
 * extension's removal observer never sees a toast go and the tracked id would
 * keep its centre row. injectTimeAgoIntoCenter reconciles such an id on the
 * next centre render; the persistent control row is the proof that the render
 * happened, so the absence is not measured on an empty centre.
 */
test('should drop a transient notification delivered to an open centre', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  await page.evaluate(async () => {
    await (window as any).jupyterapp.commands.execute(
      'apputils:display-notifications'
    );
  });
  await expect(page.locator('.jp-Notification-Center')).toBeVisible({
    timeout: 10000
  });

  const transientMessage = 'Transient open-centre probe';
  await postNotification(page, {
    message: transientMessage,
    transient: true,
    immediate: true,
    autoClose: 1000
  });

  const persistentMessage = 'Persistent open-centre probe';
  await postNotification(page, {
    message: persistentMessage,
    immediate: true,
    autoClose: false
  });

  await expect(
    page.locator('.jp-Notification-List-Item', { hasText: persistentMessage })
  ).toBeVisible({ timeout: 10000 });
  await expect(
    page.locator('.jp-Notification-List-Item', { hasText: transientMessage })
  ).toHaveCount(0);
});

/**
 * The sanitised output is asserted structurally: a browser does not run a
 * script inserted through innerHTML, so the absence of the node, the handler
 * and the href is the security property, and the global proves none ran.
 */
test('should strip scripts, event handlers and javascript: URLs in a toast', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  await postNotification(page, {
    message:
      'Security probe <script>window.__notifXss = "script"</script>' +
      '<img src="missing.png" onerror="window.__notifXss = \'error\'">' +
      '<a href="javascript:window.__notifXss = \'href\'">unsafe link</a>',
    autoClose: false,
    immediate: true
  });

  const message = page.locator('.jp-toast-message', {
    hasText: 'Security probe'
  });
  await expect(message).toBeVisible({ timeout: 10000 });

  // The anchor survives without its href, so finding it also waits for the
  // rendered markup to replace JupyterLab's plain text.
  const link = message.locator('a', { hasText: 'unsafe link' });
  await expect(link).toBeVisible({ timeout: 5000 });

  await expect(message.locator('script')).toHaveCount(0);
  await expect(message.locator('img')).toHaveCount(0);
  await expect(message.locator('[onerror]')).toHaveCount(0);
  expect(await link.getAttribute('href')).toBeNull();
  expect(await page.evaluate(() => (window as any).__notifXss)).toBeUndefined();
});

/**
 * apputils:notify calls the manager directly, the same path as the culler and
 * file-upload toasts. Markdown in such a message must stay literal, because
 * the text was never addressed to this extension's renderer.
 */
test('should leave a JupyterLab native notification as plain text', async ({
  page
}) => {
  await page.goto();
  await labReady(page);

  await page.evaluate(async () => {
    await (window as any).jupyterapp.commands.execute('apputils:notify', {
      message: 'Native probe **bold** <span style="color: red">span</span>',
      type: 'info',
      options: { autoClose: false }
    });
  });

  const message = page.locator('.jp-toast-message', {
    hasText: 'Native probe'
  });
  await expect(message).toBeVisible({ timeout: 10000 });

  await expect(message.locator('strong')).toHaveCount(0);
  await expect(message.locator('span')).toHaveCount(0);
  await expect(message).toContainText('Native probe **bold**');
});
