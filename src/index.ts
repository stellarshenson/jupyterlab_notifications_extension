import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ICommandPalette, Dialog, Notification } from '@jupyterlab/apputils';
import { Widget } from '@lumino/widgets';
import {
  ReadonlyJSONValue,
  ReadonlyPartialJSONObject
} from '@lumino/coreutils';

import { requestAPI } from './request';
import { formatTimeAgo } from './utils';

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
 * Poll interval in milliseconds (30 seconds)
 */
const POLL_INTERVAL = 30000;

/**
 * Create and return a styled time-ago DOM element.
 */
function createTimeAgoElement(createdAt: number): HTMLDivElement {
  const el = document.createElement('div');
  el.className = 'jp-toast-time-ago';
  el.textContent = formatTimeAgo(createdAt);
  el.style.fontSize = '0.75em';
  el.style.color = 'var(--jp-ui-font-color2, #888)';
  el.style.marginTop = '4px';
  return el;
}

/**
 * Inject a time-ago indicator into a toast popup after notify().
 *
 * Finds the toast by matching message text inside .jp-toast-message,
 * appends a styled element, and refreshes it every 10 seconds.
 * The interval self-clears when the notification is dismissed.
 */
function injectTimeAgo(
  message: string,
  createdAt: number,
  notifId: string
): void {
  setTimeout(() => {
    const toasts = Array.from(document.querySelectorAll('.jp-toast-message'));
    let target: Element | null = null;
    for (const el of toasts) {
      if (
        el.textContent === message &&
        !el.querySelector('.jp-toast-time-ago')
      ) {
        target = el;
        break;
      }
    }
    if (!target) {
      return;
    }

    const timeEl = createTimeAgoElement(createdAt);

    // If a button bar exists, place time-ago inside it (left-aligned)
    const parent = target.parentElement;
    const buttonBar = parent
      ? parent.querySelector('.jp-toast-buttonBar')
      : null;
    if (buttonBar) {
      timeEl.style.marginTop = '0';
      buttonBar.insertBefore(timeEl, buttonBar.firstChild);
    } else {
      target.appendChild(timeEl);
    }

    const refreshInterval = setInterval(() => {
      if (!Notification.manager.has(notifId)) {
        clearInterval(refreshInterval);
        return;
      }
      timeEl.textContent = formatTimeAgo(createdAt);
    }, 10000);
  }, 100);
}

/**
 * Inject time-ago indicators into all notifications visible in the
 * Notification Center panel. Matches DOM elements to manager entries
 * by message text to look up createdAt timestamps. Starts a shared
 * interval that refreshes all visible indicators and stops when the
 * center is removed from the DOM.
 */
function injectTimeAgoIntoCenter(center: Element): void {
  const items = Array.from(center.querySelectorAll('.jp-toast-message'));
  const notifications = Notification.manager.notifications;

  // Build a lookup from message text to createdAt, handling duplicates
  // by consuming matched entries (shift from a per-message list)
  const lookup = new Map<string, number[]>();
  for (const n of notifications) {
    const list = lookup.get(n.message) || [];
    list.push(n.createdAt);
    lookup.set(n.message, list);
  }

  const injected: HTMLDivElement[] = [];

  for (const el of items) {
    // Check both inside the message and in the parent (covers button bar sibling)
    const elParent = el.parentElement;
    if (
      el.querySelector('.jp-toast-time-ago') ||
      (elParent && elParent.querySelector('.jp-toast-time-ago'))
    ) {
      continue;
    }
    const msg = el.textContent || '';
    const timestamps = lookup.get(msg);
    if (!timestamps || timestamps.length === 0) {
      continue;
    }
    const createdAt = timestamps.shift()!;
    const timeEl = createTimeAgoElement(createdAt);

    // If a button bar exists, place time-ago inside it (left-aligned)
    const bar = elParent ? elParent.querySelector('.jp-toast-buttonBar') : null;
    if (bar) {
      timeEl.style.marginTop = '0';
      bar.insertBefore(timeEl, bar.firstChild);
    } else {
      el.appendChild(timeEl);
    }
    injected.push(timeEl);
  }

  if (injected.length === 0) {
    return;
  }

  // Refresh all injected elements while the center is open
  const refreshInterval = setInterval(() => {
    if (!document.body.contains(center)) {
      clearInterval(refreshInterval);
      return;
    }
    // Re-read timestamps for accuracy
    const fresh = Notification.manager.notifications;
    const freshLookup = new Map<string, number[]>();
    for (const n of fresh) {
      const list = freshLookup.get(n.message) || [];
      list.push(n.createdAt);
      freshLookup.set(n.message, list);
    }
    for (const el of injected) {
      if (!document.body.contains(el)) {
        continue;
      }
      const parent = el.parentElement;
      if (!parent) {
        continue;
      }
      // Get the message text excluding the time-ago element itself
      const msg = Array.from(parent.childNodes)
        .filter(node => node !== el)
        .map(node => node.textContent || '')
        .join('');
      const ts = freshLookup.get(msg);
      if (ts && ts.length > 0) {
        el.textContent = formatTimeAgo(ts.shift()!);
      }
    }
  }, 10000);
}

