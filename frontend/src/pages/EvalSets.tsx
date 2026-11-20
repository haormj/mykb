import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Input,
  List,
  Space,
  Statistic,
  Typography,
  message,
} from "antd";
import { DeleteOutlined, PlayCircleOutlined, PlusOutlined } from "@ant-design/icons";
import { useOutletContext } from "react-router-dom";
import { api, type EvalCase, type EvalRun } from "@/services/api";
import type { KbOutletContext } from "./kb/context";

const { Text } = Typography;

const emptyCase: EvalCase = { question: "", reference_answer: "", expected_concept: "" };

export default function EvalSets() {
  const { kb, canWrite } = useOutletContext<KbOutletContext>();
  const [sets, setSets] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [cases, setCases] = useState<EvalCase[]>([{ ...emptyCase }]);
  const [run, setRun] = useState<EvalRun | null>(null);
  const [saving, setSaving] = useState(false);

  const refresh = async () => {
    try {
      setSets(await api.listEvalSets(kb.id));
    } catch (error) {
      message.error(String(error));
    }
  };

  useEffect(() => {
    void refresh();
  }, [kb.id]);

  const updateCase = (index: number, patch: Partial<EvalCase>) => {
    setCases((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  };
  const addCase = () => setCases((prev) => [...prev, { ...emptyCase }]);
  const removeCase = (index: number) => setCases((prev) => prev.filter((_, i) => i !== index));

  const create = async () => {
    if (!name.trim()) {
      message.warning("请填写评测集名称");
      return;
    }
    setSaving(true);
    try {
      await api.createEvalSet(kb.id, { name, title: title || undefined, cases });
      message.success("评测集已保存");
      setName("");
      setTitle("");
      setCases([{ ...emptyCase }]);
      await refresh();
    } catch (error) {
      message.error(String(error));
    } finally {
      setSaving(false);
    }
  };

  const runSet = async (setName: string) => {
    try {
      setRun(await api.runEval(kb.id, setName));
      message.success("评测完成");
    } catch (error) {
      message.error(String(error));
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      {canWrite && (
      <Card
        title="新建评测集"
        extra={<Text type="secondary">问题 + 期望答案 + 期望命中概念</Text>}
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
                  placeholder="期望命中概念 id (如 knowledge/finance/ltv)"
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
            <Button type="primary" loading={saving} onClick={() => void create()}>
              保存评测集
            </Button>
          </Space>
        </Space>
      </Card>

      )}

      <Card title="已有评测集">
        {sets.length === 0 ? (
          <Empty description="暂无评测集" />
        ) : (
          <List
            dataSource={sets}
            renderItem={(setName) => (
              <List.Item
                actions={
                  canWrite
                    ? [
                        <Button
                          key="run"
                          type="primary"
                          ghost
                          icon={<PlayCircleOutlined />}
                          onClick={() => void runSet(setName)}
                        >
                          运行评测
                        </Button>,
                      ]
                    : []
                }
              >
                <List.Item.Meta title={setName} />
              </List.Item>
            )}
          />
        )}
      </Card>

      {run && (
        <Card title={`评测结果 · ${run.set_name}`}>
          <Space size={48} wrap>
            <Statistic
              title="A · 知识质量"
              value={run.a_score}
              precision={3}
              valueStyle={{ color: "#1890ff" }}
            />
            <Statistic
              title="B · 端到端能力"
              value={run.b_score}
              precision={3}
              valueStyle={{ color: "#52c41a" }}
            />
            <Statistic
              title="知识版本"
              value={(run.knowledge_version ?? "unversioned").slice(0, 12)}
              valueStyle={{ fontSize: 14 }}
            />
          </Space>
        </Card>
      )}
    </Space>
  );
}
