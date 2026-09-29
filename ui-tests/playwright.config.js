/**
 * Configuration for Playwright using default from @jupyterlab/galata.
 *
 * The port is threaded through one variable so a developer with their own lab
 * on 8888 can run the suite. Galata pins the test server to a port and sets no
 * retries, so both ends must agree or the server dies rather than move.
 */
const baseConfig = require('@jupyterlab/galata/lib/playwright-config');

const PORT = process.env.JUPYTER_TEST_PORT || '8888';
const BASE_URL = `http://localhost:${PORT}`;

module.exports = {
  ...baseConfig,
  use: {
    ...baseConfig.use,
    baseURL: BASE_URL
  },
  // The server's notification queue is process-global and the fetch drains it,
  // so two specs running at once steal each other's notifications.
  workers: 1,
  fullyParallel: false,
  webServer: {
    command: 'jlpm start',
    url: `${BASE_URL}/lab`,
    // The server root is this directory, so galata's per-test tmpPath
    // directory resolves through the contents API at the same place;
    // configure_jupyter_server otherwise roots the server at a fresh mkdtemp.
    // The port is passed too, so this file is its sole owner under Playwright.
    env: {
      ...process.env,
      JUPYTERLAB_GALATA_ROOT_DIR: __dirname,
      JUPYTER_TEST_PORT: PORT
    },
    timeout: 120 * 1000,
    // Never reuse: an existing server on this port is the developer's own lab,
    // and the suite would report on that instead of on a fixture.
    reuseExistingServer: false
  }
};
