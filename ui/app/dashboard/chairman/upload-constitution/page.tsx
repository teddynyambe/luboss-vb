'use client';

import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';

interface ConstitutionCurrent {
  id: string;
  version_number: string;
  uploaded_at: string;
  description: string | null;
}

interface ConstitutionResponse {
  current: ConstitutionCurrent | null;
}

export default function UploadConstitutionPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [current, setCurrent] = useState<ConstitutionCurrent | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [versionNumber, setVersionNumber] = useState('');
  const [description, setDescription] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadCurrent();
  }, []);

  const loadCurrent = async () => {
    setLoading(true);
    const res = await api.get<ConstitutionResponse>('/api/chairman/constitution');
    if (res.data?.current) {
      setCurrent(res.data.current);
    } else {
      setCurrent(null);
    }
    setLoading(false);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setMessage({ type: 'error', text: 'Please select a PDF file.' });
      return;
    }
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setMessage({ type: 'error', text: 'Only PDF files are accepted.' });
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    if (versionNumber.trim()) formData.append('version_number', versionNumber.trim());
    if (description.trim()) formData.append('description', description.trim());

    const res = await api.postFormData<{ message: string; version_id: string; version_number: string }>(
      '/api/chairman/constitution/upload',
      formData
    );

    setUploading(false);
    if (res.error) {
      const detail = typeof (res as { detail?: string | string[] }).detail === 'string'
        ? (res as unknown as { detail: string }).detail
        : Array.isArray((res as unknown as { detail?: string[] }).detail)
          ? (res as unknown as { detail: string[] }).detail?.join(', ')
          : res.error;
      setMessage({ type: 'error', text: detail || res.error });
      return;
    }

    setMessage({
      type: 'success',
      text: res.data?.message || 'Constitution uploaded successfully.',
    });
    setVersionNumber('');
    setDescription('');
    if (fileInputRef.current) fileInputRef.current.value = '';
    loadCurrent();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link
                href="/dashboard/chairman"
                className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium"
              >
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Upload Constitution</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-2xl mx-auto py-6 md:py-8 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        <div className="card space-y-6">
          <p className="text-blue-800">
            Upload or replace the constitution PDF. It is used by the AI chat to answer members’ questions
            about the constitution and other policies. Replacing will remove the previous version and
            update the AI knowledge base.
          </p>

          {loading ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600" />
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-blue-50 border-2 border-blue-200">
              <h2 className="text-lg font-bold text-blue-900 mb-2">Current constitution</h2>
              {current ? (
                <div className="text-blue-800 space-y-1">
                  <p>
                    <span className="font-semibold">Version:</span> {current.version_number}
                  </p>
                  <p>
                    <span className="font-semibold">Uploaded:</span>{' '}
                    {new Date(current.uploaded_at).toLocaleString()}
                  </p>
                  {current.description && (
                    <p>
                      <span className="font-semibold">Description:</span> {current.description}
                    </p>
                  )}
                </div>
              ) : (
                <p className="text-blue-700">No constitution uploaded yet.</p>
              )}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-semibold text-blue-900 mb-2">PDF file *</label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,application/pdf"
                className="block w-full text-base text-blue-800 file:mr-4 file:py-3 file:px-4 file:rounded-lg file:border-0 file:bg-blue-100 file:text-blue-800 file:font-semibold file:cursor-pointer hover:file:bg-blue-200"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-blue-900 mb-2">
                Version (optional)
              </label>
              <input
                type="text"
                value={versionNumber}
                onChange={(e) => setVersionNumber(e.target.value)}
                placeholder="e.g. 2025-01 or 1.2"
                className="w-full px-4 py-3 border-2 border-blue-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-blue-500"
              />
              <p className="mt-1 text-sm text-blue-600">
                Leave blank to use today’s date (YYYYMMDD).
              </p>
            </div>

            <div>
              <label className="block text-sm font-semibold text-blue-900 mb-2">
                Description (optional)
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="e.g. Amended January 2025"
                rows={2}
                className="w-full px-4 py-3 border-2 border-blue-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-blue-500 resize-none"
              />
            </div>

            {message && (
              <div
                className={`p-4 rounded-lg ${
                  message.type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                }`}
              >
                {message.text}
              </div>
            )}

            <button
              type="submit"
              disabled={uploading}
              className="btn-primary w-full disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {uploading ? 'Uploading…' : current ? 'Replace constitution' : 'Upload constitution'}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
