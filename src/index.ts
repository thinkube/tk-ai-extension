import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ISettingRegistry } from '@jupyterlab/settingregistry';

/**
 * Initialization data for the tk-ai-extension extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'tk-ai-extension:plugin',
  description: 'AI assistant extension for tk-ai lab (Thinkube JupyterHub)',
  autoStart: true,
  optional: [ISettingRegistry],
  activate: (app: JupyterFrontEnd, settingRegistry: ISettingRegistry | null) => {
    console.log('JupyterLab extension tk-ai-extension is activated!');

    if (settingRegistry) {
      settingRegistry
        .load(plugin.id)
        .then(settings => {
          console.log('tk-ai-extension settings loaded:', settings.composite);
        })
        .catch(reason => {
          console.error('Failed to load settings for tk-ai-extension.', reason);
        });
    }
  }
};

export default plugin;
