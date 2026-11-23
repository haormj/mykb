import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  PlayCircleOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import {
  api,
  type CurrentUser,
  type EvalCase,
  type EvalRun,
  type EvalSetSummary,
  type KnowledgeBase,
} from "@/services/api";

const { Text } = Typography;

const emptyCase: EvalCase = { question: "", reference_answer: "", expected_concept: "" };
const EDIT_ROLES = new Set(["editor", "admin", "owner"]);

export default function EvalSets() {
  const [me, setMe] = useState<CurrentUser | null>(null);
  const [sets, setSets] = useState<EvalSetSummary[]>([]);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [cases, setCases] = useState<EvalCase[]>([{ ...emptyCase }]);
  const [saving, setSaving] = useState(false);

  const [runTarget, setRunTarget] = useState<EvalSetSummary | null>(null);
  const [runKbIds, setRunKbIds] = useState<string[]>([]);
  const [runResults, setRunResults] = useState<EvalRun[]>([]);
  const [running, setRunning] = useState(false);

  const editableKbs = kbs.filter((kb) => EDIT_ROLES.has(kb.my_role));

  const refresh = async () => {
    try {
      const [current, list, kbList] = await Promise.all([
        api.me(),
        api.listEvalSets(),
        api.listKbs(),
      ]);
      setMe(current);
      setSets(list);
      setKbs(kbList);
    } catch (error) {
      message.error(String(error));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const resetForm = () => {
    setEditingId(null);
    setName("");
    setTitle("");
    setCases([{ ...emptyCase }]);
  };

  const startEdit = async (set: EvalSetSummary) => {
    try {
      const detail = await api.getEvalSet(set.id);
      setEditingId(detail.id);
      setName(detail.name);
      setTitle(detail.title ?? "");
      setCases(
        detail.cases.length
          ? detail.cases.map((c) => ({
              question: c.question,
              reference_answer: c.reference_answer,
              expected_concept: c.expected_concept ?? "",
              domain: c.domain ?? "",
              difficulty: c.difficulty ?? "",
            }))
          : [{ ...emptyCase }],
      );
    } catch (error) {
      message.error(String(error));
    }
  };

  const updateCase = (index: number, patch: Partial<EvalCase>) => {
    setCases((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };
  const addCase = () => setCases((prev) => [...prev, { ...emptyCase }]);
  const removeCase = (index: number) => setCases((prev) => prev.filter((_, i) => i !== index));

  const save = async () => {
    if (!name.trim()) {
      message.warning("请填写评测集名称");
      return;
    }
    setSaving(true);
    try {
      const input = { name, title: title || undefined, cases };
      if (editingId) {
        await api.updateEvalSet(editingId, input);
        message.success("评测集已更新");
      } else {
        await api.createEvalSet(input);
        message.success("评测集已创建");
      }
      resetForm();
      await refresh();
    } catch (error) {
      message.error(String(error));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (set: EvalSetSummary) => {
    try {
      await api.deleteEvalSet(set.id);
      message.success("已删除");
      if (editingId === set.id) resetForm();
      await refresh();
    } catch (error) {
      message.error(String(error));
    }
  };

  const openRun = (set: EvalSetSummary) => {
    setRunTarget(set);
    setRunKbIds([]);
    setRunResults([]);
  };

  const submitRun = async () => {
    if (!runTarget) return;
    if (runKbIds.length === 0) {
      message.warning("请至少选择一个目标知识库");
      return;
    }
    setRunning(true);
    try {
      const runs = await api.runEvalSet(runTarget.id, runKbIds);
      setRunResults(runs);
      message.success("评测完成");
    } catch (error) {
      message.error(String(error));
    } finally {
      setRunning(false);
    }
  };

  const canManage = (set: EvalSetSummary) => me?.id === set.owner_user_id;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title={editingId ? "编辑评测集" : "新建评测集"}
        extra={<Text type="secondary">平台级题集，可复用于多个知识库</Text>}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Space wrap>
            <Input
              placeholder="名称 (如 finance-basics)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ width: 260 }}
            />
            <Input
              placeholder="标题 (可选)"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              style={{ width: 260 }}
            />
          </Space>

          {cases.map((item, index) => (
            <Card
              key={index}
              size="small"
              type="inner"
              title={`题目 ${index + 1}`}
              extra={
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => removeCase(index)}
                />
              }
            >
              <Space direction="vertical" size={8} style={{ width: "100%" }}>
                <Input
                  placeholder="问题"
                  value={item.question}
                  onChange={(e) => updateCase(index, { question: e.target.value })}
                />
                <Input
                  placeholder="期望答案"
                  value={item.reference_answer}
                  onChange={(e) => updateCase(index, { reference_answer: e.target.value })}
                />
                <Input
                  placeholder="期望命中概念 id (如 knowledge/topics/ltv)，留空则只计端到端分"
                  value={item.expected_concept ?? ""}
                  onChange={(e) => updateCase(index, { expected_concept: e.target.value })}
                />
                <Space wrap>
                  <Input
                    placeholder="领域"
                    value={item.domain ?? ""}
                    onChange={(e) => updateCase(index, { domain: e.target.value })}
                    style={{ width: 160 }}
                  />
                  <Input
                    placeholder="难度"
                    value={item.difficulty ?? ""}
                    onChange={(e) => updateCase(index, { difficulty: e.target.value })}
                    style={{ width: 160 }}
                  />
                </Space>
              </Space>
            </Card>
          ))}

          <Space>
            <Button icon={<PlusOutlined />} onClick={addCase}>
              增加题目
            </Button>
            <Button type="primary" loading={saving} onClick={() => void save()}>
              {editingId ? "保存修改" : "保存评测集"}
            </Button>
            {editingId && <Button onClick={resetForm}>取消编辑</Button>}
          </Space>
        </Space>
      </Card>

      <Card title="评测集">
        {sets.length === 0 ? (
          <Empty description="暂无评测集" />
        ) : (
          <Table
            rowKey="id"
            dataSource={sets}
            pagination={false}
            columns={[
              { title: "名称", dataIndex: "name" },
              {
                title: "标题",
                dataIndex: "title",
                render: (value?: string | null) => value ?? "-",
              },
              { title: "题目数", dataIndex: "case_count", width: 100 },
              {
                title: "操作",
                width: 280,
                render: (_value, set) => (
                  <Space wrap>
                    <Button
                      size="small"
                      type="primary"
                      ghost
                      icon={<PlayCircleOutlined />}
                      onClick={() => openRun(set)}
                    >
                      运行
                    </Button>
                    {canManage(set) && (
                      <>
                        <Button
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => void startEdit(set)}
                        >
                          编辑
                        </Button>
                        <Button
                          size="small"
                          danger
                          icon={<DeleteOutlined />}
                          onClick={() => void remove(set)}
                        >
                          删除
                        </Button>
                      </>
                    )}
                  </Space>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Modal
        open={runTarget !== null}
        title={`运行评测 · ${runTarget?.name ?? ""}`}
        okText="开始运行"
        confirmLoading={running}
        onOk={() => void submitRun()}
        onCancel={() => setRunTarget(null)}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Text type="secondary">选择目标知识库（需要 editor 及以上权限，可多选）</Text>
          {editableKbs.length === 0 ? (
            <Empty description="没有可运行的知识库" />
          ) : (
            <Checkbox.Group
              style={{ display: "flex", flexDirection: "column", gap: 8 }}
              value={runKbIds}
              onChange={(values) => setRunKbIds(values.map((value) => String(value)))}
              options={editableKbs.map((kb) => ({ label: `${kb.name} (${kb.my_role})`, value: kb.id }))}
            />
          )}

          {runResults.length > 0 && (
            <Card size="small" title="运行结果">
              <Space size={32} wrap>
                {runResults.map((run) => {
                  const kb = kbs.find((item) => item.id === run.target_kb_id);
                  return (
                    <Space key={run.id} direction="vertical">
                      <Text strong>{kb?.name ?? run.target_kb_id.slice(0, 8)}</Text>
                      <Tag color="blue">A {run.a_score.toFixed(3)}</Tag>
                      <Tag color="green">B {run.b_score.toFixed(3)}</Tag>
                      <Tag>覆盖 {(run.coverage * 100).toFixed(0)}%</Tag>
                    </Space>
                  );
                })}
              </Space>
            </Card>
          )}
        </Space>
      </Modal>
    </Space>
  );
}
