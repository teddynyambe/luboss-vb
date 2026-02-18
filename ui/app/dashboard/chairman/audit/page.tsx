'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import UserMenu from '@/components/UserMenu';

interface MonthOption {
  year: number;
  month: number;
  label: string;
}

interface AuditLine {
  ts: string;
  role: string;
  name: string;
  action: string;
  details: string;
}

export default function AuditLogPage() {
  const { user } = useAuth();
  const [months, setMonths] = useState<MonthOption[]>([]);
  const [selectedKey, setSelectedKey] = useState('');
  const [lines, setLines] = useState<AuditLine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load available months on mount
  useEffect(() => {
    api.get<MonthOption[]>('/api/chairman/audit/months').then((res) => {
      if (res.data && res.data.length > 0) {
        setMonths(res.data);
        const first = res.data[0];
        setSelectedKey(`${first.year}-${first.month}`);
      }
    });
  }, []);

  // Load lines whenever selectedKey changes
  useEffect(() => {
    if (!selectedKey) return;
    const [year, month] = selectedKey.split('-');
    fetchLines(Number(year), Number(month));
  }, [selectedKey]);

  const fetchLines = async (year: number, month: number) => {
    setLoading(true);
    setError(null);
    setLines([]);
    try {
      const res = await api.get<{ lines: AuditLine[] }>(`/api/chairman/audit/${year}/${month}`);
      if (res.data) {
        setLines(res.data.lines);
      } else if (res.error?.includes('404') || res.error?.includes('No audit')) {
        setLines([]);
      } else {
        setError(res.error || 'Failed to load audit log');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/chairman" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Chairman
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Activity Log</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24 space-y-6">
        {/* Month selector */}
        <div className="card flex flex-wrap items-center gap-4">
          <label className="text-sm font-semibold text-blue-900">Month:</label>
          {months.length === 0 ? (
            <span className="text-blue-700 text-sm">No log files found.</span>
          ) : (
            <select
              value={selectedKey}
              onChange={(e) => setSelectedKey(e.target.value)}
              className="px-3 py-2 border-2 border-blue-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {months.map((m) => (
                <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>
                  {m.label}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* Log table */}
        <div className="card overflow-x-auto">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto" />
              <p className="mt-4 text-blue-700">Loading…</p>
            </div>
          ) : error ? (
            <p className="text-red-700 text-center py-8">{error}</p>
          ) : lines.length === 0 ? (
            <p className="text-blue-600 text-center py-8 italic">No activity recorded for this month.</p>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr className="bg-blue-100 border-b-2 border-blue-300">
                  <th className="text-left p-3 font-semibold text-blue-900 whitespace-nowrap">Time</th>
                  <th className="text-left p-3 font-semibold text-blue-900 whitespace-nowrap">Role</th>
                  <th className="text-left p-3 font-semibold text-blue-900 whitespace-nowrap">Name</th>
                  <th className="text-left p-3 font-semibold text-blue-900 whitespace-nowrap">Action</th>
                  <th className="text-left p-3 font-semibold text-blue-900">Details</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line, idx) => (
                  <tr key={idx} className={idx % 2 === 0 ? 'bg-white' : 'bg-blue-50'}>
                    <td className="p-3 text-blue-800 whitespace-nowrap font-mono text-xs">{line.ts.split(' ')[1] || line.ts}</td>
                    <td className="p-3 text-blue-800 whitespace-nowrap capitalize">{line.role}</td>
                    <td className="p-3 text-blue-900 font-medium whitespace-nowrap">{line.name}</td>
                    <td className="p-3 text-blue-800 whitespace-nowrap">{line.action}</td>
                    <td className="p-3 text-blue-700 text-xs">{line.details}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </main>
    </div>
  );
}
