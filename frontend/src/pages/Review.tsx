import { useEffect, useState } from "react";
import { Button, Card, Empty, Input, List, Space, Tag, Typography, message } from "antd";
import { CheckOutlined, ReloadOutlined } from "@ant-design/icons";
import { api, type Draft } from "@/services/api";

const { Text } = Typography;

export default function Review() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [selected, setSelected] = useState("");
  const [diff, setDiff] = useState("");
  const [reviewer, setReviewer] = useState("alice");
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    try {
      setDrafts(await api.listDrafts());
    } catch (error) {
      message.error(String(error));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const open = async (conceptId: string) => {
    setSelected(conceptId);
    setDiff("");
    try {
      setDiff(await api.diff(conceptId));
    } catch (error) {
      message.error(String(error));
    }
  };

  const approve = async () => {
    if (!selected) return;
    setLoading(true);
    try {
      await api.approve(selected, reviewer);
      message.success("已审核并合并");
      setSelected("");
      setDiff("");
      await refresh();
    } catch (error) {
      message.error(String(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 16 }}>
      <Card
        title="待审草稿"
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()}>
            刷新
          </Button>
        }
      >
        {drafts.length === 0 ? (
          <Empty description="暂无待审草稿" />
        ) : (
          <List
            dataSource={drafts}
            renderItem={(draft) => (
              <List.Item
                onClick={() => void open(draft.concept_id)}
                style={{
                  cursor: "pointer",
                  borderRadius: 6,
                  paddingInline: 8,
                  background: selected === draft.concept_id ? "#e6f4ff" : undefined,
                }}
              >
                <List.Item.Meta
                  title={draft.title ?? draft.concept_id}
                  description={<Tag color="orange">{draft.status}</Tag>}
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      <Card
        title="草稿 diff"
        extra={
          <Space>
            <Text type="secondary">审核人</Text>
            <Input
              size="small"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              style={{ width: 120 }}
            />
            <Button
              type="primary"
              icon={<CheckOutlined />}
              loading={loading}
              disabled={!selected}
              onClick={() => void approve()}
            >
              确认合并
            </Button>
          </Space>
        }
      >
        {selected ? (
          <pre className="diff-view">{diff}</pre>
        ) : (
          <Empty description="选择左侧草稿查看 diff" />
        )}
      </Card>
    </div>
  );
}
