'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import Link from 'next/link';
import UserMenu from '@/components/UserMenu';

interface UserProfile {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  phone_number?: string;
  nrc_number?: string;
  physical_address?: string;
  bank_account?: string;
  bank_name?: string;
  bank_branch?: string;
  first_name_next_of_kin?: string;
  last_name_next_of_kin?: string;
  phone_number_next_of_kin?: string;
}

export default function ProfilePage() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [formData, setFormData] = useState<Partial<UserProfile>>({});
  const [passwordData, setPasswordData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: ''
  });

  useEffect(() => {
    if (!user) {
      router.push('/login');
      return;
    }
    loadProfile();
  }, [user, router]);

  const loadProfile = async () => {
    try {
      const response = await api.get<UserProfile>('/api/auth/me');
      if (response.data) {
        setProfile(response.data);
        setFormData({
          first_name: response.data.first_name || '',
          last_name: response.data.last_name || '',
          phone_number: response.data.phone_number || '',
          nrc_number: response.data.nrc_number || '',
          physical_address: response.data.physical_address || '',
          bank_account: response.data.bank_account || '',
          bank_name: response.data.bank_name || '',
          bank_branch: response.data.bank_branch || '',
          first_name_next_of_kin: response.data.first_name_next_of_kin || '',
          last_name_next_of_kin: response.data.last_name_next_of_kin || '',
          phone_number_next_of_kin: response.data.phone_number_next_of_kin || '',
        });
      }
    } catch (err) {
      setError('Failed to load profile information');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setError('');
    setSuccess('');
  };

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPasswordData({ ...passwordData, [e.target.name]: e.target.value });
    setError('');
    setSuccess('');
  };

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setSaving(true);

    try {
      const response = await api.put('/api/auth/profile', formData);
      if (!response.error) {
        setSuccess('Profile updated successfully!');
        // Reload profile to get updated data
        await loadProfile();
      } else {
        setError(response.error || 'Failed to update profile');
      }
    } catch (err) {
      setError('Failed to update profile. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (passwordData.new_password !== passwordData.confirm_password) {
      setError('New passwords do not match');
      return;
    }

    if (passwordData.new_password.length < 6) {
      setError('New password must be at least 6 characters long');
      return;
    }

    setChangingPassword(true);

    try {
      const response = await api.post('/api/auth/change-password', {
        current_password: passwordData.current_password,
        new_password: passwordData.new_password
      });
      if (!response.error) {
        setSuccess('Password changed successfully!');
        setPasswordData({
          current_password: '',
          new_password: '',
          confirm_password: ''
        });
      } else {
        setError(response.error || 'Failed to change password');
      }
    } catch (err) {
      setError('Failed to change password. Please try again.');
    } finally {
      setChangingPassword(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">My Profile</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        {error && (
          <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
            {error}
          </div>
        )}

        {success && (
          <div className="mb-4 md:mb-6 bg-green-100 border-2 border-green-400 text-green-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
            {success}
          </div>
        )}

        <div className="space-y-4 md:space-y-6">
          {/* Personal Information */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Personal Information</h2>
            <form onSubmit={handleSaveProfile} className="space-y-4 md:space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                <div>
                  <label htmlFor="first_name" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    First Name
                  </label>
                  <input
                    id="first_name"
                    name="first_name"
                    type="text"
                    className="w-full"
                    value={formData.first_name || ''}
                    onChange={handleChange}
                  />
                </div>
                <div>
                  <label htmlFor="last_name" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    Last Name
                  </label>
                  <input
                    id="last_name"
                    name="last_name"
                    type="text"
                    className="w-full"
                    value={formData.last_name || ''}
                    onChange={handleChange}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="email" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  className="w-full bg-gray-100"
                  value={profile?.email || ''}
                  disabled
                />
                <p className="mt-1 text-sm text-blue-600">Email cannot be changed</p>
              </div>

              <div>
                <label htmlFor="phone_number" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Phone Number
                </label>
                <input
                  id="phone_number"
                  name="phone_number"
                  type="tel"
                  className="w-full"
                  value={formData.phone_number || ''}
                  onChange={handleChange}
                />
              </div>

              <div>
                <label htmlFor="nrc_number" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  NRC Number
                </label>
                <input
                  id="nrc_number"
                  name="nrc_number"
                  type="text"
                  className="w-full"
                  value={formData.nrc_number || ''}
                  onChange={handleChange}
                />
              </div>

              <div>
                <label htmlFor="physical_address" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Physical Address
                </label>
                <textarea
                  id="physical_address"
                  name="physical_address"
                  className="w-full min-h-[100px]"
                  value={formData.physical_address || ''}
                  onChange={handleChange}
                />
              </div>

              <button
                type="submit"
                disabled={saving}
                className="btn-primary w-full md:w-auto disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </form>
          </div>

          {/* Bank Details */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Bank Details</h2>
            <form onSubmit={handleSaveProfile} className="space-y-4 md:space-y-6">
              <div>
                <label htmlFor="bank_account" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Bank Account
                </label>
                <input
                  id="bank_account"
                  name="bank_account"
                  type="text"
                  className="w-full"
                  value={formData.bank_account || ''}
                  onChange={handleChange}
                />
              </div>

              <div>
                <label htmlFor="bank_name" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Bank Name
                </label>
                <input
                  id="bank_name"
                  name="bank_name"
                  type="text"
                  className="w-full"
                  value={formData.bank_name || ''}
                  onChange={handleChange}
                />
              </div>

              <div>
                <label htmlFor="bank_branch" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Bank Branch
                </label>
                <input
                  id="bank_branch"
                  name="bank_branch"
                  type="text"
                  className="w-full"
                  value={formData.bank_branch || ''}
                  onChange={handleChange}
                />
              </div>

              <button
                type="submit"
                disabled={saving}
                className="btn-primary w-full md:w-auto disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </form>
          </div>

          {/* Next of Kin */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Next of Kin Information</h2>
            <form onSubmit={handleSaveProfile} className="space-y-4 md:space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6">
                <div>
                  <label htmlFor="first_name_next_of_kin" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    First Name
                  </label>
                  <input
                    id="first_name_next_of_kin"
                    name="first_name_next_of_kin"
                    type="text"
                    className="w-full"
                    value={formData.first_name_next_of_kin || ''}
                    onChange={handleChange}
                  />
                </div>
                <div>
                  <label htmlFor="last_name_next_of_kin" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    Last Name
                  </label>
                  <input
                    id="last_name_next_of_kin"
                    name="last_name_next_of_kin"
                    type="text"
                    className="w-full"
                    value={formData.last_name_next_of_kin || ''}
                    onChange={handleChange}
                  />
                </div>
              </div>

              <div>
                <label htmlFor="phone_number_next_of_kin" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Phone Number
                </label>
                <input
                  id="phone_number_next_of_kin"
                  name="phone_number_next_of_kin"
                  type="tel"
                  className="w-full"
                  value={formData.phone_number_next_of_kin || ''}
                  onChange={handleChange}
                />
              </div>

              <button
                type="submit"
                disabled={saving}
                className="btn-primary w-full md:w-auto disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </form>
          </div>

          {/* Change Password */}
          <div className="card">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Change Password</h2>
            <form onSubmit={handleChangePassword} className="space-y-4 md:space-y-6">
              <div>
                <label htmlFor="current_password" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Current Password *
                </label>
                <input
                  id="current_password"
                  name="current_password"
                  type="password"
                  required
                  className="w-full"
                  value={passwordData.current_password}
                  onChange={handlePasswordChange}
                />
              </div>

              <div>
                <label htmlFor="new_password" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  New Password *
                </label>
                <input
                  id="new_password"
                  name="new_password"
                  type="password"
                  required
                  className="w-full"
                  value={passwordData.new_password}
                  onChange={handlePasswordChange}
                />
                <p className="mt-1 text-sm text-blue-600">Password must be at least 6 characters long</p>
              </div>

              <div>
                <label htmlFor="confirm_password" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Confirm New Password *
                </label>
                <input
                  id="confirm_password"
                  name="confirm_password"
                  type="password"
                  required
                  className="w-full"
                  value={passwordData.confirm_password}
                  onChange={handlePasswordChange}
                />
              </div>

              <button
                type="submit"
                disabled={changingPassword}
                className="btn-primary w-full md:w-auto disabled:opacity-50"
              >
                {changingPassword ? 'Changing Password...' : 'Change Password'}
              </button>
            </form>
          </div>
        </div>
      </main>
    </div>
  );
}
