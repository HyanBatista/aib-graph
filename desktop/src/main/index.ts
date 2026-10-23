import { app, BrowserWindow, dialog, ipcMain, safeStorage, session, shell } from 'electron'
import { promises as fs } from 'fs'
import { join } from 'path'
import { pathToFileURL } from 'url'
import { isAllowedRequest, isAppPage, isExternalLink } from './security'

const DEFAULT_SERVER = 'http://localhost:8000'
const RENDERER_URL = process.env.ELECTRON_RENDERER_URL
const INDEX_FILE = join(__dirname, '../renderer/index.html')

// The server the renderer may talk to; kept in sync with the settings by `server:set`.
let allowedServer = DEFAULT_SERVER

// Separate profile for tests or for running two users side by side.
if (process.env.AIB_USER_DATA) app.setPath('userData', process.env.AIB_USER_DATA)

const userFile = (name: string): string => join(app.getPath('userData'), name)

async function readTokens(): Promise<string | null> {
  try {
    const raw = await fs.readFile(userFile('tokens.bin'))
    return safeStorage.isEncryptionAvailable() ? safeStorage.decryptString(raw) : raw.toString('utf8')
  } catch {
    return null
  }
}

async function writeTokens(value: string): Promise<void> {
  const data = safeStorage.isEncryptionAvailable() ? safeStorage.encryptString(value) : Buffer.from(value, 'utf8')
  await fs.writeFile(userFile('tokens.bin'), data, { mode: 0o600 })
}

async function readSettings(): Promise<{ serverUrl?: string }> {
  try {
    return JSON.parse(await fs.readFile(userFile('settings.json'), 'utf8'))
  } catch {
    return {}
  }
}

async function serverUrl(): Promise<string> {
  if (process.env.AIB_SERVER_URL) return process.env.AIB_SERVER_URL
  return (await readSettings()).serverUrl || DEFAULT_SERVER
}

function registerIpc(): void {
  ipcMain.handle('tokens:get', () => readTokens())
  ipcMain.handle('tokens:set', (_e, value: string) => writeTokens(value))
  ipcMain.handle('tokens:clear', () => fs.rm(userFile('tokens.bin'), { force: true }))
  ipcMain.handle('server:get', () => serverUrl())
  ipcMain.handle('server:set', async (_e, url: string) => {
    const settings = await readSettings()
    await fs.writeFile(userFile('settings.json'), JSON.stringify({ ...settings, serverUrl: url }))
    allowedServer = await serverUrl()
  })
  ipcMain.handle('file:save', async (event, defaultName: string, contents: string) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    const options = { defaultPath: defaultName, filters: [{ name: 'Edukors Graph', extensions: ['egf'] }] }
    const result = win ? await dialog.showSaveDialog(win, options) : await dialog.showSaveDialog(options)
    if (result.canceled || !result.filePath) return null
    await fs.writeFile(result.filePath, contents, 'utf8')
    return result.filePath
  })
}

function createWindow(): void {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    show: false,
    title: 'AIB Graph',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })
  win.once('ready-to-show', () => win.show())
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isExternalLink(url)) void shell.openExternal(url)
    return { action: 'deny' }
  })
  // The window only ever shows the app: links open in the system browser instead.
  const guard = (event: Electron.Event, url: string): void => {
    if (isAppPage(url, { rendererUrl: RENDERER_URL, indexUrl: pathToFileURL(INDEX_FILE).href })) return
    event.preventDefault()
    if (isExternalLink(url)) void shell.openExternal(url)
  }
  win.webContents.on('will-navigate', guard)
  win.webContents.on('will-redirect', guard)
  if (RENDERER_URL) {
    win.loadURL(RENDERER_URL)
  } else {
    win.loadFile(INDEX_FILE)
  }
}

/** Block renderer network requests to anything but the configured server (and the dev server). */
function restrictNetwork(): void {
  session.defaultSession.webRequest.onBeforeRequest((details, callback) => {
    callback({ cancel: !isAllowedRequest(details.url, { serverUrl: allowedServer, rendererUrl: RENDERER_URL }) })
  })
}

app.whenReady().then(async () => {
  allowedServer = await serverUrl()
  restrictNetwork()
  registerIpc()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
