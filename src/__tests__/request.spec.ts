import { ServerConnection } from '@jupyterlab/services';

import { requestAPI } from '../request';

/**
 * The extension's handlers report failures under `error`, jupyter_server's own
 * report under `message`. Reading only one key handed the whole body to
 * ResponseError, and the dialog's failure toast rendered it as "[object Object]".
 */
describe('requestAPI error reporting', () => {
  const makeResponse = (
    body: string,
    status = 400,
    statusText = 'Bad Request'
  ) =>
    ({
      ok: false,
      status,
      statusText,
      text: async () => body
    }) as unknown as Response;

  beforeEach(() => {
    jest
      .spyOn(ServerConnection, 'makeSettings')
      .mockReturnValue({ baseUrl: 'http://localhost:8888/' } as any);
  });

  afterEach(() => jest.restoreAllMocks());

  const reason = "'message' must be a non-empty string";

  it("reports the reason from this extension's `error` key", async () => {
    jest
      .spyOn(ServerConnection, 'makeRequest')
      .mockResolvedValue(makeResponse(JSON.stringify({ error: reason })));

    await expect(requestAPI('ingest')).rejects.toThrow(reason);
  });

  it("reports the reason from jupyter_server's `message` key", async () => {
    jest
      .spyOn(ServerConnection, 'makeRequest')
      .mockResolvedValue(
        makeResponse(JSON.stringify({ message: 'Forbidden' }))
      );

    await expect(requestAPI('ingest')).rejects.toThrow('Forbidden');
  });

  /**
   * A body carrying NEITHER key is the whole point: a proxy answering a restart
   * with its own JSON, an nginx HTML page, or an empty 502. Feeding a body that
   * has `error` here tested nothing - it passed with the fallback deleted.
   */
  it.each([
    ['a proxy JSON body under a third key', '{"detail":"upstream closed"}'],
    ['an HTML error page', '<html><head><title>504 Gateway Time-out</title>'],
    ['an empty body', ''],
    ['an empty object', '{}'],
    ['an array', '[]'],
    ['a null body', 'null'],
    // The only row that reaches the `typeof detail === 'string'` half of the
    // guard. Without it, deleting that check left every case green, because
    // every other body makes `detail` undefined. A proxy really does answer
    // with a structured message.
    ['a non-string message value', '{"message":{"code":502}}']
  ])('falls back to the status line for %s', async (_label, body) => {
    jest
      .spyOn(ServerConnection, 'makeRequest')
      .mockResolvedValue(makeResponse(body, 504, 'Gateway Time-out'));

    const err = (await requestAPI('ingest').catch(e => e)) as Error;
    // Equality alone; asserting the message does not contain '[object Object]'
    // or '<html>' after it could not fail.
    expect(err.message).toBe('504 Gateway Time-out');
  });
});
