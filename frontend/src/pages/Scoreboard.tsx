import { useEffect, useMemo, useState } from "react";
import { Card, Empty, Select, Space, Table, Tag } from "antd";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type EvalOverview, type EvalRun, type TrendPoint } from "@/services/api";

interface ChartRow {
  name: string;
  A: number;
  B: number;
  time: string;
  version?: string | null;
}

function latestPerKb(runs: EvalRun[]): EvalRun[] {
  const byKb = new Map<string, EvalRun>();
  for (const run of runs) {
    const current = byKb.get(run.target_kb_id);
    if (!current || (run.created_at ?? "") > (current.created_at ?? "")) {
      byKb.set(run.target_kb_id, run);
    }
  }
  return [...byKb.values()];
}

export default function Scoreboard() {
  const [overview, setOverview] = useState<EvalOverview | null>(null);
  const [selectedSet, setSelectedSet] = useState<string>();
  const [selectedKb, setSelectedKb] = useState<string>();
  const [trend, setTrend] = useState<TrendPoint[]>([]);

  useEffect(() => {
    void (async () => {
      try {
        const data = await api.evalOverview();
        setOverview(data);
        setSelectedSet((prev) => prev ?? data.sets[0]?.id);
        setSelectedKb((prev) => prev ?? data.kbs[0]?.id);
      } catch {
        // empty state covers the failure
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedSet || !selectedKb) return;
    void (async () => {
      try {
        setTrend(await api.evalTrend(selectedSet, selectedKb));
      } catch {
        setTrend([]);
      }
    })();
  }, [selectedSet, selectedKb]);

  const setRuns = useMemo(
    () => (overview?.runs ?? []).filter((run) => run.set_id === selectedSet),
    [overview, selectedSet],
  );

  const compareRows = useMemo(() => {
    const kbName = (id: string) =>
      overview?.kbs.find((kb) => kb.id === id)?.name ?? id.slice(0, 8);
    return latestPerKb(setRuns).map((run) => ({
      key: run.target_kb_id,
      kb: kbName(run.target_kb_id),
      A: Number((run.a_score * 100).toFixed(1)),
      B: Number((run.b_score * 100).toFixed(1)),
      coverage: Number((run.coverage * 100).toFixed(1)),
      version: run.knowledge_version,
      time: run.created_at,
    }));
  }, [overview, setRuns]);

  const chartRows: ChartRow[] = trend.map((point, index) => ({
    name: `第 ${index + 1} 次`,
    A: Number((point.a_score * 100).toFixed(1)),
    B: Number((point.b_score * 100).toFixed(1)),
    time: point.created_at ?? "",
    version: point.knowledge_version,
  }));

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title="分数看板"
        extra={
          <Space wrap>
            <Select
              style={{ width: 220 }}
              placeholder="选择评测集"
              value={selectedSet}
              onChange={setSelectedSet}
              options={(overview?.sets ?? []).map((set) => ({
                label: set.title || set.name,
                value: set.id,
              }))}
            />
            <Select
              style={{ width: 200 }}
              placeholder="选择知识库"
              value={selectedKb}
              onChange={setSelectedKb}
              options={(overview?.kbs ?? []).map((kb) => ({ label: kb.name, value: kb.id }))}
            />
          </Space>
        }
      >
        {compareRows.length === 0 ? (
          <Empty description="暂无跨库分数" />
        ) : (
          <Table
            rowKey="key"
            pagination={false}
            dataSource={compareRows}
            columns={[
              { title: "知识库", dataIndex: "kb" },
              {
                title: "A 知识质量",
                dataIndex: "A",
                render: (value: number) => <Tag color="blue">{value.toFixed(1)}%</Tag>,
              },
              {
                title: "B 端到端",
                dataIndex: "B",
                render: (value: number) => <Tag color="green">{value.toFixed(1)}%</Tag>,
              },
              {
                title: "覆盖率",
                dataIndex: "coverage",
                render: (value: number) => <Tag>{value.toFixed(1)}%</Tag>,
              },
              {
                title: "知识版本",
                dataIndex: "version",
                render: (value?: string | null) => (
                  <code>{(value ?? "unversioned").slice(0, 12)}</code>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Card title="趋势">
        {chartRows.length === 0 ? (
          <Empty description="暂无分数数据" />
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={chartRows} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis domain={[0, 100]} tickFormatter={(value) => `${value}%`} />
              <Tooltip formatter={(value) => `${value}%`} />
              <Legend />
              <Line type="monotone" dataKey="A" name="A 知识质量" stroke="#1890ff" strokeWidth={2} />
              <Line type="monotone" dataKey="B" name="B 端到端" stroke="#52c41a" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>
    </Space>
  );
}
