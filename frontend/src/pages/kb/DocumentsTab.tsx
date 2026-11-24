import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Empty,
  Input,
  Modal,
  Space,
  Spin,
  Table,
  Tag,
  Tree,
  Typography,
  Upload,
  message,
} from "antd";
import type { TreeDataNode, UploadFile } from "antd";
import {
  DeleteOutlined,
  ReloadOutlined,
  StopOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useOutletContext } from "react-router-dom";
import MarkdownView from "@/components/MarkdownView";
import { filterTree, buildTree, type TreeNode } from "@/lib/tree";
import {
  api,
  isActiveTask,
  type DocumentItem,
  type ImportTask,
  type ReviewMr,
} from "@/services/api";
import type { KbOutletContext } from "./context";

const { Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  queued: "default",
  running: "processing",
  converting: "processing",
  "queued-for-review": "blue",
  reviewing: "purple",
  merged: "green",
  rejected: "default",
  succeeded: "green",
  partial: "orange",
  failed: "red",
  cancelled: "default",
};

const FILE_KEY_PREFIX = "file:";

function toDataNode(node: TreeNode<DocumentItem>): TreeDataNode {
  return {
    key: node.key,
    isLeaf: node.isLeaf,
    selectable: node.isLeaf,
    title: node.isLeaf ? (
      <span title={node.conceptId}>{node.title}</span>
    ) : (
      <Space size={6}>
        <span>{node.title}</span>
        <Text type="secondary">{node.count}</Text>
      </Space>
    ),
    children: node.children?.map(toDataNode),
  };
}

