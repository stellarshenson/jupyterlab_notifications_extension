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
        'JupyterLab extension jupyterlab_notifications_extension is activated!'
    )
  ).toHaveLength(1);
});

test('should launch notification dialog from command', async ({ page }) => {
  await page.goto();

  // Open command palette
  await page.keyboard.press('Control+Shift+c');

  // Wait for palette
  await page.waitForSelector('.lm-CommandPalette');

  // Type command name
  await page.keyboard.type('Send Notification');

  // Wait for filtered results
  await page.waitForTimeout(300);

  // Press Enter to execute first matching command
  await page.keyboard.press('Enter');

  // Verify dialog appears
  const dialog = page.locator('.jp-Dialog');
  await expect(dialog.locator('.jp-Dialog-header')).toContainText(
    'Send Notification',
    { timeout: 5000 }
  );

  // Verify form elements exist within dialog
  await expect(
    dialog.locator('input[placeholder="Enter notification message"]')
  ).toBeVisible();
  await expect(dialog.locator('select')).toBeVisible();

  // Close dialog
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
