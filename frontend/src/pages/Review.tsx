import { useEffect, useState } from "react";
import { Button, Card, Empty, Input, List, Space, Tag, Typography, message } from "antd";
import { CheckOutlined, CloseOutlined, ReloadOutlined, RedoOutlined } from "@ant-design/icons";
import { useOutletContext } from "react-router-dom";
import { api, type Draft, type ReviewMr, type ReviewMrDiff } from "@/services/api";
import type { KbOutletContext } from "./kb/context";

const { Text } = Typography;

export default function Review() {
  const { kb } = useOutletContext<KbOutletContext>();
  const [mrs, setMrs] = useState<ReviewMr[]>([]);
  const [selected, setSelected] = useState("");
  const [diff, setDiff] = useState<ReviewMrDiff | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [reviewer, setReviewer] = useState("alice");
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    try {
      const [reviewMrs, legacyDrafts] = await Promise.all([
        api.listReviewMrs(kb.id),
        api.listDrafts(kb.id),
      ]);
      setMrs(reviewMrs);
      setDrafts(legacyDrafts);
    } catch (error) {
      message.error(String(error));
    }
  };

  useEffect(() => {
    void refresh();
  }, [kb.id]);

  const open = async (itemId: string) => {
    setSelected(itemId);
    setDiff(null);
    try {
      setDiff(await api.reviewMrDiff(kb.id, itemId));
    } catch (error) {
      message.error(String(error));
    }
  };

  const act = async (label: string, action: () => Promise<void>) => {
    if (!selected) return;
    setLoading(true);
    try {
      await action();
      message.success(label);
      setSelected("");
      setDiff(null);
      await refresh();
    } catch (error) {
      message.error(String(error));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 16 }}>
        <Card
          title="待审文档变更"
          extra={
            <Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()}>
              刷新
            </Button>
          }
        >
          {mrs.length === 0 ? (
            <Empty description="暂无待审变更" />
          ) : (
            <List
              dataSource={mrs}
              renderItem={(mr) => (
                <List.Item
                  onClick={() => void open(mr.item_id)}
                  style={{
                    cursor: "pointer",
                    borderRadius: 6,
                    paddingInline: 8,
                    background: selected === mr.item_id ? "#e6f4ff" : undefined,
                  }}
                >
                  <List.Item.Meta
                    title={mr.title ?? mr.concept_id}
                    description={
                      <Space size={4}>
                        <Tag>{mr.action}</Tag>
                        <Tag color="purple">{mr.status}</Tag>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          )}
        </Card>

        <Card
          title="变更 diff（源文档 + 提取结果）"
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
                onClick={() =>
                  void act("已合并", () => api.approveMr(kb.id, selected, reviewer))
                }
              >
                合并
              </Button>
              <Button
                icon={<RedoOutlined />}
                loading={loading}
                disabled={!selected}
                onClick={() => void act("已退回重做", () => api.redraftMr(kb.id, selected))}
              >
                退回重做
              </Button>
              <Button
                danger
                icon={<CloseOutlined />}
                loading={loading}
                disabled={!selected}
                onClick={() => void act("已拒绝", () => api.rejectMr(kb.id, selected))}
              >
                拒绝
              </Button>
            </Space>
          }
        >
          {selected && diff ? (
            <div>
              <Space wrap size={[4, 4]} style={{ marginBottom: 8 }}>
                {diff.files.map((file) => (
                  <Tag key={file}>{file}</Tag>
                ))}
              </Space>
              <pre className="diff-view">{diff.diff}</pre>
            </div>
          ) : (
            <Empty description="选择左侧变更查看 diff（含 raw 与受影响知识）" />
          )}
        </Card>
      </div>

      <Card title="历史草稿（逐概念）">
        {drafts.length === 0 ? (
          <Empty description="暂无草稿" />
        ) : (
          <List
            dataSource={drafts}
            renderItem={(draft) => (
              <List.Item>
                <List.Item.Meta
                  title={draft.title ?? draft.concept_id}
                  description={<Tag color="orange">{draft.status}</Tag>}
                />
                <Button
                  size="small"
                  icon={<CheckOutlined />}
                  onClick={async () => {
                    try {
                      await api.approve(kb.id, draft.concept_id, reviewer);
                      message.success("已审核并合并");
                      await refresh();
                    } catch (error) {
                      message.error(String(error));
                    }
                  }}
                >
                  确认合并
                </Button>
              </List.Item>
            )}
          />
        )}
      </Card>
    </div>
  );
}
