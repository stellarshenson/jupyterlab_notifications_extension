import { URLExt } from '@jupyterlab/coreutils';

import { ServerConnection } from '@jupyterlab/services';

/**
 * The server extension's URL namespace. Three copies exist on purpose:
 * here, routes.py, and a third copy in cli.py, which must not import
 * tornado to send one POST. The path is a published contract.
 */
export const API_NAMESPACE = 'jupyterlab-notifications-extension';

/**
 * Call the server extension
 *
 * @param endPoint API REST end point for the extension
 * @param init Initial values for the request
 * @returns The response body interpreted as JSON
 */
export async function requestAPI<T>(
  endPoint = '',
  init: RequestInit = {}
): Promise<T> {
  // Make request to Jupyter API
  const settings = ServerConnection.makeSettings();
  const requestUrl = URLExt.join(settings.baseUrl, API_NAMESPACE, endPoint);

  let response: Response;
  try {
    response = await ServerConnection.makeRequest(requestUrl, init, settings);
  } catch (error) {
    throw new ServerConnection.NetworkError(error as any);
  }

  let data: any = await response.text();

  if (data.length > 0) {
    try {
      data = JSON.parse(data);
    } catch (error) {
      console.warn('Not a JSON response body.', response);
    }
  }

  if (!response.ok) {
    // jupyter_server's own error bodies use `message`; this extension's use
    // `error`. Anything else - a proxy's JSON under some third key, an nginx
    // HTML page, an empty body - has no reason to be readable, so it falls back
    // to the status line rather than being interpolated into the toast, which
    // is where "[object Object]" and a truncated <html> came from.
    const detail = data?.message ?? data?.error;
    throw new ServerConnection.ResponseError(
      response,
      typeof detail === 'string' && detail
        ? detail
        : `${response.status} ${response.statusText}`
    );
  }

  return data;
}
