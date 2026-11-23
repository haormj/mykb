import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { PlusOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import { api, type KnowledgeBase } from "@/services/api";

const { Text } = Typography;

export default function KnowledgeBases() {
  const navigate = useNavigate();
  const [items, setItems] = useState<KnowledgeBase[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm();

  const refresh = async () => {
    setLoading(true);
    try {
      setItems(await api.listKbs());
    } catch (error) {
      message.error(String(error));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const create = async (values: {
    name: string;
    git_url?: string;
    git_branch?: string;
    git_token?: string;
  }) => {
    setSaving(true);
    try {
      const kb = await api.createKb({
        name: values.name,
        git_url: values.git_url || undefined,
        git_branch: values.git_branch || undefined,
        git_token: values.git_token || undefined,
      });
      message.success("知识库已创建");
      setOpen(false);
      form.resetFields();
      navigate(`/kbs/${kb.id}`);
    } catch (error) {
      message.error(String(error));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card
        title="知识库列表"
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
            新建
          </Button>
        }
      >
        {items.length === 0 && !loading ? (
          <Empty description="还没有知识库，先新建一个" />
        ) : (
          <List
            loading={loading}
            dataSource={items}
            renderItem={(kb) => (
              <List.Item
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/kbs/${kb.id}`)}
                actions={[
                  <Tag key="role" color="blue">
                    {kb.my_role}
                  </Tag>,
                  <Tag key="remote" color={kb.has_remote ? "green" : "default"}>
                    {kb.has_remote ? "已配置远程" : "仅本地"}
                  </Tag>,
                ]}
              >
                <List.Item.Meta
                  title={kb.name}
                  description={
                    <Text type="secondary">
                      {kb.slug} · {kb.git_branch}
                    </Text>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      <Modal
        title="新建知识库"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={saving}
        destroyOnClose
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => void create(values)}
          initialValues={{ git_branch: "main" }}
        >
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入知识库名称" }]}
          >
            <Input placeholder="如：财务知识库" />
          </Form.Item>
          <Form.Item
            name="git_url"
            label="Git 仓库地址（可选）"
            extra="留空则仅在本机使用 git 管理；配置后会把内容推送到该仓库"
          >
            <Input placeholder="https://git.example.com/team/kb.git" />
          </Form.Item>
          <Form.Item name="git_branch" label="分支">
            <Input />
          </Form.Item>
          <Form.Item name="git_token" label="访问令牌（可选）">
            <Input.Password placeholder="HTTPS token" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
