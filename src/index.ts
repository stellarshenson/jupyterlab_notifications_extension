import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ICommandPalette, Dialog, Notification } from '@jupyterlab/apputils';
import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';
import { Widget } from '@lumino/widgets';
import {
  ReadonlyJSONValue,
  ReadonlyPartialJSONObject
} from '@lumino/coreutils';

import { requestAPI, API_NAMESPACE } from './request';
import { formatTimeAgo, reconnectDelay } from './utils';

/**
 * Action interface for notifications
 */
interface INotificationAction {
  label: string;
  caption?: string;
  displayType?: 'default' | 'accent' | 'warn' | 'link';
  commandId?: string;
  args?: ReadonlyPartialJSONObject;
}

/**
 * Notification interface matching backend payload
 */
interface INotificationData {
  id: string;
  message: string;
  type: 'default' | 'info' | 'success' | 'warning' | 'error' | 'in-progress';
  autoClose: number | false;
  createdAt: number;
  actions?: INotificationAction[];
  data?: ReadonlyJSONValue;
}

/**
 * How long a notification stays on screen when the sender does not say. The
 * server applies the same default to a REST caller that omits the field.
 */
const DEFAULT_AUTO_CLOSE_MS = 5000;

/**
 * Poll interval in milliseconds (30 seconds)
 */
const POLL_INTERVAL = 30000;

/**
 * How many notifications either bookkeeping structure remembers. One number for
 * one concept: serverCreatedAt is keyed by the UUID notify() returns while
 * seenNotificationIds holds the server's id, so the two key spaces never meet -
 * but both exist to stop unbounded growth over a long-lived tab, so a reader who
 * changes the retention depth changes it once.
 */
const MAX_TRACKED_NOTIFICATIONS = 500;

/**
 * Module-level map from notification id to the server-side createdAt.
 *
 * Keyed by id, never by message text: JupyterLab truncates a rendered message
 * at 140 characters, so the text in the DOM is not the text we sent, and two
 * notifications may legitimately carry the same message.
 */
const serverCreatedAt = new Map<string, number>();

/**
 * How often a visible relative timestamp is rewritten.
 */
const TIME_AGO_REFRESH_MS = 10000;

/**
 * How long to let JupyterLab finish rendering before looking for the element.
 */
const DOM_SETTLE_MS = 100;

/**
 * Create and return a styled time-ago DOM element.
 */
function createTimeAgoElement(createdAt: number): HTMLDivElement {
  const el = document.createElement('div');
  el.className = 'jp-toast-time-ago';
  el.textContent = formatTimeAgo(createdAt);
  // No size reduction: 0.75em of the 11px message text rendered at 8.25px,
  // below JupyterLab's smallest type token. Colour alone subordinates it.
  el.style.color = 'var(--jp-ui-font-color2)';
  el.style.marginTop = '4px';
  el.title = new Date(createdAt).toLocaleString();
  return el;
}

/**
 * Place a time-ago element for one notification and keep it current.
 *
 * `insideLiveRegion` marks the toast case: react-toastify gives the toast body
 * role="alert", which implies an assertive atomic live region, so rewriting
 * anything inside re-announces the whole toast. There the element is hidden
 * from assistive technology, and in both cases the text is written only when
 * it actually changed.
 */
