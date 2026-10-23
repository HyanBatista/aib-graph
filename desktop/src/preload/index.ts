import { contextBridge, ipcRenderer } from 'electron'

const bridge = {
  tokens: {
    get: (): Promise<string | null> => ipcRenderer.invoke('tokens:get'),
    set: (value: string): Promise<void> => ipcRenderer.invoke('tokens:set', value),
    clear: (): Promise<void> => ipcRenderer.invoke('tokens:clear')
  },
  server: {
    get: (): Promise<string> => ipcRenderer.invoke('server:get'),
    set: (url: string): Promise<void> => ipcRenderer.invoke('server:set', url)
  },
  saveFile: (defaultName: string, contents: string): Promise<string | null> =>
    ipcRenderer.invoke('file:save', defaultName, contents)
}

contextBridge.exposeInMainWorld('aib', bridge)

export type AibBridge = typeof bridge
