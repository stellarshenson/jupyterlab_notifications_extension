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

  // Execute the command programmatically (simpler than UI interaction)
  await page.evaluate(() => {
    window.jupyterlab.commands.execute('jupyterlab-notifications:send');
  });

  // Verify dialog appears
  await expect(page.locator('.jp-Dialog-header')).toContainText(
    'Send Notification'
  );

  // Verify form elements exist
  await expect(page.locator('input[type="text"]')).toBeVisible();
  await expect(page.locator('select')).toBeVisible();

  // Close dialog
  await page.click('button:has-text("Cancel")');
});
