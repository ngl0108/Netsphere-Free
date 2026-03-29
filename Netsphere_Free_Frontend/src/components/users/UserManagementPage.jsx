import React, { useState, useEffect } from 'react';
import { SDNService } from '../../api/services';
import { useAuth } from '../../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import { t } from '../../i18n';
import { InlineEmpty, InlineLoading, SectionCard } from '../common/PageState';
import {
    Users, Plus, Edit2, Trash2, RefreshCw, Shield,
    Check, X, AlertTriangle
} from 'lucide-react';

const UserManagementPage = () => {
    const { isAdmin, user: currentUser } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();

    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingUser, setEditingUser] = useState(null);
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        full_name: '',
        password: '',
        role: 'viewer',
        is_active: true,
        mfa_enabled: false,
    });

    // [RBAC] Access Control: Redirect non-admins
    useEffect(() => {
        if (!isAdmin()) {
            toast.error(t('user_mgmt_access_denied'));
            navigate('/');
        }
    }, [isAdmin, navigate, toast]);

    // Fetch users
    const fetchUsers = async () => {
        setLoading(true);
        try {
            const res = await SDNService.getUsers();
            setUsers(res.data);
        } catch (err) {
            console.error(t('user_mgmt_failed_fetch_users'), err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchUsers();
    }, []);

    // Open modal for create/edit
    const openModal = (user = null) => {
        if (user) {
            setEditingUser(user);
            setFormData({
                username: user.username,
                email: user.email || '',
                full_name: user.full_name || '',
                password: '', // Don't show password
                role: user.role,
                is_active: user.is_active,
                mfa_enabled: !!user.mfa_enabled,
            });
        } else {
            setEditingUser(null);
            setFormData({
                username: '',
                email: '',
                full_name: '',
                password: '',
                role: 'viewer',
                is_active: true,
                mfa_enabled: false,
            });
        }
        setShowModal(true);
    };

    // Handle form submit
    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            // Clean up empty optional fields to avoid validation errors
            const cleanData = {
                username: formData.username,
                password: formData.password,
                role: formData.role,
                is_active: formData.is_active,
                mfa_enabled: !!formData.mfa_enabled,
            };
            // Only include optional fields if they have values
            if (formData.email && formData.email.trim()) {
                cleanData.email = formData.email.trim();
            }
            if (formData.full_name && formData.full_name.trim()) {
                cleanData.full_name = formData.full_name.trim();
            }

            if (editingUser) {
                // Update existing user
                const updateData = { ...cleanData };
                if (!updateData.password) delete updateData.password; // Don't update if empty
                delete updateData.username; // Cannot change username
                await SDNService.updateUser(editingUser.id, updateData);
            } else {
                // Create new user
                await SDNService.createUser(cleanData);
            }
            setShowModal(false);
            fetchUsers();
        } catch (err) {
            console.error(t('user_mgmt_failed_save_user'), err);
            // Show more detailed error message
            const detail = err.response?.data?.detail;
            const msg = (typeof detail === 'object')
                ? JSON.stringify(detail, null, 2)
                : (detail || t('user_mgmt_failed_save_user'));
            toast.error(String(msg).slice(0, 800));
        }
    };

    // Handle delete
    const handleDelete = async (userId, username) => {
        if (username === currentUser?.username) {
            toast.warning(t('user_mgmt_cannot_delete_own'));
            return;
        }
        if (window.confirm(t('user_mgmt_delete_confirm').replace('{username}', String(username || '')))) {
            try {
                await SDNService.deleteUser(userId);
                fetchUsers();
            } catch (err) {
                console.error(t('user_mgmt_failed_delete_user'), err);
                toast.error(err.response?.data?.detail || t('user_mgmt_failed_delete_user'));
            }
        }
    };

    // Role badge color (3-Tier)
    const getRoleBadge = (role) => {
        const colors = {
            admin: 'bg-red-500/20 text-red-400 border-red-500/30',
            operator: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
            viewer: 'bg-gray-500/20 text-gray-600 dark:text-gray-400 border-gray-500/30'
        };
        const labels = {
            admin: t('role_admin', 'Administrator'),
            operator: t('role_operator', 'Operator'),
            viewer: t('role_viewer', 'Viewer')
        };
        return (
            <span className={`px-2 py-1 text-xs font-medium rounded-full border ${colors[role] || colors.viewer}`}>
                {labels[role] || role}
            </span>
        );
    };

    return (
        <div className="h-full min-h-0 overflow-y-auto p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012]">
            {/* Header */}
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center mb-6">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-600/20 rounded-lg">
                        <Users className="text-blue-400" size={24} />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold text-gray-900 dark:text-white">{t('user_mgmt_title')}</h1>
                        <p className="text-sm text-gray-500">{t('user_mgmt_desc')}</p>
                    </div>
                </div>

                <div className="flex gap-3 flex-wrap">
                    <button
                        onClick={fetchUsers}
                        className="h-10 w-10 inline-flex items-center justify-center rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 transition-colors"
                    >
                        <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    </button>
                    <button
                        onClick={() => openModal()}
                        className="h-10 inline-flex items-center gap-2 px-4 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
                    >
                        <Plus size={18} />
                        {t('user_mgmt_add_user')}
                    </button>
                </div>
            </div>

            {/* User Table */}
            <SectionCard className="overflow-hidden shadow-sm">
                <table className="w-full">
                    <thead className="bg-gray-100 dark:bg-[#25282c]">
                        <tr>
                            <th className="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">{t('user_mgmt_table_user')}</th>
                            <th className="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">{t('user_mgmt_table_role')}</th>
                            <th className="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">{t('user_mgmt_table_status')}</th>
                            <th className="px-6 py-4 text-right text-xs font-bold text-gray-500 uppercase tracking-wider">{t('user_mgmt_table_actions')}</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {loading ? (
                            <tr>
                                <td colSpan="4" className="px-6 py-10">
                                    <InlineLoading label={t('user_mgmt_loading_users')} />
                                </td>
                            </tr>
                        ) : users.length === 0 ? (
                            <tr>
                                <td colSpan="4" className="px-6 py-10">
                                    <InlineEmpty label={t('user_mgmt_no_users')} />
                                </td>
                            </tr>
                        ) : (
                            users.map((u) => (
                                <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors border-b border-gray-100 dark:border-gray-800/50">
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-600 to-blue-400 flex items-center justify-center text-white font-bold text-sm">
                                                {(u.full_name || u.username).substring(0, 2).toUpperCase()}
                                            </div>
                                            <div>
                                                <div className="text-sm font-medium text-gray-900 dark:text-white">{u.full_name || u.username}</div>
                                                <div className="text-xs text-gray-600 dark:text-gray-500">{u.email || u.username}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        {getRoleBadge(u.role)}
                                    </td>
                                    <td className="px-6 py-4">
                                        {u.is_active ? (
                                            <span className="flex items-center gap-1 text-green-600 dark:text-green-400 text-sm">
                                                <Check size={14} /> {t('user_mgmt_active')}
                                            </span>
                                        ) : (
                                            <span className="flex items-center gap-1 text-red-600 dark:text-red-400 text-sm">
                                                <X size={14} /> {t('user_mgmt_inactive')}
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <button
                                            onClick={() => openModal(u)}
                                            className="p-2 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-500/20 text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors mr-2"
                                            title={t('user_mgmt_edit')}
                                        >
                                            <Edit2 size={16} />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(u.id, u.username)}
                                            className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/20 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                                            title={t('user_mgmt_delete')}
                                            disabled={u.username === currentUser?.username}
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </SectionCard>

            {/* Modal */}
            {showModal && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 p-6 w-full max-w-md shadow-2xl">
                        <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                            <Shield className="text-blue-400" size={20} />
                            {editingUser ? t('user_mgmt_edit_user') : t('user_mgmt_create_user')}
                        </h2>

                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">{t('user_mgmt_username_required')}</label>
                                <input
                                    type="text"
                                    required
                                    value={formData.username}
                                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                    disabled={!!editingUser} // Cannot change username
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">{t('user_mgmt_full_name')}</label>
                                <input
                                    type="text"
                                    value={formData.full_name}
                                    onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">{t('user_mgmt_email')}</label>
                                <input
                                    type="email"
                                    value={formData.email}
                                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">
                                    {editingUser ? t('user_mgmt_new_password_optional') : t('user_mgmt_password_required')}
                                </label>
                                <input
                                    type="password"
                                    required={!editingUser}
                                    value={formData.password}
                                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">{t('user_mgmt_role_required')}</label>
                                <select
                                    value={formData.role}
                                    onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                >
                                    <option value="viewer">{t('user_mgmt_role_viewer')}</option>
                                    <option value="operator">{t('user_mgmt_role_operator')}</option>
                                    <option value="admin">{t('user_mgmt_role_admin')}</option>
                                </select>
                            </div>

                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="is_active"
                                    checked={formData.is_active}
                                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                    className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-blue-600 focus:ring-blue-500"
                                />
                                <label htmlFor="is_active" className="text-sm text-gray-600 dark:text-gray-400">{t('user_mgmt_active_account')}</label>
                            </div>

                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="mfa_enabled"
                                    checked={!!formData.mfa_enabled}
                                    onChange={(e) => setFormData({ ...formData, mfa_enabled: e.target.checked })}
                                    disabled={!formData.email}
                                    className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-blue-600 focus:ring-blue-500"
                                />
                                <label htmlFor="mfa_enabled" className="text-sm text-gray-600 dark:text-gray-400">{t('user_mgmt_enable_2fa')}</label>
                            </div>

                            <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-800">
                                <button
                                    type="button"
                                    onClick={() => setShowModal(false)}
                                    className="px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-white rounded-lg font-medium transition-colors"
                                >
                                    {t('common_cancel')}
                                </button>
                                <button
                                    type="submit"
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
                                >
                                    {editingUser ? t('user_mgmt_save_changes') : t('user_mgmt_create_user_btn')}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default UserManagementPage;
