'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import UserMenu from '@/components/UserMenu';
import { FaEdit } from 'react-icons/fa';

interface PenaltyType {
  id: string;
  name: string;
  description: string;
  fee_amount: string;
}

interface Member {
  id: string;
  user_id: string;
  status: string;
  user?: {
    email: string;
    first_name?: string;
    last_name?: string;
  };
}

export default function ComplianceDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [penaltyTypes, setPenaltyTypes] = useState<PenaltyType[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedType, setSelectedType] = useState('');
  const [selectedFee, setSelectedFee] = useState<string>('');
  const [memberId, setMemberId] = useState('');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);
  const [showPenaltyTypeForm, setShowPenaltyTypeForm] = useState(false);
  const [editingPenaltyTypeId, setEditingPenaltyTypeId] = useState<string | null>(null);
  const [newPenaltyType, setNewPenaltyType] = useState({ name: '', description: '', fee_amount: '' });
  const [editPenaltyType, setEditPenaltyType] = useState({ name: '', description: '', fee_amount: '' });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    loadPenaltyTypes();
    loadMembers();
  }, []);

  const loadPenaltyTypes = async () => {
    const response = await api.get<PenaltyType[]>('/api/compliance/penalty-types');
    if (response.data) {
      setPenaltyTypes(response.data);
    }
    setLoading(false);
  };

  const loadMembers = async () => {
    const response = await api.get<Member[]>('/api/compliance/members');
    if (response.data) {
      setMembers(response.data);
    }
  };

  const handleCreatePenalty = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    
    if (!memberId || !selectedType) {
      setError('Please select a member and penalty type');
      return;
    }

    const response = await api.post('/api/compliance/penalties', {
      member_id: memberId,
      penalty_type_id: selectedType,
      notes,
    });

    if (!response.error) {
      setSuccess('Penalty created successfully and sent to Treasurer for approval');
      setMemberId('');
      setSelectedType('');
      setSelectedFee('');
      setNotes('');
      setTimeout(() => setSuccess(''), 5000);
    } else {
      setError(response.error || 'Failed to create penalty');
      setTimeout(() => setError(''), 5000);
    }
  };

  const handleCreatePenaltyType = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (!newPenaltyType.name || !newPenaltyType.fee_amount) {
      setError('Please fill in name and fee amount');
      return;
    }

    const fee = parseFloat(newPenaltyType.fee_amount);
    if (isNaN(fee) || fee <= 0) {
      setError('Fee amount must be a positive number');
      return;
    }

    const formData = new FormData();
    formData.append('name', newPenaltyType.name);
    formData.append('description', newPenaltyType.description || '');
    formData.append('fee_amount', newPenaltyType.fee_amount);

    const response = await api.postFormData('/api/compliance/penalty-types', formData);

    if (!response.error) {
      setSuccess('Penalty type created successfully');
      setNewPenaltyType({ name: '', description: '', fee_amount: '' });
      setShowPenaltyTypeForm(false);
      loadPenaltyTypes();
      setTimeout(() => setSuccess(''), 5000);
    } else {
      setError(response.error || 'Failed to create penalty type');
      setTimeout(() => setError(''), 5000);
    }
  };

  const handleEditPenaltyType = (penaltyType: PenaltyType) => {
    setEditingPenaltyTypeId(penaltyType.id);
    setEditPenaltyType({
      name: penaltyType.name,
      description: penaltyType.description || '',
      fee_amount: penaltyType.fee_amount
    });
    setShowPenaltyTypeForm(false);
    setError('');
    setSuccess('');
  };

  const handleCancelEdit = () => {
    setEditingPenaltyTypeId(null);
    setEditPenaltyType({ name: '', description: '', fee_amount: '' });
  };

  const handleUpdatePenaltyType = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingPenaltyTypeId) return;

    setError('');
    setSuccess('');

    if (!editPenaltyType.name || !editPenaltyType.fee_amount) {
      setError('Please fill in name and fee amount');
      return;
    }

    const fee = parseFloat(editPenaltyType.fee_amount);
    if (isNaN(fee) || fee <= 0) {
      setError('Fee amount must be a positive number');
      return;
    }

    const formData = new FormData();
    formData.append('name', editPenaltyType.name);
    formData.append('description', editPenaltyType.description || '');
    formData.append('fee_amount', editPenaltyType.fee_amount);

    const response = await api.putFormData(`/api/compliance/penalty-types/${editingPenaltyTypeId}`, formData);

    if (!response.error) {
      setSuccess('Penalty type updated successfully');
      setEditingPenaltyTypeId(null);
      setEditPenaltyType({ name: '', description: '', fee_amount: '' });
      loadPenaltyTypes();
      setTimeout(() => setSuccess(''), 5000);
    } else {
      setError(response.error || 'Failed to update penalty type');
      setTimeout(() => setError(''), 5000);
    }
  };

  const handlePenaltyTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const typeId = e.target.value;
    setSelectedType(typeId);
    const selected = penaltyTypes.find(t => t.id === typeId);
    if (selected) {
      setSelectedFee(selected.fee_amount);
    } else {
      setSelectedFee('');
    }
  };

  const getMemberDisplayName = (member: Member) => {
    if (member.user?.first_name || member.user?.last_name) {
      return `${member.user.first_name || ''} ${member.user.last_name || ''}`.trim();
    }
    return member.user?.email || `Member ${member.id.substring(0, 8)}`;
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

        {/* Penalty Type Management */}
        <div className="card mb-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 md:mb-6 gap-4">
            <h2 className="text-xl md:text-2xl font-bold text-blue-900">Penalty Types</h2>
            {!editingPenaltyTypeId && (
              <button
                onClick={() => setShowPenaltyTypeForm(!showPenaltyTypeForm)}
                className="btn-secondary"
              >
                {showPenaltyTypeForm ? 'Cancel' : '+ Add Penalty Type'}
              </button>
            )}
          </div>

          {showPenaltyTypeForm && (
            <div className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4 md:p-6 mb-4">
              <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Create New Penalty Type</h3>
              <form onSubmit={handleCreatePenaltyType} className="space-y-4">
                <div>
                  <label className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                    Name *
                  </label>
                  <input
                    type="text"
                    value={newPenaltyType.name}
                    onChange={(e) => setNewPenaltyType({ ...newPenaltyType, name: e.target.value })}
                    required
                    className="w-full"
                    placeholder="e.g., Late Declaration"
                  />
                </div>
                <div>
                  <label className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                    Description (Optional)
                  </label>
                  <textarea
                    value={newPenaltyType.description}
                    onChange={(e) => setNewPenaltyType({ ...newPenaltyType, description: e.target.value })}
                    className="w-full"
                    rows={2}
                    placeholder="Optional description"
                  />
                </div>
                <div>
                  <label className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                    Fee Amount (K) *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={newPenaltyType.fee_amount}
                    onChange={(e) => setNewPenaltyType({ ...newPenaltyType, fee_amount: e.target.value })}
                    required
                    className="w-full"
                    placeholder="e.g., 50.00"
                  />
                </div>
                <button type="submit" className="btn-primary">
                  Create Penalty Type
                </button>
              </form>
            </div>
          )}

          {editingPenaltyTypeId && (
            <div className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4 md:p-6 mb-4">
              <h3 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Edit Penalty Type</h3>
              <form onSubmit={handleUpdatePenaltyType} className="space-y-4">
                <div>
                  <label className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                    Name *
                  </label>
                  <input
                    type="text"
                    value={editPenaltyType.name}
                    onChange={(e) => setEditPenaltyType({ ...editPenaltyType, name: e.target.value })}
                    required
                    className="w-full"
                    placeholder="e.g., Late Declaration"
                  />
                </div>
                <div>
                  <label className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                    Description (Optional)
                  </label>
                  <textarea
                    value={editPenaltyType.description}
                    onChange={(e) => setEditPenaltyType({ ...editPenaltyType, description: e.target.value })}
                    className="w-full"
                    rows={2}
                    placeholder="Optional description"
                  />
                </div>
                <div>
                  <label className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                    Fee Amount (K) *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={editPenaltyType.fee_amount}
                    onChange={(e) => setEditPenaltyType({ ...editPenaltyType, fee_amount: e.target.value })}
                    required
                    className="w-full"
                    placeholder="e.g., 50.00"
                  />
                </div>
                <div className="flex gap-2">
                  <button type="submit" className="btn-primary">
                    Update Penalty Type
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelEdit}
                    className="btn-secondary"
                  >
                    Cancel
                  </button>
                </div>
              </form>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {penaltyTypes.map((type) => (
              <div key={type.id} className="bg-blue-50 border-2 border-blue-200 rounded-lg p-4 relative">
                {editingPenaltyTypeId !== type.id && (
                  <button
                    onClick={() => handleEditPenaltyType(type)}
                    className="absolute top-2 right-2 text-blue-600 hover:text-blue-800 transition-colors"
                    title="Edit penalty type"
                  >
                    <FaEdit className="w-4 h-4" />
                  </button>
                )}
                <h4 className="text-base md:text-lg font-bold text-blue-900 mb-2 pr-6">{type.name}</h4>
                {type.description && (
                  <p className="text-sm text-blue-700 mb-2">{type.description}</p>
                )}
                <p className="text-lg font-bold text-blue-900">
                  Fee: K{parseFloat(type.fee_amount).toLocaleString()}
                </p>
              </div>
            ))}
            {penaltyTypes.length === 0 && !loading && (
              <p className="text-blue-700 col-span-full text-center py-4">
                No penalty types created yet. Click "Add Penalty Type" to create one.
              </p>
            )}
          </div>
        </div>

        {/* Create Penalty Record */}
        <div className="card">
          <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Create Penalty Record</h2>
          
          <form onSubmit={handleCreatePenalty} className="space-y-4 md:space-y-6">
            <div>
              <label className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                Member *
              </label>
              <select
                value={memberId}
                onChange={(e) => setMemberId(e.target.value)}
                required
                className="w-full"
              >
                <option value="">Select a member</option>
                {members.map((member) => (
                  <option key={member.id} value={member.id}>
                    {getMemberDisplayName(member)} {member.user?.email ? `(${member.user.email})` : ''}
                  </option>
                ))}
              </select>
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
                <>
                  <select
                    value={selectedType}
                    onChange={handlePenaltyTypeChange}
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
                  {selectedFee && (
                    <div className="mt-2 p-3 bg-blue-50 border-2 border-blue-200 rounded-lg">
                      <p className="text-sm font-semibold text-blue-900">
                        Fee Amount: <span className="text-lg">K{parseFloat(selectedFee).toLocaleString()}</span>
                      </p>
                      <p className="text-xs text-blue-600 mt-1">
                        This amount will be charged to the member's account when approved by the Treasurer.
                      </p>
                    </div>
                  )}
                </>
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
              Create Penalty (Pending Treasurer Approval)
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
