import React, { useState } from 'react';
import { Modal, Form, Input, message } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import type { AxiosInstance } from 'axios';

interface ChangePasswordModalProps {
    visible: boolean;
    onCancel: () => void;
    api: AxiosInstance;
    onSuccess?: () => void;
}

const ChangePasswordModal: React.FC<ChangePasswordModalProps> = ({ visible, onCancel, api, onSuccess }) => {
    const [loading, setLoading] = useState(false);
    const [form] = Form.useForm();

    const handleFinish = async (values: any) => {
        if (values.newPassword !== values.confirmPassword) {
            return message.error('两次输入的新密码不一致');
        }

        setLoading(true);
        try {
            await api.post('/api/v1/users/me/change-password', {
                old_password: values.oldPassword,
                new_password: values.newPassword
            });
            message.success('密码修改成功，请重新登录');
            form.resetFields();
            if (onSuccess) {
                onSuccess();
            }
        } catch (error: any) {
            message.error(error.response?.data?.detail || '修改失败，请检查原密码是否正确');
        } finally {
            setLoading(false);
        }
    };

    return (
        <Modal
            title="修改账户密码"
            visible={visible}
            onCancel={onCancel}
            onOk={() => form.submit()}
            confirmLoading={loading}
            destroyOnClose
        >
            <Form form={form} layout="vertical" onFinish={handleFinish}>
                <Form.Item
                    name="oldPassword"
                    label="原始密码"
                    rules={[{ required: true, message: '请输入当前使用的密码' }]}
                >
                    <Input.Password prefix={<LockOutlined />} placeholder="请输入原始密码" />
                </Form.Item>

                <Form.Item
                    name="newPassword"
                    label="新密码"
                    rules={[
                        { required: true, message: '请输入新密码' },
                        { min: 6, message: '密码长度至少为 6 位' }
                    ]}
                >
                    <Input.Password prefix={<LockOutlined />} placeholder="请输入新密码" />
                </Form.Item>

                <Form.Item
                    name="confirmPassword"
                    label="确认新密码"
                    dependencies={['newPassword']}
                    rules={[
                        { required: true, message: '请再次输入新密码以确认' },
                        ({ getFieldValue }) => ({
                            validator(_, value) {
                                if (!value || getFieldValue('newPassword') === value) {
                                    return Promise.resolve();
                                }
                                return Promise.reject(new Error('两次输入的密码不一致'));
                            },
                        }),
                    ]}
                >
                    <Input.Password prefix={<LockOutlined />} placeholder="请再次输入新密码" />
                </Form.Item>
            </Form>
        </Modal>
    );
};

export default ChangePasswordModal;
