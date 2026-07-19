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

interface ApprovedPenalty {
  id: string;
  member_name: string;
  penalty_type_name: string;
  fee_amount: number;
  status: string;
  date_issued: string | null;
  notes: string | null;
  reversal_reason: string | null;
  reversal_requested_at: string | null;
}

interface MemberPenalty {
  id: string;
  member_id: string;
  member_name: string;
  penalty_type_name: string;
  penalty_type_description?: string | null;
  fee_amount: number;
  status: string;
  date_issued: string | null;
  approved_at?: string | null;
  notes: string | null;
  created_by_name?: string | null;
  reversal_reason: string | null;
  reversal_requested_by_name?: string | null;
  reversal_requested_at: string | null;
  reversed_by_name?: string | null;
  reversed_at?: string | null;
}

interface MemberPenaltyAudit {
  member_id: string;
  member_name: string;
  summary: {
    total_count: number;
    pending_count: number;
    approved_count: number;
    reversal_pending_count: number;
    reversed_count: number;
    paid_count: number;
    total_approved_fee: number;
  };
  penalties: MemberPenalty[];
}

// Render an ISO 8601 UTC timestamp in the browser's locale. Used for the
// "date issued", "reversed at" etc. columns AND for the timestamps embedded
// inside the narration (see `renderNarrationWithLocalDates` below).
const formatIsoInBrowserLocale = (iso: string | null | undefined, withTime: boolean): string => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    if (withTime) {
      return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
    }
    return d.toLocaleDateString(undefined, { dateStyle: 'medium' });
  } catch {
    return iso;
  }
};

// Detect ISO 8601 date/datetime tokens inside a narration string and swap
// them for browser-locale-formatted equivalents. Keeps the surrounding
// English text intact so the "why was this charged" sentence stays
// readable, just with the timestamps auto-translated to the reader's
// timezone / regional format.
const renderNarrationWithLocalDates = (text: string | null | undefined): string => {
  if (!text) return '';
  // Match full UTC datetimes (2026-06-27T05:12:00Z) first — with `Z` — so
  // the date-only fallback doesn't strip the time portion.
  let out = text.replace(/\b(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})Z\b/g, (m) =>
    formatIsoInBrowserLocale(m, true)
  );
  // Then bare YYYY-MM-DD dates (period_start / period_end).
  out = out.replace(/\b(\d{4}-\d{2}-\d{2})\b(?!T)/g, (m) => formatIsoInBrowserLocale(m, false));
  return out;
};

