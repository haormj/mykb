import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Space, Spin, Tabs, Tag, Typography, message } from "antd";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  api,
  type IndexVersion,
  type KnowledgeBase,
  type Member,
  type PublishTask,
} from "@/services/api";
import { privileges, type KbOutletContext } from "./kb/context";

const { Title, Text } = Typography;

const ACTIVE_STATUSES = new Set(["queued", "building", "indexing", "activating"]);

export default function KnowledgeBaseDetail() {
  const { kbId = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [kb, setKb] = useState<KnowledgeBase | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [versions, setVersions] = useState<IndexVersion[]>([]);
  const [publishTask, setPublishTask] = useState<PublishTask | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const pollRef = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    const [detail, memberList] = await Promise.all([api.getKb(kbId), api.listMembers(kbId)]);
    setKb(detail);
    setMembers(memberList);
    setVersions(await api.listVersions(kbId));
  }, [kbId]);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearTimeout(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const poll = useCallback(
    (taskId: string) => {
      const tick = async () => {
        try {
          const task = await api.getPublishTask(kbId, taskId);
          setPublishTask(task);
          if (ACTIVE_STATUSES.has(task.status)) {
            pollRef.current = window.setTimeout(tick, 1000);
            return;
          }
          setPublishing(false);
          await refresh();
          if (task.status === "ready") {
            message.success("发布完成");
          } else if (task.status === "failed") {
            message.error(`发布失败：${task.error ?? "未知错误"}`);
          }
        } catch (err) {
          setPublishing(false);
          message.error(String(err));
        }
      };
      void tick();
    },
    [kbId, refresh],
  );

  useEffect(() => () => stopPolling(), [stopPolling]);

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

  const onPublish = async () => {
    try {
      setPublishing(true);
      const task = await api.publishKb(kbId);
      setPublishTask(task);
      poll(task.task_id);
    } catch (err) {
      setPublishing(false);
      const text = String(err);
      if (text.startsWith("409")) {
        message.warning("已有发布正在进行");
      } else {
        message.error(text);
      }
    }
  };

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
  const activeVersion = versions.find((version) => version.is_active) ?? null;

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
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
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

          <Space align="center" size={8} wrap>
            {canAdmin && (
              <Button
                type="primary"
                loading={publishing}
                disabled={publishing}
                onClick={() => void onPublish()}
              >
                发布
              </Button>
            )}
            {publishing && publishTask ? (
              <Tag color="processing">
                发布中 {publishTask.doc_completed}/{publishTask.doc_total}
              </Tag>
            ) : activeVersion ? (
              <Tag color="green">已发布 {activeVersion.git_commit.slice(0, 8)}</Tag>
            ) : (
              <Tag color="default">未发布</Tag>
            )}
            {!activeVersion && (
              <Text type="secondary">
                未发布：检索暂无结果{canAdmin ? "；点击“发布”生成检索快照。" : "。"}
              </Text>
            )}
          </Space>

          {publishTask?.status === "failed" && (
            <Alert
              type="error"
              showIcon
              message="发布失败"
              description={publishTask.error ?? "未知错误"}
            />
          )}
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
