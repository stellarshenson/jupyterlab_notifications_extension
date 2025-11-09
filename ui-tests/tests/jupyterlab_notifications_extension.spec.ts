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
