import { useState } from "react";
import { Button, Card, Form, Input, Segmented, Typography, message } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import { api, setToken } from "@/services/api";

const { Title, Text } = Typography;

export default function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [loading, setLoading] = useState(false);

  const submit = async (values: { username: string; password: string }) => {
    setLoading(true);
    try {
      const result =
        mode === "login"
          ? await api.login(values.username, values.password)
          : await api.register(values.username, values.password);
      setToken(result.token);
      const from = (location.state as { from?: string } | null)?.from ?? "/kbs";
      navigate(from, { replace: true });
    } catch (error) {
      message.error(String(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f6f8fa",
      }}
    >
      <Card style={{ width: 380 }}>
        <Title level={3} style={{ marginBottom: 4 }}>
          mykb
        </Title>
        <Text type="secondary">企业知识管理平台</Text>
        <Segmented
          block
          style={{ margin: "16px 0" }}
          value={mode}
          onChange={(value) => setMode(value as "login" | "register")}
          options={[
            { label: "登录", value: "login" },
            { label: "注册", value: "register" },
          ]}
        />
        <Form layout="vertical" onFinish={(values) => void submit(values)}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>
            {mode === "login" ? "登录" : "注册并登录"}
          </Button>
        </Form>
      </Card>
    </div>
  );
}
