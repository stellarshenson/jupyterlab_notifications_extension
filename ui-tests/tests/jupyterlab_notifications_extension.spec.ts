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

test('should open notification dialog from command palette', async ({
  page
}) => {
  await page.goto();

  // Open command palette
  await page.keyboard.press('Control+Shift+C');

  // Search for Send Notification command
  await page.fill('.jp-Dialog-content input', 'Send Notification');

  // Click the command
  await page.click('text=Send Notification');

  // Verify dialog appears with title
  await expect(page.locator('.jp-Dialog-header')).toContainText(
    'Send Notification'
  );

  // Verify form elements are present
  await expect(page.locator('input[type="text"]')).toBeVisible();
  await expect(page.locator('select')).toBeVisible();
  await expect(page.locator('input[type="checkbox"]')).toBeVisible();
  await expect(page.locator('input[type="number"]')).toBeVisible();

  // Close dialog
  await page.click('button:has-text("Cancel")');
});
