import { useEffect, useState } from "react";
import { Avatar, Button, Layout, Menu, Space, Typography } from "antd";
import type { MenuProps } from "antd";
import { BookOutlined, LogoutOutlined, UserOutlined } from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, clearToken, type CurrentUser } from "@/services/api";

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

const NAV_KEYS = ["/kbs"];

const items: MenuProps["items"] = [
  { key: "/kbs", icon: <BookOutlined />, label: "知识库" },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        setUser(await api.me());
      } catch {
        clearToken();
        navigate("/login", { replace: true });
      }
    };
    void load();
  }, [navigate]);

  const selected = NAV_KEYS.find((key) => location.pathname.startsWith(key)) ?? "/kbs";

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      navigate("/login", { replace: true });
    }
  };

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
            justifyContent: "space-between",
          }}
        >
          <span className="header-title">企业知识管理平台</span>
          <Space>
            <Avatar size="small" icon={<UserOutlined />} />
            <Text>{user?.display_name ?? user?.username ?? ""}</Text>
            <Button size="small" icon={<LogoutOutlined />} onClick={() => void logout()}>
              退出
            </Button>
          </Space>
        </Header>
        <Content style={{ padding: 24, background: "#f6f8fa" }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
