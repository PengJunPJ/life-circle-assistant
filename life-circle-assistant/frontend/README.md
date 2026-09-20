# 前端运行说明

这是一个 Vite 源码项目，不能通过双击 `index.html` 的方式运行。浏览器对 `file://` 页面中的 ES module 有跨源限制，直接打开会导致 `/src/main.ts` 加载失败。

## 开发模式

```bash
npm install
npm run dev
```

打开 <http://localhost:5173>。

## 预览构建产物

```bash
npm run build
npm run serve
```

打开 <http://localhost:4173>。

