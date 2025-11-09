import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ICommandPalette } from '@jupyterlab/apputils';

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
        const message = args.message as string;
        const type = (args.type as string) || 'info';
        const autoClose = args.autoClose !== undefined ? args.autoClose : 5000;
        const actions = args.actions || [];
        const data = args.data;

        if (!message) {
          console.error('Notification message is required');
          return;
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
