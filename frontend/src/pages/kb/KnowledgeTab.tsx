import { useEffect, useState } from "react";
import { Button, Card, Empty, Space, Table, Tag, Typography, message } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useOutletContext } from "react-router-dom";
import { api, type KnowledgeItem } from "@/services/api";
import type { KbOutletContext } from "./context";

const { Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  stable: "green",
  draft: "orange",
  "needs-review": "gold",
  deprecated: "red",
};

export default function KnowledgeTab() {
  const { kb } = useOutletContext<KbOutletContext>();
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    try {
      setItems(await api.listKnowledge(kb.id));
    } catch (error) {
      message.error(String(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, [kb.id]);

  return (
    <Card
      title="业务知识"
      extra={
        <Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()}>
          刷新
        </Button>
      }
    >
      {items.length === 0 && !loading ? (
        <Empty description="还没有业务知识" />
      ) : (
        <Table
          loading={loading}
          size="small"
          rowKey="concept_id"
          pagination={false}
          dataSource={items}
          columns={[
            { title: "标题", dataIndex: "title" },
            { title: "概念", dataIndex: "concept_id" },
            {
              title: "状态",
              dataIndex: "status",
              render: (value: string | null) => (
                <Tag color={STATUS_COLORS[value ?? ""] ?? "default"}>{value ?? "unknown"}</Tag>
              ),
            },
            {
              title: "验证",
              dataIndex: "verified",
              render: (value: boolean) =>
                value ? <Tag color="green">verified</Tag> : <Tag>未验证</Tag>,
            },
            {
              title: "血缘来源",
              dataIndex: "sources",
              render: (sources: string[]) =>
                sources.length === 0 ? (
                  <Text type="secondary">-</Text>
                ) : (
                  <Space size={[4, 4]} wrap>
                    {sources.map((source) => (
                      <Tag key={source}>{source}</Tag>
                    ))}
                  </Space>
                ),
            },
          ]}
        />
      )}
    </Card>
  );
}