export default function ComplianceDashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'manage' | 'reverse'>('manage');
  const [memberSearch, setMemberSearch] = useState('');
  const [reverseNameFilter, setReverseNameFilter] = useState('');
  const [reverseTypeFilter, setReverseTypeFilter] = useState<string>('');
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

  // Reversal state
  const [approvedPenalties, setApprovedPenalties] = useState<ApprovedPenalty[]>([]);
  const [reversingId, setReversingId] = useState<string | null>(null);
  const [reversalReason, setReversalReason] = useState('');

  // Per-member penalty audit — the "why was this charged" view. State lives
  // separate from the create-penalty picker so the officer can be looking at
  // one member's audit while considering issuing a penalty to another.
  const [auditMemberSearch, setAuditMemberSearch] = useState('');
  const [auditMemberId, setAuditMemberId] = useState('');
  const [auditData, setAuditData] = useState<MemberPenaltyAudit | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState('');

  useEffect(() => {
    loadPenaltyTypes();
    loadMembers();
    loadApprovedPenalties();
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

  const loadApprovedPenalties = async () => {
    const res = await api.get<ApprovedPenalty[]>('/api/compliance/penalties/approved');
    if (res.data) setApprovedPenalties(res.data);
  };

  const loadMemberPenaltyAudit = async (memberId: string) => {
    if (!memberId) {
      setAuditData(null);
      setAuditError('');
      return;
    }
    setAuditLoading(true);
    setAuditError('');
    try {
      const res = await api.get<MemberPenaltyAudit>(`/api/compliance/members/${memberId}/penalties`);
      if (res.data) {
        setAuditData(res.data);
      } else {
        setAuditError(res.error || 'Failed to load penalties for this member.');
      }
    } finally {
      setAuditLoading(false);
    }
  };

  const handleRequestReversal = async () => {
    if (!reversingId || !reversalReason.trim()) return;
    setError('');
    const res = await api.put(`/api/compliance/penalties/${reversingId}/request-reversal`, {
      reason: reversalReason,
    });
    if (!res.error) {
      setSuccess('Reversal request submitted — awaiting Treasurer approval');
      setReversingId(null);
      setReversalReason('');
      loadApprovedPenalties();
      setTimeout(() => setSuccess(''), 5000);
    } else {
      setError(res.error || 'Failed to request reversal');
      setTimeout(() => setError(''), 5000);
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

  const toTitleCase = (str: string) =>
    str.split(' ').map(w => w ? w[0].toUpperCase() + w.slice(1).toLowerCase() : '').join(' ').trim();

  const getMemberDisplayName = (member: Member) => {
    if (member.user?.first_name || member.user?.last_name) {
      return toTitleCase(`${member.user.first_name || ''} ${member.user.last_name || ''}`);
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

        {/* Tab toggle */}
        <div className="flex gap-2 mb-6 border-b-2 border-blue-200">
          <button
            type="button"
            onClick={() => setActiveTab('manage')}
            className={`px-4 py-2 md:px-6 md:py-3 text-sm md:text-base font-semibold rounded-t-lg transition-colors -mb-0.5 border-b-2 ${
              activeTab === 'manage'
                ? 'bg-white text-blue-900 border-blue-600'
                : 'text-blue-600 hover:text-blue-800 border-transparent'
            }`}
          >
            Manage Penalties
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('reverse')}
            className={`px-4 py-2 md:px-6 md:py-3 text-sm md:text-base font-semibold rounded-t-lg transition-colors -mb-0.5 border-b-2 ${
              activeTab === 'reverse'
                ? 'bg-white text-blue-900 border-blue-600'
                : 'text-blue-600 hover:text-blue-800 border-transparent'
            }`}
          >
            Reverse Penalty
          </button>
        </div>

        {activeTab === 'manage' && (<>
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
                    type="number" inputMode="decimal"
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
                    type="number" inputMode="decimal"
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
              <input
                type="text"
                value={memberSearch}
                onChange={(e) => setMemberSearch(e.target.value)}
                placeholder="Filter by first name or last name"
                className="w-full mb-2"
              />
              <select
                value={memberId}
                onChange={(e) => setMemberId(e.target.value)}
                required
                className="w-full"
              >
                <option value="">Select a member</option>
                {members
                  .filter((m) => {
                    const q = memberSearch.trim().toLowerCase();
                    if (!q) return true;
                    const fn = (m.user?.first_name || '').toLowerCase();
                    const ln = (m.user?.last_name || '').toLowerCase();
                    return fn.includes(q) || ln.includes(q);
                  })
                  .map((member) => (
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

        {/* Per-member penalty audit — the "why was this charged" view.
            Every penalty for the picked member is listed with the full
            narration and browser-locale timestamps so the officer can
            justify (or reverse) each charge without cross-referencing
            other records. */}
        <div className="card mt-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 md:mb-6 gap-3">
            <div>
              <h2 className="text-xl md:text-2xl font-bold text-blue-900">Member Penalty Audit</h2>
              <p className="text-sm text-blue-600 mt-1">
                Pick a member to see every penalty charged to them, why it was charged, and the current status.
                Times shown in your local timezone.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                Filter members
              </label>
              <input
                type="text"
                value={auditMemberSearch}
                onChange={(e) => setAuditMemberSearch(e.target.value)}
                placeholder="Filter by first name or last name"
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-sm md:text-base font-semibold text-blue-900 mb-2">
                Member
              </label>
              <select
                value={auditMemberId}
                onChange={(e) => {
                  setAuditMemberId(e.target.value);
                  loadMemberPenaltyAudit(e.target.value);
                }}
                className="w-full"
              >
                <option value="">Pick a member…</option>
                {members
                  .filter((m) => {
                    const q = auditMemberSearch.trim().toLowerCase();
                    if (!q) return true;
                    const fn = (m.user?.first_name || '').toLowerCase();
                    const ln = (m.user?.last_name || '').toLowerCase();
                    return fn.includes(q) || ln.includes(q);
                  })
                  .map((member) => (
                    <option key={member.id} value={member.id}>
                      {getMemberDisplayName(member)} {member.user?.email ? `(${member.user.email})` : ''}
                    </option>
                  ))}
              </select>
            </div>
          </div>

          {auditError && (
            <p className="text-sm text-red-800 bg-red-50 border border-red-300 rounded px-3 py-2 mb-3">
              {auditError}
            </p>
          )}

          {auditLoading && (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-10 w-10 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
              <p className="mt-3 text-blue-700 text-sm">Loading penalties…</p>
            </div>
          )}

          {!auditLoading && auditData && (
            <>
              {/* Summary strip */}
              <div className="grid grid-cols-2 md:grid-cols-6 gap-2 mb-4">
                <div className="p-2 bg-gray-50 border border-gray-200 rounded-lg text-center">
                  <p className="text-[10px] text-gray-600 uppercase">Total</p>
                  <p className="text-base font-bold text-gray-900">{auditData.summary.total_count}</p>
                </div>
                <div className="p-2 bg-yellow-50 border border-yellow-200 rounded-lg text-center">
                  <p className="text-[10px] text-yellow-700 uppercase">Pending</p>
                  <p className="text-base font-bold text-yellow-900">{auditData.summary.pending_count}</p>
                </div>
                <div className="p-2 bg-blue-50 border border-blue-200 rounded-lg text-center">
                  <p className="text-[10px] text-blue-700 uppercase">Approved</p>
                  <p className="text-base font-bold text-blue-900">{auditData.summary.approved_count}</p>
                </div>
                <div className="p-2 bg-orange-50 border border-orange-200 rounded-lg text-center">
                  <p className="text-[10px] text-orange-700 uppercase">Rev. pending</p>
                  <p className="text-base font-bold text-orange-900">{auditData.summary.reversal_pending_count}</p>
                </div>
                <div className="p-2 bg-green-50 border border-green-200 rounded-lg text-center">
                  <p className="text-[10px] text-green-700 uppercase">Paid</p>
                  <p className="text-base font-bold text-green-900">{auditData.summary.paid_count}</p>
                </div>
                <div className="p-2 bg-red-50 border border-red-200 rounded-lg text-center">
                  <p className="text-[10px] text-red-700 uppercase">Reversed</p>
                  <p className="text-base font-bold text-red-900">{auditData.summary.reversed_count}</p>
                </div>
              </div>
              <p className="text-xs text-blue-700 mb-4">
                Total exposure (approved + reversal-pending + paid): <strong>K{auditData.summary.total_approved_fee.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</strong>
              </p>

              {auditData.penalties.length === 0 ? (
                <p className="text-sm text-blue-700 bg-blue-50 border border-blue-200 rounded p-3">
                  No penalties on record for this member.
                </p>
              ) : (
                <div className="space-y-3">
                  {auditData.penalties.map((p) => {
                    const statusStyle = (() => {
                      switch (p.status) {
                        case 'approved':          return 'bg-blue-100 text-blue-800 border-blue-300';
                        case 'reversal_pending':  return 'bg-orange-100 text-orange-800 border-orange-300';
                        case 'reversed':          return 'bg-red-100 text-red-800 border-red-300';
                        case 'paid':              return 'bg-green-100 text-green-800 border-green-300';
                        case 'pending':           return 'bg-yellow-100 text-yellow-800 border-yellow-300';
                        default:                  return 'bg-gray-100 text-gray-800 border-gray-300';
                      }
                    })();
                    return (
                      <div key={p.id} className="bg-white border-2 border-blue-100 rounded-lg p-3 md:p-4">
                        <div className="flex flex-wrap justify-between items-start gap-2 mb-2">
                          <div>
                            <h3 className="font-bold text-blue-900">{p.penalty_type_name}</h3>
                            <p className="text-xs text-blue-700">
                              K{p.fee_amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              {' · issued '}{formatIsoInBrowserLocale(p.date_issued, true)}
                              {p.created_by_name ? <> {' · by '}{p.created_by_name}</> : null}
                            </p>
                          </div>
                          <span className={`px-2 py-0.5 text-xs font-semibold rounded border ${statusStyle}`}>
                            {p.status.replace(/_/g, ' ')}
                          </span>
                        </div>
                        {p.notes && (
                          <p className="mt-2 text-sm text-blue-900 bg-blue-50 border border-blue-200 rounded px-3 py-2 whitespace-pre-wrap">
                            {renderNarrationWithLocalDates(p.notes)}
                          </p>
                        )}
                        {(p.approved_at || p.reversal_requested_at || p.reversed_at || p.reversal_reason) && (
                          <div className="mt-2 text-[11px] text-blue-700 space-y-0.5">
                            {p.approved_at && (
                              <div>Approved by treasurer at <strong>{formatIsoInBrowserLocale(p.approved_at, true)}</strong>.</div>
                            )}
                            {p.reversal_requested_at && (
                              <div>
                                Reversal requested by {p.reversal_requested_by_name || 'compliance'} at{' '}
                                <strong>{formatIsoInBrowserLocale(p.reversal_requested_at, true)}</strong>.
                              </div>
                            )}
                            {p.reversal_reason && (
                              <div>Reversal reason: <em>{p.reversal_reason}</em></div>
                            )}
                            {p.reversed_at && (
                              <div>
                                Reversed by {p.reversed_by_name || 'treasurer'} at{' '}
                                <strong>{formatIsoInBrowserLocale(p.reversed_at, true)}</strong>.
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
        </>)}

        {activeTab === 'reverse' && (
        /* Penalty Reversals */
        <div className="card">
          <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">Reverse Penalty</h2>
          <p className="text-sm text-blue-600 mb-4">
            Select an approved penalty to request reversal. The Treasurer must approve the reversal before it takes effect.
          </p>

          {/* Filters */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <input
              type="text"
              value={reverseNameFilter}
              onChange={(e) => setReverseNameFilter(e.target.value)}
              placeholder="Filter by first name or last name"
              className="w-full"
            />
            <select
              value={reverseTypeFilter}
              onChange={(e) => setReverseTypeFilter(e.target.value)}
              className="w-full"
            >
              <option value="">All penalty types</option>
              {penaltyTypes.map((t) => (
                <option key={t.id} value={t.name}>{t.name}</option>
              ))}
            </select>
          </div>

          {(() => {
            const q = reverseNameFilter.trim().toLowerCase();
            const filtered = approvedPenalties.filter((p) => {
              const nameOk = !q || (p.member_name || '').toLowerCase().includes(q);
              const typeOk = !reverseTypeFilter || p.penalty_type_name === reverseTypeFilter;
              return nameOk && typeOk;
            });
            if (filtered.length === 0) {
              return (
                <p className="text-blue-500 text-center py-4">
                  {approvedPenalties.length === 0
                    ? 'No approved penalties to reverse.'
                    : 'No penalties match the current filters.'}
                </p>
              );
            }
            return (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {filtered.map(p => (
                <div key={p.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border border-blue-100 rounded-lg p-3 bg-blue-50">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-blue-900">{p.member_name}</span>
                      <span className="text-xs bg-blue-200 text-blue-800 px-2 py-0.5 rounded-full">{p.penalty_type_name}</span>
                      <span className="font-bold text-blue-900">K{p.fee_amount.toLocaleString()}</span>
                      {p.status === 'reversal_pending' && (
                        <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">Reversal Pending</span>
                      )}
                    </div>
                    {p.notes && <p className="text-xs text-blue-600 mt-0.5 truncate">{p.notes}</p>}
                    {p.reversal_reason && (
                      <p className="text-xs text-orange-600 mt-0.5">Reversal reason: {p.reversal_reason}</p>
                    )}
                  </div>
                  {p.status === 'approved' && (
                    <button
                      onClick={() => { setReversingId(p.id); setReversalReason(''); }}
                      className="px-3 py-1.5 bg-red-500 text-white rounded-lg text-xs font-semibold hover:bg-red-600 shrink-0"
                    >
                      Request Reversal
                    </button>
                  )}
                </div>
              ))}
            </div>
            );
          })()}
        </div>
        )}

        {/* Reversal reason modal */}
        {reversingId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
              <h3 className="text-lg font-bold text-red-800 mb-3">Request Penalty Reversal</h3>
              <p className="text-sm text-blue-700 mb-3">Provide a reason for reversing this penalty. The Treasurer must approve before it takes effect.</p>
              <textarea
                value={reversalReason}
                onChange={e => setReversalReason(e.target.value)}
                className="w-full mb-4"
                rows={3}
                placeholder="Reason for reversal (e.g. wrongly charged, disputed and resolved)..."
                autoFocus
              />
              <div className="flex justify-end gap-2">
                <button onClick={() => setReversingId(null)} className="px-4 py-2 bg-gray-200 rounded-lg text-sm font-semibold">
                  Cancel
                </button>
                <button
                  onClick={handleRequestReversal}
                  disabled={!reversalReason.trim()}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-semibold hover:bg-red-700 disabled:opacity-50"
                >
                  Submit Request
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
