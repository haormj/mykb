import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd";
import { ReloadOutlined, StopOutlined, UploadOutlined } from "@ant-design/icons";
import { useOutletContext } from "react-router-dom";
import {
  api,
  isActiveTask,
  type DocumentItem,
  type ImportTask,
} from "@/services/api";
import type { KbOutletContext } from "./context";

const { Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  queued: "default",
  running: "processing",
  succeeded: "green",
  partial: "orange",
  failed: "red",
  cancelled: "default",
};

export default function DocumentsTab() {
  const { kb, canWrite } = useOutletContext<KbOutletContext>();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [tasks, setTasks] = useState<ImportTask[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [uploading, setUploading] = useState(false);

  const hasActive = tasks.some(isActiveTask);

  const refresh = useCallback(async () => {
    const [docs, taskList] = await Promise.all([
      api.listDocuments(kb.id),
      api.listImportTasks(kb.id),
    ]);
    setDocuments(docs);
    setTasks(taskList);
  }, [kb.id]);

  useEffect(() => {
    void refresh().catch((error) => message.error(String(error)));
  }, [refresh]);

  useEffect(() => {
    if (!hasActive) {
      return;
    }
    const timer = window.setInterval(() => {
      void refresh().catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [hasActive, refresh]);

  const submitImport = async () => {
    const files = fileList.map((item) => item.originFileObj).filter(Boolean) as File[];
    if (files.length === 0) {
      message.warning("请选择要导入的文件");
      return;
    }
    setUploading(true);
    try {
      await api.createImportTask(kb.id, files);
      message.success("已创建导入任务");
      setImportOpen(false);
      setFileList([]);
      await refresh();
    } catch (error) {
      message.error(String(error));
    } finally {
      setUploading(false);
    }
  };

  const cancelTask = async (taskId: string) => {
    try {
      await api.cancelImportTask(kb.id, taskId);
      message.success("任务已取消");
      await refresh();
    } catch (error) {
      message.error(String(error));
    }
  };

  return (
    <Card
      title="已导入文档"
      extra={
        <Space>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()}>
            刷新
          </Button>
          {canWrite && (
            <Button
              type="primary"
              size="small"
              icon={<UploadOutlined />}
              onClick={() => setImportOpen(true)}
            >
              导入文档
            </Button>
          )}
        </Space>
      }
    >
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        {documents.length === 0 ? (
          <Empty description="还没有导入文档" />
        ) : (
          <Table
            size="small"
            rowKey="concept_id"
            pagination={false}
            dataSource={documents}
            columns={[
              { title: "标题", dataIndex: "title" },
              { title: "概念", dataIndex: "concept_id" },
              {
                title: "来源",
                dataIndex: "resource",
                render: (value: string | null) => (
                  <Text type="secondary" ellipsis style={{ maxWidth: 260 }}>
                    {value ?? "-"}
                  </Text>
                ),
              },
              {
                title: "导入任务",
                dataIndex: "import_task_id",
                render: (value: string | null) =>
                  value ? <Text code>{value.slice(0, 8)}</Text> : "-",
              },
            ]}
          />
        )}

        <Card size="small" title="导入任务">
          {tasks.length === 0 ? (
            <Empty description="暂无导入任务" />
          ) : (
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={tasks}
              columns={[
                {
                  title: "任务",
                  dataIndex: "id",
                  render: (value: string) => <Text code>{value.slice(0, 8)}</Text>,
                },
                {
                  title: "状态",
                  dataIndex: "status",
                  render: (value: string) => (
                    <Tag color={STATUS_COLORS[value] ?? "default"}>{value}</Tag>
                  ),
                },
                {
                  title: "结果",
                  key: "counts",
                  render: (_value, task) => (
                    <Text type="secondary">
                      新增 {task.added} / 更新 {task.updated} / 跳过 {task.skipped} / 失败{" "}
                      {task.failed} / 共 {task.total}
                    </Text>
                  ),
                },
                {
                  title: "操作",
                  key: "actions",
                  render: (_value, task) =>
                    canWrite && isActiveTask(task) ? (
                      <Button
                        size="small"
                        danger
                        icon={<StopOutlined />}
                        onClick={() => void cancelTask(task.id)}
                      >
                        取消
                      </Button>
                    ) : task.error ? (
                      <Text type="danger" ellipsis style={{ maxWidth: 200 }}>
                        {task.error}
                      </Text>
                    ) : null,
                },
              ]}
            />
          )}
        </Card>
      </Space>

      <Modal
        title="导入文档"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={() => void submitImport()}
        confirmLoading={uploading}
        okText="开始导入"
        destroyOnClose
      >
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Text type="secondary">支持 Markdown（.md/.markdown）或包含 Markdown 的 zip。</Text>
          <Upload
            multiple
            accept=".md,.markdown,.zip"
            beforeUpload={() => false}
            fileList={fileList}
            onChange={({ fileList: next }) => setFileList(next)}
          >
            <Button icon={<UploadOutlined />}>选择文件</Button>
          </Upload>
        </Space>
      </Modal>
    </Card>
  );
}