function placeTimeAgo(
  msgEl: Element,
  createdAt: number,
  insideLiveRegion: boolean
): void {
  const parent = msgEl.parentElement;
  if (
    msgEl.querySelector('.jp-toast-time-ago') ||
    (parent && parent.querySelector('.jp-toast-time-ago'))
  ) {
    return;
  }

  const timeEl = createTimeAgoElement(createdAt);
  if (insideLiveRegion) {
    timeEl.setAttribute('aria-hidden', 'true');
  }

  const buttonBar = parent ? parent.querySelector('.jp-toast-buttonBar') : null;
  if (buttonBar) {
    timeEl.style.marginTop = '0';
    // The bar sets no align-items, so the item would stretch and its text would
    // sit above the button labels' baseline.
    timeEl.style.alignSelf = 'center';
    buttonBar.insertBefore(timeEl, buttonBar.firstChild);
  } else {
    msgEl.appendChild(timeEl);
  }

  const refresh = setInterval(() => {
    // Detachment is the only reliable end condition: manager.has() stays true
    // after a toast auto-closes, because autoClose does not dismiss it.
    if (!document.body.contains(timeEl)) {
      clearInterval(refresh);
      return;
    }
    const next = formatTimeAgo(createdAt);
    if (timeEl.textContent !== next) {
      timeEl.textContent = next;
    }
  }, TIME_AGO_REFRESH_MS);
}

/**
 * Resolve the createdAt for a notification id, preferring the server value.
 */
function createdAtFor(notifId: string): number | null {
  const fromServer = serverCreatedAt.get(notifId);
  if (fromServer !== undefined) {
    return fromServer;
  }
  const entry = Notification.manager.notifications.find(n => n.id === notifId);
  return entry ? entry.createdAt : null;
}

/**
 * Inject a time-ago element into one toast, addressed by its notification id.
 *
 * Every toast element carries its notification id as the DOM id, including
 * toasts from other sources, so the culler and file-upload toasts are covered
 * by the same lookup.
 */
function injectTimeAgoIntoToast(toast: HTMLElement): void {
  const msgEl = toast.querySelector('.jp-toast-message');
  if (!msgEl || !toast.id) {
    return;
  }
  const createdAt = createdAtFor(toast.id);
  if (createdAt === null) {
    return;
  }
  placeTimeAgo(msgEl, createdAt, true);
}

/**
 * Inject time-ago into every row of the notification centre.
 *
 * The centre renders Notification.manager.notifications in array order, so row
 * N is entry N. The row carries its id only as a React key, not as a DOM
 * attribute, so position is the only join available; injection is skipped
 * while the counts disagree rather than risk pairing a row with the wrong
 * notification's timestamp.
 */
function injectTimeAgoIntoCenter(center: Element): void {
  const rows = Array.from(
    center.querySelectorAll('.jp-Notification-List-Item')
  );
  const entries = Notification.manager.notifications;
  if (rows.length !== entries.length) {
    return;
  }

  rows.forEach((row, i) => {
    const msgEl = row.querySelector('.jp-toast-message');
    if (!msgEl) {
      return;
    }
    const entry = entries[i];
    const createdAt = serverCreatedAt.get(entry.id) ?? entry.createdAt;
    placeTimeAgo(msgEl, createdAt, false);
  });
}

/**
 * Set up a MutationObserver to watch for the Notification Center
 * opening and for any toast popup appearing, injecting time-ago
 * indicators into both.
 *
 * Uses subtree observation to catch the center being added,
 * its list items being populated, and individual toast popups.
 */
