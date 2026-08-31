# frontend — HuntAI Test 前端

React 19 + TypeScript + Vite SPA。技术栈锁定见 `docs/06_architecture_design/tech_stack_decision-v1.0.md`。
页面与路由见 `docs/06_architecture_design/frontend_design_spec-v1.0.md`。
接口契约见 `docs/07_backend_design/api_spec.md`。后端未实现的端点在 UI 标注「未开发」，不伪造成功路径。

## 本地运行

```bash
cd frontend
npm install   # 已设 legacy-peer-deps（TypeScript 7 与 typescript-eslint 8.68 的 peer 冲突）
npm run dev
```

开发服务器默认 `http://127.0.0.1:5173`，`/api` 代理到 `http://127.0.0.1:8000`。

环境变量从**仓库根** `.env` 读取（`vite.config.ts` `envDir`）。键名见根目录 `.env.example` 的 `VITE_API_BASE_URL`。

## 验证

```bash
npm run lint      # tsc -b（typed ESLint 受冻结的 typescript-eslint 不支持 TS 7 所限）
npx tsc --noEmit  # 或 npm run lint
npm run test
npm run build
```

## 约定

- 服务端状态：TanStack Query。本地 UI：Zustand。URL 筛选：React Router search params。
- 不使用 React Router loader/action。
- shadcn/ui 以源码内置于 `src/components/ui`，底层为冻结的 `radix-ui`。
