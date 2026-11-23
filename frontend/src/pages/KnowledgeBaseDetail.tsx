import { useCallback, useEffect, useState } from "react";
import { Alert, Card, Space, Spin, Tabs, Tag, Typography, message } from "antd";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { api, type KnowledgeBase, type Member } from "@/services/api";
import { privileges, type KbOutletContext } from "./kb/context";

const { Title, Text } = Typography;

export default function KnowledgeBaseDetail() {
  const { kbId = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);

  const refresh = useCallback(async () => {
    const [detail, memberList] = await Promise.all([api.getKb(kbId), api.listMembers(kbId)]);
    setKb(detail);
    setMembers(memberList);
  }, [kbId]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        await refresh();
      } catch (err) {
        const text = String(err);
        setForbidden(text.startsWith("403"));
        setError(text);
        message.error(text);
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [kbId, refresh]);

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spin />
      </div>
    );
  }

  if (!kb) {
    return (
      <Alert
        type="error"
        showIcon
        message={forbidden ? "无权访问该知识库" : "无法访问该知识库"}
        description={error}
      />
    );
  }

  const { canWrite, canAdmin, isOwner } = privileges(kb.my_role);
  const context: KbOutletContext = { kb, members, refresh, canWrite, canAdmin, isOwner };

  const allTabs = [
    { key: "documents", label: "文档", visible: true },
    { key: "knowledge", label: "知识", visible: true },
    { key: "review", label: "审核", visible: canAdmin },
    { key: "settings", label: "设置", visible: canAdmin },
  ];
  const tabs = allTabs.filter((tab) => tab.visible);
  const allowedKeys = new Set(tabs.map((tab) => tab.key));
  const segment = location.pathname.split("/").filter(Boolean).pop();
  const activeKey = segment && allowedKeys.has(segment) ? segment : "documents";

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card>
        <Space align="center" size={12} wrap>
          <Title level={4} style={{ margin: 0 }}>
            {kb.name}
          </Title>
          <Tag color="blue">{kb.my_role}</Tag>
          <Tag color={kb.has_remote ? "green" : "default"}>
            {kb.has_remote ? "已配置远程" : "仅本地"}
          </Tag>
          {!kb.has_remote && <Text type="secondary">未配置远程仓库，内容仅存在本机</Text>}
        </Space>
      </Card>

      <Tabs
        activeKey={activeKey}
        onChange={(key) => navigate(`/kbs/${kbId}/${key}`)}
        items={tabs.map((tab) => ({ key: tab.key, label: tab.label }))}
      />

      {allowedKeys.has(segment ?? "") ? (
        <Outlet context={context} />
      ) : (
        <Alert type="warning" showIcon message="当前角色无权访问该页面" />
      )}
    </Space>
  );
}
