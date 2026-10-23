export interface AibBridge {
  tokens: {
    get(): Promise<string | null>
    set(value: string): Promise<void>
    clear(): Promise<void>
  }
  server: {
    get(): Promise<string>
    set(url: string): Promise<void>
  }
  saveFile(defaultName: string, contents: string): Promise<string | null>
}

declare global {
  interface Window {
    aib: AibBridge
  }
}
