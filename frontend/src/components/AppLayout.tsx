import { useEffect, useState } from "react";
import { Avatar, Button, Layout, Menu, Space, Typography } from "antd";
import type { MenuProps } from "antd";
import {
  BarChartOutlined,
  LogoutOutlined,
  ProfileOutlined,
  ToolOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, clearToken, type CurrentUser } from "@/services/api";

const { Header, Sider, Content } = Layout;
const { Text } = Typography;

type Section = "kbs" | "eval" | "maintenance";

function sectionOf(pathname: string): Section {
  if (pathname === "/evals" || pathname === "/scores") return "eval";
  if (pathname.startsWith("/maintenance")) return "maintenance";
  return "kbs";
}

const TOP_ITEMS: MenuProps["items"] = [
  { key: "kbs", label: "知识库" },
  { key: "eval", label: "知识评测" },
  { key: "maintenance", label: "知识维护" },
];

const TOP_DEFAULT: Record<Section, string> = {
  kbs: "/kbs",
  eval: "/scores",
  maintenance: "/maintenance",
};

const KBS_SIDER: MenuProps["items"] = [
  { key: "/kbs", icon: <UnorderedListOutlined />, label: "知识库列表" },
];

const EVAL_SIDER: MenuProps["items"] = [
  { key: "/scores", icon: <BarChartOutlined />, label: "看板" },
  { key: "/evals", icon: <ProfileOutlined />, label: "评测集" },
];

const MAINTENANCE_SIDER: MenuProps["items"] = [
  { key: "maintenance-placeholder", icon: <ToolOutlined />, label: "暂无页面", disabled: true },
];

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState<CurrentUser | null>(null);

  const section = sectionOf(location.pathname);

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

  const logout = async () => {
    try {
      await api.logout();
    } finally {
      navigate("/login", { replace: true });
    }
  };

  let siderItems: MenuProps["items"] = KBS_SIDER;
  let siderSelected: string[] = ["/kbs"];
  if (section === "eval") {
    siderItems = EVAL_SIDER;
    siderSelected = [location.pathname.startsWith("/evals") ? "/evals" : "/scores"];
  } else if (section === "maintenance") {
    siderItems = MAINTENANCE_SIDER;
    siderSelected = ["maintenance-placeholder"];
  }

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="light" width={240} style={{ borderRight: "1px solid #f0f0f0" }}>
        <div className="brand">企业知识管理平台</div>
        <Menu
          mode="inline"
          selectedKeys={siderSelected}
          items={siderItems}
          onClick={(event) => {
            if (event.key.startsWith("/")) navigate(event.key);
          }}
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
          <Menu
            mode="horizontal"
            selectedKeys={[section]}
            items={TOP_ITEMS}
            onClick={(event) => navigate(TOP_DEFAULT[event.key as Section])}
            style={{ flex: 1, borderBottom: 0 }}
          />
          <Space style={{ marginLeft: 16 }}>
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