function observeNotificationCenter(): void {
  const observer = new MutationObserver(mutations => {
    for (const mutation of mutations) {
      for (let i = 0; i < mutation.addedNodes.length; i++) {
        const node = mutation.addedNodes[i];
        if (!(node instanceof HTMLElement)) {
          continue;
        }
        // Check if the added node is or contains a notification center
        const center = node.classList.contains('jp-Notification-Center')
          ? node
          : node.querySelector('.jp-Notification-Center');
        if (center) {
          setTimeout(() => injectTimeAgoIntoCenter(center), DOM_SETTLE_MS);
          continue;
        }
        // Also catch list items added inside an existing center
        const existingCenter = node.closest('.jp-Notification-Center');
        if (existingCenter) {
          setTimeout(
            () => injectTimeAgoIntoCenter(existingCenter),
            DOM_SETTLE_MS
          );
          continue;
        }
        // Catch toast popups (from any source, not just our extension)
        const toast = node.classList.contains('Toastify__toast')
          ? node
          : node.querySelector('.Toastify__toast');
        if (toast instanceof HTMLElement) {
          setTimeout(() => injectTimeAgoIntoToast(toast), DOM_SETTLE_MS);
        }
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

/**
 * IDs of notifications already displayed. A notification can arrive via
 * both the WebSocket push and the poll, so this dedups across both paths.
 * Bounded to MAX_TRACKED_NOTIFICATIONS (oldest evicted) - an id can never
 * legitimately re-arrive once its push and single poll delivery are past, so a
 * large cap is ample and prevents unbounded growth on long-lived tabs.
 */
const seenNotificationIds = new Set<string>();

/**
 * Display a single notification, skipping duplicates by id.
 * Shared by the WebSocket push path and the polling path.
 */
function displayNotification(
  app: JupyterFrontEnd,
  notif: INotificationData
): void {
  if (notif.id && seenNotificationIds.has(notif.id)) {
    return;
  }
  if (notif.id) {
    seenNotificationIds.add(notif.id);
    // Evict the oldest id (Set preserves insertion order) to bound memory
    if (seenNotificationIds.size > MAX_TRACKED_NOTIFICATIONS) {
      const oldest = seenNotificationIds.values().next().value;
      if (oldest !== undefined) {
        seenNotificationIds.delete(oldest);
      }
    }
  }

  // Build options object with explicit type
  const options: Notification.IOptions<ReadonlyJSONValue> = {
    autoClose: notif.autoClose
  };

  // Add data field if present
  if (notif.data !== undefined) {
    options.data = notif.data;
  }

  // Build actions array if present
  if (notif.actions && notif.actions.length > 0) {
    options.actions = notif.actions.map(action => ({
      label: action.label,
      caption: action.caption || '',
      displayType: action.displayType || 'default',
      callback: () => {
        // If commandId provided, execute the command
        if (action.commandId) {
          app.commands.execute(action.commandId, action.args).catch(err => {
            console.error(
              `Failed to execute command '${action.commandId}':`,
              err
            );
          });
        }
        // Default: button click dismisses notification (built-in behavior)
      }
    }));
  }

  // Display notification
  const notifId = Notification.manager.notify(
    notif.message,
    notif.type,
    options
  );

  // Record the server timestamp against the id the toast will carry; the
  // MutationObserver places the element once the toast is rendered.
  serverCreatedAt.set(notifId, notif.createdAt);
  if (serverCreatedAt.size > MAX_TRACKED_NOTIFICATIONS) {
    const oldestKey = serverCreatedAt.keys().next().value;
    if (oldestKey !== undefined) {
      serverCreatedAt.delete(oldestKey);
    }
  }
}

/**
 * Tracks whether the background poll is currently failing, so a transient
 * network condition (offline tab, suspended machine) is reported once on the
 * transition rather than spilling a fresh console error every poll cycle.
 */
let pollOffline = false;

async function fetchAndDisplayNotifications(
  app: JupyterFrontEnd
): Promise<void> {
  try {
    const response = await requestAPI<{ notifications: INotificationData[] }>(
      'notifications'
    );

    if (pollOffline) {
      pollOffline = false;
      console.debug('Notification poll reconnected to server');
    }

    if (response.notifications && response.notifications.length > 0) {
      console.debug(
        `Received ${response.notifications.length} notification(s) from server`
      );

      response.notifications.forEach(notif => displayNotification(app, notif));
    }
  } catch (reason) {
    // A failed poll is almost always transient (tab offline, machine asleep).
    // Warn once on the offline transition, then stay silent while it persists -
    // the poll keeps retrying and recovers on its own without operator action.
    if (!pollOffline) {
      pollOffline = true;
      console.warn(
        'Notification poll temporarily unavailable; will keep retrying',
        reason
      );
    }
  }
}

/**
 * Reconnect backoff for the notification stream. On repeated failure the delay
 * grows exponentially to a 60s ceiling and retries at that rate for as long as
 * the tab is open - the same contract the 30s poll already has.
 *
 * There is deliberately no give-up. The poll is a single-consumer destructive
 * drain (README, "Poll is best-effort"), so a tab that stops reconnecting does
 * not degrade to poll-only: it loses outright every --now notification that
 * another tab's poll takes first. A give-up here made a server outage longer
 * than the budget disable immediate delivery for the life of the tab.
 */
const RECONNECT_BASE_MS = 5000;
const RECONNECT_MAX_MS = 60000;

/**
 * Open a WebSocket to the server's notification stream for immediate
 * ("--now") delivery. Notifications pushed here display instantly rather
 * than waiting for the next poll. Reconnects with capped exponential backoff
 * for as long as the tab is open. While the socket is down this tab competes
 * for the destructive poll queue with every other tab and can miss a
 * notification outright, so reconnecting matters more than the retry cost.
 */
function connectNotificationStream(app: JupyterFrontEnd): void {
  const settings = ServerConnection.makeSettings();
  let url = URLExt.join(settings.wsUrl, API_NAMESPACE, 'stream');
  // Gated on appendToken, as @jupyterlab/services does for its own kernel
  // sockets: for a same-host session it is false and the httpOnly cookie
  // carries the handshake, so appending the token only put it in proxy logs.
  // This project states twice that the token travels in a header, not a URL.
  if (settings.appendToken && settings.token) {
    url += `?token=${encodeURIComponent(settings.token)}`;
  }

  let attempts = 0;

  const connect = (): void => {
    const ws = new settings.WebSocket(url);

    ws.onopen = () => {
      attempts = 0; // reset backoff once connected
      console.debug('Notification stream connected');
    };

    ws.onmessage = (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data) as {
          notifications: INotificationData[];
        };
        if (payload.notifications) {
          payload.notifications.forEach(notif =>
            displayNotification(app, notif)
          );
        }
      } catch (err) {
        console.error('Failed to parse notification stream message:', err);
      }
    };

    ws.onclose = () => {
      attempts += 1;
      // The first close since the last successful open, which is the only one
      // worth a line: warning every 60s while a server is down is the noise
      // the poll's own once-only warning exists to avoid. `attempts` is reset
      // in onopen, so this is exactly a transition into the down state.
      if (attempts === 1) {
        console.warn(
          'Notification stream disconnected; retrying in the background. ' +
            'Immediate (--now) delivery is unavailable until it reconnects.'
        );
      }
      setTimeout(
        connect,
        reconnectDelay(attempts, RECONNECT_BASE_MS, RECONNECT_MAX_MS)
      );
    };

    ws.onerror = () => {
      ws.close();
    };
  };

  connect();
}

/**
 * Initialization data for the jupyterlab_notifications_extension extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab_notifications_extension:plugin',
  description:
    'JupyterLab extension that shows notifications sent by a JupyterHub administrator or by a script, as a toast and in the notification center.',
  autoStart: true,
  requires: [ICommandPalette],
  activate: (app: JupyterFrontEnd, palette: ICommandPalette) => {
    // The exact message is required by the extension template and asserted by
    // the Galata suite; the level is not - Playwright captures debug too.
    console.debug(
      'JupyterLab extension jupyterlab_notifications_extension is activated!'
    );

    // Register command to send notifications
    const commandId = 'jupyterlab-notifications:send';
    app.commands.addCommand(commandId, {
      label: 'Send Notification',
      caption:
        'Send a notification to every open tab of this JupyterLab server',
      execute: async (args: any) => {
        let message = args.message as string;
        let type = (args.type as string) || 'info';
        let autoClose =
          args.autoClose !== undefined ? args.autoClose : DEFAULT_AUTO_CLOSE_MS;
        let actions = args.actions || [];
        const data = args.data;

        // If no message provided, show input dialog
        if (!message) {
          // Create dialog body with form elements
          const body = document.createElement('div');
          // Scopes style/base.css's corrections to JupyterLab's inputWrapper
          // styling so they cannot reach the platform's own input dialogs.
          body.className = 'jp-notify-dialog';

          // The command's caption says this too, but Lumino renders captions
          // into .lm-CommandPalette-itemCaption and JupyterLab sets that to
          // display:none, so the palette shows nothing. This is the only place
          // the sender is told who receives it. The second sentence is the
          // half that does the work: naming what is reached does not
          // contradict an administrator who believes it reaches everyone.
          const audience = document.createElement('div');
          audience.id = 'jp-notify-audience';
          audience.textContent =
            'Goes to every open tab of this server. Other users are not reached.';
          // 10px on top of the body's own 10px gap, so the notice reads as
          // separate from the form rather than as its first row.
          audience.style.marginBottom = '10px';
          audience.style.color = 'var(--jp-ui-font-color2)';
          body.style.display = 'flex';
          body.style.flexDirection = 'column';
          body.style.gap = '10px';

          // Message input
          const messageLabel = document.createElement('label');
          messageLabel.textContent = 'Message:';
          messageLabel.htmlFor = 'jp-notify-message';
          const messageInput = document.createElement('input');
          messageInput.id = 'jp-notify-message';
          messageInput.type = 'text';
          messageInput.placeholder = 'Enter notification message';
          // Makes the Dialog disable Send while the field is empty, and the
          // wrapper further down paints the field. It blocks the first Enter
          // only because of the dialog.ready dispatch below - Dialog starts
          // with _hasValidationErrors false and validates only from its own
          // `input` handler, so without that event an untouched field is
          // accepted.
          messageInput.required = true;
          // `required` alone is satisfied by a single space, so Send stayed
          // live, the dialog closed, and the trim further down discarded
          // everything typed. Whitespace-only is invalid here instead.
          // `[\s\S]` rather than `.`, which matches neither U+2028 nor
          // U+2029: a message pasted from a PDF carrying either was rejected
          // with no visible offending character, while the REST route took it.
          messageInput.pattern = '[\\s\\S]*\\S[\\s\\S]*';
          // The hover explanation for a painted field, and part of the
          // accessible description - measured on the field as
          // description=<this text> with invalid=true. Nothing else on screen
          // says why the field turned red. Not the native validation bubble:
          // there is no form here and nothing calls reportValidity, so no
          // bubble can appear.
          messageInput.title =
            'Enter at least one character that is not a space.';
          messageInput.style.width = '100%';
          messageInput.style.padding = '5px';

          // Type select
          const typeLabel = document.createElement('label');
          typeLabel.textContent = 'Type:';
          typeLabel.htmlFor = 'jp-notify-type';
          const typeSelect = document.createElement('select');
          typeSelect.id = 'jp-notify-type';
          typeSelect.style.width = '100%';
          typeSelect.style.padding = '5px';
          const TYPE_LABELS: Record<string, string> = {
            default: 'Default',
            info: 'Info',
            success: 'Success',
            warning: 'Warning',
            error: 'Error',
            'in-progress': 'In progress'
          };
          Object.entries(TYPE_LABELS).forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            typeSelect.appendChild(option);
          });
          typeSelect.value = 'info';

          // Auto-close checkbox and seconds input
          const autoCloseContainer = document.createElement('div');
          autoCloseContainer.style.display = 'flex';
          autoCloseContainer.style.alignItems = 'center';
          autoCloseContainer.style.gap = '10px';

          const autoCloseCheckbox = document.createElement('input');
          autoCloseCheckbox.type = 'checkbox';
          autoCloseCheckbox.id = 'jp-notify-auto-close';
          autoCloseCheckbox.checked = true;

          const autoCloseLabel = document.createElement('label');
          autoCloseLabel.htmlFor = 'jp-notify-auto-close';
          autoCloseLabel.textContent = 'Auto-close after';
          autoCloseLabel.style.cursor = 'pointer';

          const autoCloseInput = document.createElement('input');
          autoCloseInput.type = 'number';
          autoCloseInput.id = 'jp-notify-seconds';
          autoCloseInput.value = String(DEFAULT_AUTO_CLOSE_MS / 1000);
          autoCloseInput.min = '1';
          // Required, so the Dialog's own validation blocks an emptied field.
          // Without it Number('') is 0, and JupyterLab suppresses a toast for a
          // NUMERIC autoClose of zero or less, so the notification would reach
          // the centre and never appear on screen. `false` is not a number and
          // is shown, which the manual-dismiss path relies on.
          autoCloseInput.required = true;
          autoCloseInput.setAttribute('aria-label', 'Auto-close seconds');
          // Nothing associates the visible label below with this input, so
          // this title is still the field's accessible description. It is no
          // longer the only statement of the rule, but it is not removable.
          autoCloseInput.title = 'Whole seconds, one or more.';
          autoCloseInput.style.width = '60px';
          autoCloseInput.style.padding = '3px';

          const secondsLabel = document.createElement('span');
          // min=1 with the default step makes every fraction invalid too, so
          // "1 or more" described a range the control rejects. This puts the
          // whole rule on screen; the title above still carries it for
          // assistive technology, which this span is not associated with.
          secondsLabel.textContent = 'seconds (whole number, 1 or more)';

          autoCloseContainer.appendChild(autoCloseCheckbox);
          autoCloseContainer.appendChild(autoCloseLabel);
          const secondsWrapper = document.createElement('div');
          secondsWrapper.className = 'jp-InputDialog-inputWrapper';
          secondsWrapper.appendChild(autoCloseInput);
          autoCloseContainer.appendChild(secondsWrapper);
          autoCloseContainer.appendChild(secondsLabel);

          // Disable/enable input based on checkbox
          autoCloseCheckbox.addEventListener('change', () => {
            autoCloseInput.disabled = !autoCloseCheckbox.checked;
            // Dialog recomputes its accept button only from an `input` event
            // (Dialog._evtInput), and `change` fires after it. Without this the
            // button state is one action stale in both directions: unchecking
            // the box left Send dead with nothing on screen invalid, and
            // re-checking it left Send live over an empty seconds field.
            autoCloseInput.dispatchEvent(new Event('input', { bubbles: true }));
          });

          // Dismiss button checkbox. Built like the auto-close row above -
          // a flex container holding the checkbox and a sibling label - so the
          // two checkboxes in this form align and read the same way.
          const dismissContainer = document.createElement('div');
          dismissContainer.style.display = 'flex';
          dismissContainer.style.alignItems = 'center';
          dismissContainer.style.gap = '10px';

          const dismissCheckbox = document.createElement('input');
          dismissCheckbox.type = 'checkbox';
          dismissCheckbox.id = 'jp-notify-dismiss';

          const dismissLabel = document.createElement('label');
          dismissLabel.htmlFor = 'jp-notify-dismiss';
          dismissLabel.textContent = 'Include dismiss button';
          dismissLabel.style.cursor = 'pointer';

          dismissContainer.appendChild(dismissCheckbox);
          dismissContainer.appendChild(dismissLabel);

          // JupyterLab's only :invalid styling is scoped to this wrapper class
          // (@jupyterlab/apputils/style/inputdialog.css), and Dialog runs
          // Styling.styleNode over the body, so every input here already
          // carries jp-mod-styled. Wrapping the two constrained fields is what
          // puts an error mark on the field at fault; before it, a greyed Send
          // button was the whole signal and typing 0 in the seconds box killed
          // Send with nothing on screen marked. The stylesheet suppresses the
          // mark while a required field still shows its placeholder, so an
          // untouched form stays calm.
          const messageWrapper = document.createElement('div');
          messageWrapper.className = 'jp-InputDialog-inputWrapper';
          messageWrapper.appendChild(messageInput);

          body.appendChild(audience);
          body.appendChild(messageLabel);
          body.appendChild(messageWrapper);
          body.appendChild(typeLabel);
          body.appendChild(typeSelect);
          body.appendChild(autoCloseContainer);
          body.appendChild(dismissContainer);

          const widget = new Widget({ node: body });

          const dialog = new Dialog({
            title: 'Send Notification',
            body: widget,
            buttons: [
              Dialog.cancelButton(),
              Dialog.okButton({ label: 'Send' })
            ],
            // Addressed by id, not position: 'input' would silently move to
            // whatever field someone inserts above the message field.
            focusNodeSelector: '#jp-notify-message'
          });

          // Describes the dialog, not the message field: aria-describedby
          // outranks title, so putting it on the field would silence that
          // field's own validation text. A static attribute, set here rather
          // than in the ready callback, which resolves after focus has
          // already entered the dialog.
          dialog.node.setAttribute('aria-describedby', 'jp-notify-audience');
          // Dialog sets its own aria-label only when the body is a string
          // (apputils dialog.js), and this body is a widget, so without this
          // the dialog is announced with no name and the description above it
          // has nothing to attach to. The node is a native <dialog> with
          // ariaModal already set there, so the role and the modality are not
          // ours to add.
          dialog.node.setAttribute('aria-label', 'Send Notification');

          // Dialog computes its accept-button state only from its own `input`
          // handler, which it registers in onAfterAttach, so an untouched form
          // starts with Send live over an empty required field and the first
          // Enter is accepted. `ready` resolves after that registration, so one
          // synthetic event there gives the dialog its real state from the
          // start. Dispatched before the await, which resolves only on close.
          dialog.ready.then(() =>
            messageInput.dispatchEvent(new Event('input', { bubbles: true }))
          );

          const result = await dialog.launch();

          if (result.button.accept) {
            // Trimmed so surrounding spaces do not reach the payload. The
            // field's own pattern is what stops a space-only message.
            message = messageInput.value.trim();

            // Override with dialog values
            type = typeSelect.value;

            // Set autoClose based on checkbox and input
            if (autoCloseCheckbox.checked) {
              autoClose = Number(autoCloseInput.value) * 1000; // Convert to milliseconds
            } else {
              autoClose = false;
            }

            actions = dismissCheckbox.checked
              ? [
                  {
                    label: 'Dismiss',
                    caption: 'Close this notification',
                    displayType: 'default'
                  }
                ]
              : [];
          } else {
            return; // User cancelled
          }
        }

        try {
          const payload: any = {
            message,
            type,
            autoClose,
            // The sender's own toast is the confirmation, so do not make them
            // wait a poll cycle for it.
            immediate: true
          };

          if (actions.length > 0) {
            payload.actions = actions;
          }

          if (data !== undefined) {
            payload.data = data;
          }

          await requestAPI('ingest', {
            method: 'POST',
            body: JSON.stringify(payload)
          });

          console.debug('Notification sent successfully');
        } catch (error) {
          // The sender must be told; a console line is not a report.
          // Stays until dismissed: the dialog and everything typed into it are
          // already gone, so a report that auto-closes loses the whole attempt.
          Notification.error(
            `Could not send notification: ${error instanceof Error ? error.message : error}`,
            {
              autoClose: false
            }
          );
        }
      }
    });

    // Add command to palette
    palette.addItem({ command: commandId, category: 'Notifications' });

    // Watch for Notification Center opening to inject time-ago
    observeNotificationCenter();

    // Fetch notifications immediately on startup
    fetchAndDisplayNotifications(app);

    // Set up periodic polling for new notifications (baseline/fallback)
    setInterval(() => {
      fetchAndDisplayNotifications(app);
    }, POLL_INTERVAL);

    // Opened last, and deliberately: anything the WebSocket constructor throws
    // propagates out of activate, so connecting first would have taken the poll
    // baseline down with it - the opposite of what the socket is a bonus to.
    connectNotificationStream(app);

    console.debug(
      `Notification polling started (interval: ${POLL_INTERVAL / 1000}s)`
    );
  }
};

export default plugin;
