import React from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("missing #root element");
}

createRoot(rootElement).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{ token: { colorPrimary: "#1890ff", borderRadius: 8 } }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);
