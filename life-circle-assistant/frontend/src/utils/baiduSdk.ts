// BMap 命名空间可能在鉴权失败前就存在，不能作为底图已就绪的证据。
export function loadBaiduSdk(browserAk: string, timeoutMs = 8000): Promise<void> {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    const timer = window.setTimeout(() => {
      delete (window as any).__lifeCircleBaiduReady
      reject(new Error('百度地图初始化超时，请检查浏览器 AK 域名白名单'))
    }, timeoutMs)
    ;(window as any).__lifeCircleBaiduReady = () => {
      window.clearTimeout(timer)
      delete (window as any).__lifeCircleBaiduReady
      if (typeof (window as any).BMap?.Map !== 'function') reject(new Error('百度地图 SDK 未就绪'))
      else resolve()
    }
    script.onerror = () => {
      window.clearTimeout(timer)
      delete (window as any).__lifeCircleBaiduReady
      reject(new Error('百度地图 JavaScript API 加载失败'))
    }
    script.src = `https://api.map.baidu.com/api?v=3.0&ak=${encodeURIComponent(browserAk)}&callback=__lifeCircleBaiduReady`
    document.head.appendChild(script)
  })
}
