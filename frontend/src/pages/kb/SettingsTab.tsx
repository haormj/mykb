import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Form,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useNavigate, useOutletContext } from "react-router-dom";
import { api, type Member } from "@/services/api";
import { assignableRoles, canManageMember, type KbOutletContext } from "./context";

const { Text } = Typography;

export default function SettingsTab() {
  const { kb, members, refresh, canAdmin, isOwner } = useOutletContext<KbOutletContext>();
  const navigate = useNavigate();
  const [basicForm] = Form.useForm();
  const [remoteForm] = Form.useForm();
  const [addForm] = Form.useForm();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    basicForm.setFieldsValue({ name: kb.name, git_branch: kb.git_branch });
  }, [basicForm, kb.name, kb.git_branch]);

  const roleOptions = assignableRoles(kb.my_role).map((role) => ({
    label: role,
    value: role,
  }));

  const run = async (action: () => Promise<unknown>, success: string) => {
    setSaving(true);
    try {
      await action();
      message.success(success);
      await refresh();
    } catch (error) {
      message.error(String(error));
    } finally {
      setSaving(false);
    }
  };

  const addMember = async (values: { username: string; role: string }) => {
    await run(() => api.addMember(kb.id, values), "成员已添加");
    addForm.resetFields();
  };

  const canManage = (member: Member): boolean =>
    canManageMember(kb.my_role, member.role, canAdmin);

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card title="基本信息">
        <Form
          form={basicForm}
          layout="vertical"
          disabled={!canAdmin || saving}
          onFinish={(values) =>
            void run(
              () =>
                api.patchKb(kb.id, {
                  name: values.name,
                  git_branch: values.git_branch,
                }),
              "设置已保存",
            )
          }
        >
          <Space wrap align="end">
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input style={{ width: 260 }} />
            </Form.Item>
            <Form.Item name="git_branch" label="分支">
              <Input style={{ width: 200 }} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit">
                保存
              </Button>
            </Form.Item>
          </Space>
        </Form>
        {!canAdmin && <Text type="secondary">仅 admin 及以上可修改基本设置。</Text>}
        <Divider />
        <Descriptions column={1} size="small">
          <Descriptions.Item label="标识">{kb.slug}</Descriptions.Item>
          <Descriptions.Item label="本地路径">{kb.local_path}</Descriptions.Item>
          <Descriptions.Item label="远程状态">
            <Tag color={kb.has_remote ? "green" : "default"}>
              {kb.has_remote ? "已配置远程" : "仅本地"}
            </Tag>
            <Text type="secondary">审核合并与导入时会自动推送</Text>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="远程仓库">
        <Descriptions column={1} size="small" style={{ marginBottom: 12 }}>
          <Descriptions.Item label="Git 仓库">{kb.git_url ?? "未配置"}</Descriptions.Item>
          <Descriptions.Item label="分支">{kb.git_branch}</Descriptions.Item>
        </Descriptions>
        {isOwner ? (
          <Form
            form={remoteForm}
            layout="vertical"
            onFinish={(values) =>
              void run(
                () =>
                  api.bindRemote(kb.id, {
                    git_url: values.git_url,
                    git_branch: values.git_branch || undefined,
                    git_token: values.git_token || undefined,
                  }),
                "远程仓库已绑定",
              )
            }
          >
            <Space wrap align="end">
              <Form.Item
                name="git_url"
                label="远程地址"
                rules={[{ required: true, message: "请输入远程地址" }]}
                extra="为保证安全，仅允许绑定空远程仓库"
              >
                <Input style={{ width: 360 }} placeholder="https://git.example.com/team/kb.git" />
              </Form.Item>
              <Form.Item name="git_branch" label="分支">
                <Input style={{ width: 160 }} placeholder={kb.git_branch} />
              </Form.Item>
              <Form.Item name="git_token" label="访问令牌">
                <Input.Password style={{ width: 200 }} />
              </Form.Item>
              <Form.Item>
                <Button type="primary" htmlType="submit" loading={saving}>
                  绑定
                </Button>
              </Form.Item>
            </Space>
          </Form>
        ) : (
          <Alert type="info" showIcon message="仅 owner 可绑定或修改远程仓库。" />
        )}
      </Card>

      <Card title="成员">
        {canAdmin && (
          <Form
            form={addForm}
            layout="inline"
            style={{ marginBottom: 16 }}
            onFinish={(values) => void addMember(values)}
            initialValues={{ role: "viewer" }}
          >
            <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
              <Input placeholder="用户名" style={{ width: 200 }} />
            </Form.Item>
            <Form.Item name="role">
              <Select style={{ width: 140 }} options={roleOptions} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={saving}>
                添加成员
              </Button>
            </Form.Item>
          </Form>
        )}
        <Table
          size="small"
          rowKey="user_id"
          pagination={false}
          dataSource={members}
          columns={[
            { title: "用户名", dataIndex: "username" },
            { title: "显示名", dataIndex: "display_name" },
            {
              title: "角色",
              dataIndex: "role",
              render: (role: string, member) => {
                if (member.role === "owner" || !canManage(member)) {
                  return <Tag>{role}</Tag>;
                }
                return (
                  <Select
                    size="small"
                    style={{ width: 120 }}
                    value={member.role}
                    options={roleOptions}
                    disabled={saving}
                    onChange={(value) =>
                      void run(() => api.updateMember(kb.id, member.user_id, value), "角色已更新")
                    }
                  />
                );
              },
            },
            {
              title: "操作",
              key: "actions",
              render: (_value, member) => {
                if (member.role === "owner") {
                  return <Tag color="gold">owner</Tag>;
                }
                return (
                  <Space>
                    {isOwner && (
                      <Popconfirm
                        title={`将所有权转让给 ${member.username}？`}
                        onConfirm={() =>
                          void run(() => api.transferOwner(kb.id, member.user_id), "所有权已转让")
                        }
                      >
                        <Button size="small" type="link">
                          转让 owner
                        </Button>
                      </Popconfirm>
                    )}
                    {canManage(member) && (
                      <Popconfirm
                        title={`移除成员 ${member.username}？`}
                        onConfirm={() =>
                          void run(() => api.removeMember(kb.id, member.user_id), "成员已移除")
                        }
                      >
                        <Button size="small" type="link" danger>
                          移除
                        </Button>
                      </Popconfirm>
                    )}
                  </Space>
                );
              },
            },
          ]}
        />
      </Card>

      {isOwner && (
        <Card title="危险操作">
          <Space direction="vertical">
            <Text type="secondary">删除知识库会移除其成员关系，并把本地仓库移入回收目录。</Text>
            <Popconfirm
              title="确认删除该知识库？"
              description="该操作不可撤销。"
              okText="删除"
              okButtonProps={{ danger: true }}
              onConfirm={() =>
                void run(async () => {
                  await api.deleteKb(kb.id);
                  navigate("/kbs");
                }, "知识库已删除")
              }
            >
              <Button danger>删除知识库</Button>
            </Popconfirm>
          </Space>
        </Card>
      )}
    </Space>
  );
}
