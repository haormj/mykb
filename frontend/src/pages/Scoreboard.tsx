import { useEffect, useState } from "react";
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
import { useOutletContext } from "react-router-dom";
import { api, type TrendPoint } from "@/services/api";
import type { KbOutletContext } from "./kb/context";

interface Row {
  name: string;
  A: number;
  B: number;
  time: string;
  version?: string;
}

export default function Scoreboard() {
  const { kb } = useOutletContext<KbOutletContext>();
  const [sets, setSets] = useState<string[]>([]);
  const [selected, setSelected] = useState<string>();
  const [trend, setTrend] = useState<TrendPoint[]>([]);

  useEffect(() => {
    void (async () => {
      try {
        const values = await api.listEvalSets(kb.id);
        setSets(values);
        setSelected((prev) => prev ?? values[0]);
      } catch {
        // empty state covers the failure
      }
    })();
  }, [kb.id]);

  useEffect(() => {
    if (!selected) return;
    void (async () => {
      try {
        setTrend(await api.trend(kb.id, selected));
      } catch {
        setTrend([]);
      }
    })();
  }, [kb.id, selected]);

  const rows: Row[] = trend.map((point, index) => ({
    name: `第 ${index + 1} 次`,
    A: Number((point.a_score * 100).toFixed(1)),
    B: Number((point.b_score * 100).toFixed(1)),
    time: point.created_at,
    version: point.knowledge_version,
  }));

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title="分数看板"
        extra={
          <Select
            style={{ width: 220 }}
            placeholder="选择评测集"
            value={selected}
            onChange={setSelected}
            options={sets.map((value) => ({ label: value, value }))}
          />
        }
      >
        {rows.length === 0 ? (
          <Empty description="暂无分数数据" />
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <LineChart data={rows} margin={{ top: 8, right: 24, left: 0, bottom: 8 }}>
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

      <Card title="运行记录">
        <Table
          rowKey={(record) => `${record.time}-${record.name}`}
          dataSource={rows}
          pagination={false}
          columns={[
            { title: "次数", dataIndex: "name", width: 100 },
            { title: "时间", dataIndex: "time" },
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
              title: "知识版本",
              dataIndex: "version",
              render: (value?: string) => <code>{(value ?? "unversioned").slice(0, 12)}</code>,
            },
          ]}
        />
      </Card>
    </Space>
  );
}
