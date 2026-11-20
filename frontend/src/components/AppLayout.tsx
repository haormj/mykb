import { Layout, Menu } from "antd";
import type { MenuProps } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { BarChartOutlined, ExperimentOutlined, SafetyCertificateOutlined } from "@ant-design/icons";

const { Header, Sider, Content } = Layout;

const NAV_KEYS = ["/evals", "/review", "/scores"];

const items: MenuProps["items"] = [
  { key: "/evals", icon: <ExperimentOutlined />, label: "评测集" },
  { key: "/review", icon: <SafetyCertificateOutlined />, label: "草稿审核" },
  { key: "/scores", icon: <BarChartOutlined />, label: "分数看板" },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const selected = NAV_KEYS.find((key) => location.pathname.startsWith(key)) ?? "/evals";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" width={220} style={{ borderRight: "1px solid #f0f0f0" }}>
        <div className="brand">mykb</div>
        <Menu
          mode="inline"
          selectedKeys={[selected]}
          items={items}
          onClick={(event) => navigate(event.key)}
          style={{ borderInlineEnd: 0 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: "#fff",
            borderBottom: "1px solid #f0f0f0",
            paddingInline: 24,
            display: "flex",
            alignItems: "center",
          }}
        >
          <span className="header-title">企业知识管理平台</span>
        </Header>
        <Content style={{ padding: 24, background: "#f6f8fa" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
