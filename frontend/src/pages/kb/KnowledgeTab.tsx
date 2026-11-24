import { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Empty,
  Input,
  Space,
  Spin,
  Tag,
  Tree,
  Typography,
  message,
} from "antd";
import type { TreeDataNode } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useOutletContext } from "react-router-dom";
import MarkdownView from "@/components/MarkdownView";
import { buildTree, filterTree, type TreeNode } from "@/lib/tree";
import { api, type KnowledgeItem } from "@/services/api";
import type { KbOutletContext } from "./context";

const { Text } = Typography;

const STATUS_COLORS: Record<string, string> = {
  stable: "green",
  draft: "orange",
  "needs-review": "gold",
  deprecated: "red",
};

const FILE_KEY_PREFIX = "file:";

function toDataNode(node: TreeNode<KnowledgeItem>): TreeDataNode {
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

export default function KnowledgeTab() {
  const { kb } = useOutletContext<KbOutletContext>();
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [expandedKeys, setExpandedKeys] = useState<string[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewMarkdown, setPreviewMarkdown] = useState<string | null>(null);
  const previewRequest = useRef(0);
  const expandedInitialized = useRef(false);

  const fullTree = useMemo(() => buildTree(items, "knowledge"), [items]);
  const filtered = useMemo(() => filterTree(fullTree, query), [fullTree, query]);
  const treeData = useMemo(() => filtered.nodes.map(toDataNode), [filtered.nodes]);
  const displayExpandedKeys = query.trim() ? filtered.expandKeys : expandedKeys;

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

  useEffect(() => {
    if (expandedInitialized.current || items.length === 0) {
      return;
    }
    expandedInitialized.current = true;
    setExpandedKeys(fullTree.filter((node) => !node.isLeaf).map((node) => node.key));
  }, [items.length, fullTree]);

  useEffect(() => {
    if (selectedId && !items.some((item) => item.concept_id === selectedId)) {
      previewRequest.current += 1;
      setSelectedId(null);
      setPreviewMarkdown(null);
      setPreviewLoading(false);
    }
  }, [items, selectedId]);

  const openPreview = async (item: KnowledgeItem) => {
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

  const selectedItem = items.find((item) => item.concept_id === selectedId) ?? null;

  const renderTree = () => {
    if (loading && items.length === 0) {
      return (
        <div style={{ padding: 48, textAlign: "center" }}>
          <Spin />
        </div>
      );
    }
    if (items.length === 0) {
      return <Empty description="还没有业务知识" />;
    }
    if (query.trim() && treeData.length === 0) {
      return <Empty description="没有匹配的知识" />;
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
          const item = items.find((entry) => entry.concept_id === conceptId);
          if (item) {
            void openPreview(item);
          }
        }}
      />
    );
  };

  return (
    <Card
      title="业务知识"
      extra={
        <Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()}>
          刷新
        </Button>
      }
    >
      <Card size="small" title="目录">
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Input
            allowClear
            placeholder="按标题或路径过滤"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {renderTree()}
        </Space>
      </Card>

      <Drawer
        title={selectedItem?.title ?? "知识预览"}
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
                  <Tag color={STATUS_COLORS[selectedItem.status ?? ""] ?? "default"}>
                    {selectedItem.status ?? "unknown"}
                  </Tag>
                  {selectedItem.verified ? (
                    <Tag color="green">verified</Tag>
                  ) : (
                    <Tag>未验证</Tag>
                  )}
                </Space>
                <Space size={[4, 4]} wrap>
                  <Text type="secondary">血缘来源：</Text>
                  {selectedItem.sources.length === 0 ? (
                    <Text type="secondary">-</Text>
                  ) : (
                    selectedItem.sources.map((source) => <Tag key={source}>{source}</Tag>)
                  )}
                </Space>
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
