'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';

export default function AdminDashboard() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.push('/login');
  };
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    const response = await api.get<{ settings: Record<string, string> }>('/api/admin/settings');
    if (response.data) {
      setSettings(response.data.settings || {});
    }
    setLoading(false);
  };

  const handleSave = async () => {
    const response = await api.put('/api/admin/settings', { settings });
    if (!response.error) {
      alert('Settings saved successfully');
    } else {
      alert('Error saving settings: ' + response.error);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Admin Dashboard</h1>
            </div>
            <div className="flex items-center space-x-3 md:space-x-4">
              <span className="text-sm md:text-base text-blue-700 font-medium">
                {user?.first_name} {user?.last_name}
              </span>
              <button
                onClick={handleLogout}
                className="text-sm md:text-base text-blue-600 hover:text-blue-800 font-semibold px-3 py-2 rounded-lg hover:bg-blue-50 transition-colors duration-200"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        <div className="card">
          <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">System Settings</h2>
            
            {loading ? (
              <div className="text-center py-12">
                <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                <p className="mt-4 text-blue-700 text-lg">Loading...</p>
              </div>
            ) : (
              <div className="space-y-4 md:space-y-6">
                <div>
                  <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    SMTP Host
                  </label>
                  <input
                    type="text"
                    value={settings.SMTP_HOST || ''}
                    onChange={(e) => setSettings({ ...settings, SMTP_HOST: e.target.value })}
                    className="w-full"
                    placeholder="smtp.example.com"
                  />
                </div>
                <div>
                  <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    SMTP Port
                  </label>
                  <input
                    type="number"
                    value={settings.SMTP_PORT || ''}
                    onChange={(e) => setSettings({ ...settings, SMTP_PORT: e.target.value })}
                    className="w-full"
                    placeholder="587"
                  />
                </div>
                <div>
                  <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    From Email
                  </label>
                  <input
                    type="email"
                    value={settings.FROM_EMAIL || ''}
                    onChange={(e) => setSettings({ ...settings, FROM_EMAIL: e.target.value })}
                    className="w-full"
                    placeholder="noreply@villagebank.com"
                  />
                </div>
                <div>
                  <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                    LLM Provider
                  </label>
                  <input
                    type="text"
                    value={settings.LLM_PROVIDER || ''}
                    onChange={(e) => setSettings({ ...settings, LLM_PROVIDER: e.target.value })}
                    className="w-full"
                    placeholder="groq"
                  />
                </div>
                <button
                  onClick={handleSave}
                  className="btn-primary w-full md:w-auto"
                >
                  Save Settings
                </button>
              </div>
            )}
        </div>
      </main>
    </div>
  );
}
