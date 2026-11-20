import { useEffect, useState } from "react";
import {
  Alert,
  Card,
  Descriptions,
  Empty,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import { useParams } from "react-router-dom";
import { api, type KnowledgeBase, type Member } from "@/services/api";

const { Title, Text } = Typography;

function Placeholder({ title }: { title: string }) {
  return (
    <Card>
      <Empty description={`${title}功能将在后续阶段接入`} />
    </Card>
  );
}

export default function KnowledgeBaseDetail() {
  const { kbId = "" } = useParams();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const detail = await api.getKb(kbId);
        setKb(detail);
        setMembers(await api.listMembers(kbId));
      } catch (error) {
        message.error(String(error));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [kbId]);

  if (loading) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spin />
      </div>
    );
  }

  if (!kb) {
    return <Alert type="error" message="无法访问该知识库" showIcon />;
  }

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
        items={[
          { key: "documents", label: "文档", children: <Placeholder title="文档" /> },
          { key: "knowledge", label: "知识", children: <Placeholder title="知识" /> },
          {
            key: "settings",
            label: "设置",
            children: (
              <Space direction="vertical" size={16} style={{ width: "100%" }}>
                <Card title="基本信息">
                  <Descriptions column={1} size="small">
                    <Descriptions.Item label="标识">{kb.slug}</Descriptions.Item>
                    <Descriptions.Item label="分支">{kb.git_branch}</Descriptions.Item>
                    <Descriptions.Item label="Git 仓库">
                      {kb.git_url ?? "未配置"}
                    </Descriptions.Item>
                    <Descriptions.Item label="本地路径">{kb.local_path}</Descriptions.Item>
                  </Descriptions>
                </Card>
                <Card title="成员">
                  <Table
                    size="small"
                    rowKey="user_id"
                    pagination={false}
                    dataSource={members}
                    columns={[
                      { title: "用户名", dataIndex: "username" },
                      { title: "显示名", dataIndex: "display_name" },
                      {
                        title: "角色",
                        dataIndex: "role",
                        render: (role: string) => <Tag>{role}</Tag>,
                      },
                    ]}
                  />
                </Card>
              </Space>
            ),
          },
        ]}
      />
    </Space>
  );
}
