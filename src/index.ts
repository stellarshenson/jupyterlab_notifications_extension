import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ICommandPalette, Dialog } from '@jupyterlab/apputils';
import { Widget } from '@lumino/widgets';

import { requestAPI } from './request';

/**
 * Notification interface matching backend payload
 */
interface INotificationData {
  id: string;
  message: string;
  type: 'default' | 'info' | 'success' | 'warning' | 'error' | 'in-progress';
  autoClose: number | false;
  createdAt: number;
  actions?: Array<{
    label: string;
    caption?: string;
    displayType?: 'default' | 'accent' | 'warn' | 'link';
  }>;
  data?: any;
}

/**
 * Poll interval in milliseconds (30 seconds)
 */
const POLL_INTERVAL = 30000;

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
        // Build options object
        const options: any = {
          autoClose: notif.autoClose
        };

        // Add data field if present
        if (notif.data !== undefined) {
          options.data = notif.data;
        }

        // Build actions array if present (actions are passed as part of options)
        if (notif.actions && notif.actions.length > 0) {
          options.actions = notif.actions.map(action => ({
            label: action.label,
            caption: action.caption || '',
            displayType: action.displayType || 'default',
            callback: () => {
              console.log(`Action clicked: ${action.label}`);
            }
          }));
        }

        // Display notification using JupyterLab's command
        app.commands
          .execute('apputils:notify', {
            message: notif.message,
            type: notif.type,
            options: options
          })
          .catch(err => {
            console.error('Failed to display notification:', err);
          });
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
            buttons: [
              Dialog.cancelButton(),
              Dialog.okButton({ label: 'Send' })
            ]
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