/**
 * Set up a MutationObserver to watch for the Notification Center
 * opening and inject time-ago indicators into its list items.
 *
 * Uses subtree observation to catch both the center being added
 * and its list items being populated after the initial render.
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
          setTimeout(() => injectTimeAgoIntoCenter(center), 100);
          continue;
        }
        // Also catch list items added inside an existing center
        const existingCenter = node.closest('.jp-Notification-Center');
        if (existingCenter) {
          setTimeout(() => injectTimeAgoIntoCenter(existingCenter), 100);
        }
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

/**
 * Fetch and display notifications from the server
 */
async function fetchAndDisplayNotifications(
  app: JupyterFrontEnd
): Promise<void> {
  try {
    const response = await requestAPI<{ notifications: INotificationData[] }>(
      'notifications'
    );

    if (response.notifications && response.notifications.length > 0) {
      console.log(
        `Received ${response.notifications.length} notification(s) from server`
      );

      response.notifications.forEach(notif => {
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
                app.commands
                  .execute(action.commandId, action.args)
                  .catch(err => {
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

        // Inject a time-ago element into the toast DOM
        injectTimeAgo(notif.message, notif.createdAt, notifId);
      });
    }
  } catch (reason) {
    console.error('Failed to fetch notifications from server:', reason);
  }
}

/**
 * Initialization data for the jupyterlab_notifications_extension extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'jupyterlab_notifications_extension:plugin',
  description:
    'Jupyterlab extension to receive and display notifications in the main panel. Those can be from the jupyterjub administrator or from other places.',
  autoStart: true,
  requires: [ICommandPalette],
  activate: (app: JupyterFrontEnd, palette: ICommandPalette) => {
    console.log(
      'JupyterLab extension jupyterlab_notifications_extension is activated!'
    );

    // Register command to send notifications
    const commandId = 'jupyterlab-notifications:send';
    app.commands.addCommand(commandId, {
      label: 'Send Notification',
      caption: 'Send a notification to all JupyterLab users',
      execute: async (args: any) => {
        let message = args.message as string;
        let type = (args.type as string) || 'info';
        let autoClose = args.autoClose !== undefined ? args.autoClose : 5000;
        let actions = args.actions || [];
        const data = args.data;

        // If no message provided, show input dialog
        if (!message) {
          // Create dialog body with form elements
          const body = document.createElement('div');
          body.style.display = 'flex';
          body.style.flexDirection = 'column';
          body.style.gap = '10px';

          // Message input
          const messageLabel = document.createElement('label');
          messageLabel.textContent = 'Message:';
          const messageInput = document.createElement('input');
          messageInput.type = 'text';
          messageInput.placeholder = 'Enter notification message';
          messageInput.style.width = '100%';
          messageInput.style.padding = '5px';

          // Type select
          const typeLabel = document.createElement('label');
          typeLabel.textContent = 'Type:';
          const typeSelect = document.createElement('select');
          typeSelect.style.width = '100%';
          typeSelect.style.padding = '5px';
          ['info', 'success', 'warning', 'error', 'in-progress'].forEach(t => {
            const option = document.createElement('option');
            option.value = t;
            option.textContent = t;
            typeSelect.appendChild(option);
          });

          // Auto-close checkbox and seconds input
          const autoCloseContainer = document.createElement('div');
          autoCloseContainer.style.display = 'flex';
          autoCloseContainer.style.alignItems = 'center';
          autoCloseContainer.style.gap = '10px';

          const autoCloseCheckbox = document.createElement('input');
          autoCloseCheckbox.type = 'checkbox';
          autoCloseCheckbox.id = 'autoCloseCheckbox';
          autoCloseCheckbox.checked = true;

          const autoCloseLabel = document.createElement('label');
          autoCloseLabel.htmlFor = 'autoCloseCheckbox';
          autoCloseLabel.textContent = 'Auto-close after';
          autoCloseLabel.style.cursor = 'pointer';

          const autoCloseInput = document.createElement('input');
          autoCloseInput.type = 'number';
          autoCloseInput.value = '5';
          autoCloseInput.min = '1';
          autoCloseInput.style.width = '60px';
          autoCloseInput.style.padding = '3px';

          const secondsLabel = document.createElement('span');
          secondsLabel.textContent = 'seconds';

          autoCloseContainer.appendChild(autoCloseCheckbox);
          autoCloseContainer.appendChild(autoCloseLabel);
          autoCloseContainer.appendChild(autoCloseInput);
          autoCloseContainer.appendChild(secondsLabel);

          // Disable/enable input based on checkbox
          autoCloseCheckbox.addEventListener('change', () => {
            autoCloseInput.disabled = !autoCloseCheckbox.checked;
          });

          // Dismiss button checkbox
          const dismissCheckbox = document.createElement('input');
          dismissCheckbox.type = 'checkbox';
          dismissCheckbox.id = 'dismissCheckbox';
          const dismissLabel = document.createElement('label');
          dismissLabel.htmlFor = 'dismissCheckbox';
          dismissLabel.textContent = ' Include dismiss button';
          dismissLabel.style.display = 'flex';
          dismissLabel.style.alignItems = 'center';
          dismissLabel.style.gap = '5px';
          dismissLabel.style.cursor = 'pointer';
          dismissLabel.prepend(dismissCheckbox);

          body.appendChild(messageLabel);
          body.appendChild(messageInput);
          body.appendChild(typeLabel);
          body.appendChild(typeSelect);
          body.appendChild(autoCloseContainer);
          body.appendChild(dismissLabel);

          const widget = new Widget({ node: body });

          const dialog = new Dialog({
            title: 'Send Notification',
            body: widget,
            buttons: [Dialog.cancelButton(), Dialog.okButton({ label: 'Send' })]
          });

          const result = await dialog.launch();

          if (result.button.accept) {
            message = messageInput.value;
            if (!message) {
              return; // No message entered
            }

            // Override with dialog values
            type = typeSelect.value;

            // Set autoClose based on checkbox and input
            if (autoCloseCheckbox.checked) {
              autoClose = parseInt(autoCloseInput.value) * 1000; // Convert to milliseconds
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
            autoClose
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

          console.log('Notification sent successfully');
        } catch (error) {
          console.error('Failed to send notification:', error);
        }
      }
    });

    // Add command to palette
    palette.addItem({ command: commandId, category: 'Notifications' });

    // Watch for Notification Center opening to inject time-ago
    observeNotificationCenter();

    // Fetch notifications immediately on startup
    fetchAndDisplayNotifications(app);

    // Set up periodic polling for new notifications
    setInterval(() => {
      fetchAndDisplayNotifications(app);
    }, POLL_INTERVAL);

    console.log(
      `Notification polling started (interval: ${POLL_INTERVAL / 1000}s)`
    );
  }
};

export default plugin;
