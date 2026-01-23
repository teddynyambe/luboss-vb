'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';

interface PenaltyType {
  id: string;
  name: string;
  description: string;
  fee_amount: string;
}

export default function ComplianceDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [penaltyTypes, setPenaltyTypes] = useState<PenaltyType[]>([]);
  const [selectedType, setSelectedType] = useState('');
  const [memberId, setMemberId] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPenaltyTypes();
  }, []);

  const loadPenaltyTypes = async () => {
    const response = await api.get<PenaltyType[]>('/api/treasurer/penalty-types');
    if (response.data) {
      setPenaltyTypes(response.data);
    }
    setLoading(false);
  };

  const handleCreatePenalty = async (e: React.FormEvent) => {
    e.preventDefault();
    const response = await api.post('/api/compliance/penalties', {
      member_id: memberId,
      penalty_type_id: selectedType,
      notes,
    });

    if (!response.error) {
      alert('Penalty created successfully');
      setMemberId('');
      setSelectedType('');
      setNotes('');
    } else {
      alert('Error: ' + response.error);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">Compliance Dashboard</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24">
        <div className="card">
          <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Create Penalty Record</h2>
          
          <form onSubmit={handleCreatePenalty} className="space-y-4 md:space-y-6">
            <div>
              <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                Member ID *
              </label>
              <input
                type="text"
                value={memberId}
                onChange={(e) => setMemberId(e.target.value)}
                required
                className="w-full"
                placeholder="Enter member ID"
              />
            </div>

            <div>
              <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                Penalty Type *
              </label>
              {loading ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
                  <p className="mt-4 text-blue-700 text-lg">Loading...</p>
                </div>
              ) : (
                <select
                  value={selectedType}
                  onChange={(e) => setSelectedType(e.target.value)}
                  required
                  className="w-full"
                >
                  <option value="">Select penalty type</option>
                  {penaltyTypes.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name} - K{parseFloat(type.fee_amount).toLocaleString()}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div>
              <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                Notes (Optional)
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="w-full min-h-[120px]"
                rows={4}
                placeholder="Enter any additional notes..."
              />
            </div>

            <button
              type="submit"
              className="btn-primary w-full"
            >
              Create Penalty
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
