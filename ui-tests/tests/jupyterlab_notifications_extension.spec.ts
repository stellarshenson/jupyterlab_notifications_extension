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

test('should have Send Notification command registered', async ({ page }) => {
  await page.goto();

  // Verify extension loaded by checking command is registered
  const commandExists = await page.evaluate(() => {
    return window.jupyterlab.commands.hasCommand(
      'jupyterlab-notifications:send'
    );
  });

  expect(commandExists).toBe(true);
});