export default function DocumentsTab() {
  const { kb, canWrite } = useOutletContext<KbOutletContext>();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [tasks, setTasks] = useState<ImportTask[]>([]);
  const [mrs, setMrs] = useState<ReviewMr[]>([]);
  const [importOpen, setImportOpen] = useState(false);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [query, setQuery] = useState("");
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewMarkdown, setPreviewMarkdown] = useState<string | null>(null);
  const previewRequest = useRef(0);
  const expandedInitialized = useRef(false);

  const hasActive = tasks.some(isActiveTask) || mrs.some((mr) => mr.status === "reviewing");

  const refresh = useCallback(async () => {
    const [docs, taskList, reviewMrs] = await Promise.all([
      api.listDocuments(kb.id),
      api.listImportTasks(kb.id),
      api.listReviewMrs(kb.id),
    ]);
    setDocuments(docs);
    setTasks(taskList);
    setMrs(reviewMrs);
  }, [kb.id]);

  const fullTree = useMemo(() => buildTree(documents, "raw"), [documents]);
  const filtered = useMemo(() => filterTree(fullTree, query), [fullTree, query]);
  const treeData = useMemo(() => filtered.nodes.map(toDataNode), [filtered.nodes]);
  const displayExpandedKeys = query.trim() ? filtered.expandKeys : expandedKeys;

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

  useEffect(() => {
    if (expandedInitialized.current || documents.length === 0) {
      return;
    }
    expandedInitialized.current = true;
    setExpandedKeys(fullTree.filter((node) => !node.isLeaf).map((node) => node.key));
  }, [documents.length, fullTree]);

  useEffect(() => {
    if (selectedId && !documents.some((doc) => doc.concept_id === selectedId)) {
      previewRequest.current += 1;
      setSelectedId(null);
      setPreviewMarkdown(null);
      setPreviewLoading(false);
    }
  }, [documents, selectedId]);

  const openPreview = async (item: DocumentItem) => {
    const request = previewRequest.current + 1;
    previewRequest.current = request;
    setSelectedId(item.concept_id);
    setPreviewMarkdown(null);
    setPreviewLoading(true);
    try {
      const content = await api.getConceptContent(kb.id, item.concept_id);
      if (request !== previewRequest.current) {
        return;
      }
      setPreviewMarkdown(content.body);
    } catch (error) {
      if (request === previewRequest.current) {
        message.error(String(error));
        setSelectedId(null);
      }
    } finally {
      if (request === previewRequest.current) {
        setPreviewLoading(false);
      }
    }
  };

  const closePreview = () => {
    previewRequest.current += 1;
    setSelectedId(null);
    setPreviewMarkdown(null);
    setPreviewLoading(false);
  };

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

  const runMrAction = async (label: string, action: () => Promise<void>) => {
    try {
      await action();
      message.success(label);
      await refresh();
    } catch (error) {
      message.error(String(error));
    }
  };

  const deleteDoc = async (conceptId: string) => {
    Modal.confirm({
      title: "删除文档？",
      content: "删除会生成一个待审的文档级变更，合并后才会移除该文档及其受影响的知识。",
      okText: "生成删除变更",
      cancelText: "取消",
      onOk: () => runMrAction("已生成删除变更", () => api.deleteDocument(kb.id, conceptId)),
    });
  };

  const selectedItem = documents.find((doc) => doc.concept_id === selectedId) ?? null;

  const renderDocuments = () => {
    if (documents.length === 0) {
      return <Empty description="还没有导入文档" />;
    }
    if (query.trim() && treeData.length === 0) {
      return <Empty description="没有匹配的文档" />;
    }
    return (
      <Tree
        blockNode
        showLine
        height={360}
        treeData={treeData}
        expandedKeys={displayExpandedKeys}
        onExpand={(keys) => setExpandedKeys(keys.map(String))}
        selectedKeys={selectedId ? [`${FILE_KEY_PREFIX}${selectedId}`] : []}
        onSelect={(keys) => {
          const key = keys[0];
          if (typeof key !== "string" || !key.startsWith(FILE_KEY_PREFIX)) {
            return;
          }
          const conceptId = key.slice(FILE_KEY_PREFIX.length);
          const item = documents.find((doc) => doc.concept_id === conceptId);
          if (item) {
            void openPreview(item);
          }
        }}
      />
    );
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
        <Card size="small" title="目录">
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Input
              allowClear
              placeholder="按标题或路径过滤"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            {renderDocuments()}
          </Space>
        </Card>

        <Card size="small" title="待审变更（文档级 MR）">
          {mrs.length === 0 ? (
            <Empty description="暂无待审变更" />
          ) : (
            <Table
              size="small"
              rowKey="item_id"
              pagination={false}
              dataSource={mrs}
              columns={[
                { title: "文档", dataIndex: "concept_id" },
                {
                  title: "动作",
                  dataIndex: "action",
                  render: (value: string) => <Tag>{value}</Tag>,
                },
                {
                  title: "状态",
                  dataIndex: "status",
                  render: (value: string) => (
                    <Tag color={STATUS_COLORS[value] ?? "default"}>{value}</Tag>
                  ),
                },
                {
                  title: "操作",
                  key: "actions",
                  render: (_value: unknown, mr: ReviewMr) =>
                    canWrite && mr.status === "reviewing" ? (
                      <Space size={4}>
                        <Button
                          size="small"
                          type="primary"
                          onClick={() =>
                            void runMrAction("已合并", () => api.approveMr(kb.id, mr.item_id, "alice"))
                          }
                        >
                          合并
                        </Button>
                        <Button
                          size="small"
                          onClick={() =>
                            void runMrAction("已退回重做", () => api.redraftMr(kb.id, mr.item_id))
                          }
                        >
                          退回重做
                        </Button>
                        <Button
                          size="small"
                          danger
                          onClick={() =>
                            void runMrAction("已拒绝", () => api.rejectMr(kb.id, mr.item_id))
                          }
                        >
                          拒绝
                        </Button>
                      </Space>
                    ) : null,
                },
              ]}
            />
          )}
        </Card>

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
          <Text type="secondary">支持 Markdown（.md/.markdown）、Word（.docx）或包含它们的 zip。</Text>
          <Upload
            multiple
            accept=".md,.markdown,.docx,.zip"
            beforeUpload={() => false}
            fileList={fileList}
            onChange={({ fileList: next }) => setFileList(next)}
          >
            <Button icon={<UploadOutlined />}>选择文件</Button>
          </Upload>
        </Space>
      </Modal>

      <Drawer
        title={selectedItem?.title ?? "文档预览"}
        open={selectedItem !== null}
        onClose={closePreview}
        width={860}
        destroyOnClose
      >
        {selectedItem && (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            <Card size="small">
              <Space direction="vertical" size={6} style={{ width: "100%" }}>
                <Text code copyable>
                  {selectedItem.concept_id}
                </Text>
                <Space size={[8, 4]} wrap>
                  <Text type="secondary">来源：{selectedItem.resource ?? "-"}</Text>
                  <Text type="secondary">
                    导入任务：
                    {selectedItem.import_task_id ? (
                      <Text code>{selectedItem.import_task_id.slice(0, 8)}</Text>
                    ) : (
                      "-"
                    )}
                  </Text>
                  <Tag color={STATUS_COLORS[selectedItem.status ?? ""] ?? "default"}>
                    {selectedItem.status ?? "unknown"}
                  </Tag>
                </Space>
                {canWrite && (
                  <Button
                    danger
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={() => void deleteDoc(selectedItem.concept_id)}
                  >
                    删除
                  </Button>
                )}
              </Space>
            </Card>
            {previewLoading || previewMarkdown === null ? (
              <div style={{ padding: 48, textAlign: "center" }}>
                <Spin />
              </div>
            ) : (
              <MarkdownView
                kbId={kb.id}
                conceptId={selectedItem.concept_id}
                markdown={previewMarkdown}
              />
            )}
          </Space>
        )}
      </Drawer>
    </Card>
  );
}
