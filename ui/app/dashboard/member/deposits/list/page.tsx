'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { memberApi, DepositProof } from '@/lib/memberApi';
import { api } from '@/lib/api';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { FaInfoCircle, FaCheckCircle, FaTimesCircle, FaComment, FaChevronDown, FaChevronUp } from 'react-icons/fa';
import UserMenu from '@/components/UserMenu';

export default function DepositProofsListPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [deposits, setDeposits] = useState<DepositProof[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDeposit, setSelectedDeposit] = useState<DepositProof | null>(null);
  const [showResponseModal, setShowResponseModal] = useState(false);
  const [responseText, setResponseText] = useState('');
  const [submittingResponse, setSubmittingResponse] = useState(false);
  const [showProofModal, setShowProofModal] = useState(false);
  const [proofBlobUrl, setProofBlobUrl] = useState<string | null>(null);
  const [proofLoading, setProofLoading] = useState(false);
  const [proofError, setProofError] = useState<string | null>(null);
  const [expandedDeposits, setExpandedDeposits] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadDeposits();
  }, []);

  // Auto-expand active deposits (submitted or rejected) on initial load
  useEffect(() => {
    if (deposits.length > 0 && expandedDeposits.size === 0) {
      const activeDepositIds = deposits
        .filter(d => d.status === 'submitted' || d.status === 'rejected')
        .map(d => d.id);
      if (activeDepositIds.length > 0) {
        setExpandedDeposits(new Set(activeDepositIds));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deposits.length]);

  const toggleExpand = (depositId: string) => {
    setExpandedDeposits(prev => {
      const newSet = new Set(prev);
      if (newSet.has(depositId)) {
        newSet.delete(depositId);
      } else {
        newSet.add(depositId);
      }
      return newSet;
    });
  };

  const isExpanded = (depositId: string) => {
    return expandedDeposits.has(depositId);
  };

  const loadDeposits = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await memberApi.getDepositProofs();
      if (response.data) {
        setDeposits(response.data);
      } else {
        setError(response.error || 'Failed to load deposit proofs');
      }
    } catch (err) {
      console.error('Error loading deposit proofs:', err);
      setError('An error occurred while loading deposit proofs');
    } finally {
      setLoading(false);
    }
  };

  const handleViewProof = async (uploadPath: string, deposit: DepositProof) => {
    setSelectedDeposit(deposit);
    setProofLoading(true);
    setProofError(null);
    setShowProofModal(true);
    
    try {
      const filename = uploadPath.split('/').pop() || uploadPath;
      const blobUrl = await api.getFileBlob(`/api/treasurer/deposits/proof/${encodeURIComponent(filename)}`);
      setProofBlobUrl(blobUrl);
    } catch (error) {
      setProofError(error instanceof Error ? error.message : 'Failed to load proof file');
      setProofBlobUrl(null);
    } finally {
      setProofLoading(false);
    }
  };

  const closeProofModal = () => {
    setShowProofModal(false);
    if (proofBlobUrl) {
      URL.revokeObjectURL(proofBlobUrl);
      setProofBlobUrl(null);
    }
    setProofError(null);
  };

  const handleRespond = (deposit: DepositProof) => {
    setSelectedDeposit(deposit);
    setResponseText(deposit.member_response || '');
    setShowResponseModal(true);
  };

  const handleSubmitResponse = async () => {
    if (!selectedDeposit || !responseText.trim()) {
      return;
    }

    setSubmittingResponse(true);
    try {
      const response = await memberApi.respondToDepositProof(selectedDeposit.id, responseText);
      if (response.data) {
        await loadDeposits();
        setShowResponseModal(false);
        setResponseText('');
        setSelectedDeposit(null);
      } else {
        setError(response.error || 'Failed to submit response');
      }
    } catch (err: any) {
      setError(err.message || 'Error submitting response');
    } finally {
      setSubmittingResponse(false);
    }
  };

  const handleEditDeclaration = (declarationId: string) => {
    router.push(`/dashboard/member/declarations?edit=${declarationId}`);
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
  };

  const formatMonth = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long' });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'submitted':
        return <span className="px-3 py-1 bg-yellow-200 text-yellow-800 rounded-full text-xs font-semibold">Submitted</span>;
      case 'approved':
        return <span className="px-3 py-1 bg-green-200 text-green-800 rounded-full text-xs font-semibold">Approved</span>;
      case 'rejected':
        return <span className="px-3 py-1 bg-red-200 text-red-800 rounded-full text-xs font-semibold">Rejected</span>;
      default:
        return <span className="px-3 py-1 bg-gray-200 text-gray-800 rounded-full text-xs font-semibold">{status}</span>;
    }
  };

  const isImage = (filename: string): boolean => {
    const ext = filename.split('.').pop()?.toLowerCase() || '';
    return ['jpg', 'jpeg', 'png', 'gif'].includes(ext);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/member" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">My Deposit Proofs</h1>
            </div>
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link
                href="/dashboard/member/deposits"
                className="btn-primary flex items-center gap-2"
              >
                Upload New Proof
              </Link>
              <UserMenu />
            </div>
          </div>
        </div>
      </nav>

      <main className="max-w-7xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8">
        <div className="card">
          {error && (
            <div className="mb-4 md:mb-6 bg-red-100 border-2 border-red-400 text-red-800 px-4 py-3 md:py-4 rounded-xl text-base md:text-lg font-medium">
              {error}
            </div>
          )}

          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
              <p className="mt-4 text-blue-700 text-lg">Loading deposit proofs...</p>
            </div>
          ) : deposits.length === 0 ? (
            <div className="text-center py-12 bg-yellow-50 border-2 border-yellow-300 rounded-xl p-6 md:p-8 flex flex-col items-center">
              <FaInfoCircle className="text-yellow-600 text-5xl mb-4" />
              <h2 className="text-xl md:text-2xl font-bold text-yellow-800 mb-2">No Deposit Proofs Found</h2>
              <p className="text-base md:text-lg text-yellow-700 mb-4">
                You haven't uploaded any deposit proofs yet.
              </p>
              <Link href="/dashboard/member/deposits" className="btn-primary">
                Upload Deposit Proof
              </Link>
            </div>
          ) : (
            <div>
              <h2 className="text-xl md:text-2xl font-bold text-blue-900 mb-4 md:mb-6">All Deposit Proofs ({deposits.length})</h2>
              <div className="space-y-4">
                {deposits.map((deposit) => {
                  const expanded = isExpanded(deposit.id);
                  const isActive = deposit.status === 'submitted' || deposit.status === 'rejected';
                  
                  return (
                    <div
                      key={deposit.id}
                      className={`p-4 md:p-6 bg-white rounded-xl shadow-lg border-2 transition-all ${
                        deposit.status === 'rejected' ? 'border-red-300 bg-red-50' :
                        deposit.status === 'approved' ? 'border-green-300 bg-green-50' :
                        'border-blue-300'
                      }`}
                    >
                      {/* Header - Always visible */}
                      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                        <div className="flex-1 w-full">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-3">
                              <button
                                onClick={() => toggleExpand(deposit.id)}
                                className="text-blue-600 hover:text-blue-800 transition-colors p-1"
                                aria-label={expanded ? 'Collapse' : 'Expand'}
                              >
                                {expanded ? (
                                  <FaChevronUp className="text-lg" />
                                ) : (
                                  <FaChevronDown className="text-lg" />
                                )}
                              </button>
                              <h3 className="text-lg md:text-xl font-bold text-blue-900">
                                {deposit.effective_month ? formatMonth(deposit.effective_month) : 'Deposit Proof'}
                              </h3>
                              {getStatusBadge(deposit.status)}
                            </div>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm text-blue-700 ml-8">
                            <div>
                              <span className="font-semibold">Amount:</span> K{deposit.amount.toLocaleString()}
                            </div>
                            {deposit.reference && (
                              <div>
                                <span className="font-semibold">Reference:</span> {deposit.reference}
                              </div>
                            )}
                            <div>
                              <span className="font-semibold">Uploaded:</span> {formatDate(deposit.uploaded_at)}
                            </div>
                            {deposit.rejected_at && (
                              <div>
                                <span className="font-semibold">Rejected:</span> {formatDate(deposit.rejected_at)}
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2 ml-8 md:ml-0">
                          <button
                            onClick={() => handleViewProof(deposit.upload_path, deposit)}
                            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                          >
                            View Proof
                          </button>
                          {deposit.status === 'rejected' && (
                            <>
                              <button
                                onClick={() => handleRespond(deposit)}
                                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-semibold transition-colors flex items-center gap-2"
                              >
                                <FaComment /> {deposit.member_response ? 'Update Response' : 'Respond'}
                              </button>
                              {deposit.declaration_id && (
                                <button
                                  onClick={() => handleEditDeclaration(deposit.declaration_id!)}
                                  className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 text-sm font-semibold transition-colors"
                                >
                                  Edit Declaration
                                </button>
                              )}
                            </>
                          )}
                        </div>
                      </div>

                      {/* Expandable content */}
                      {expanded && (
                        <div className="mt-4 pt-4 border-t-2 border-blue-200 space-y-4 animate-fadeIn">
                          {deposit.treasurer_comment && (
                            <div className="p-4 bg-yellow-50 border-2 border-yellow-300 rounded-xl">
                              <div className="flex items-center gap-2 mb-2">
                                <FaInfoCircle className="text-yellow-600" />
                                <h4 className="font-bold text-yellow-900">Treasurer's Comment</h4>
                              </div>
                              <p className="text-yellow-800 whitespace-pre-wrap">{deposit.treasurer_comment}</p>
                            </div>
                          )}

                          {deposit.member_response && (
                            <div className="p-4 bg-blue-50 border-2 border-blue-300 rounded-xl">
                              <div className="flex items-center gap-2 mb-2">
                                <FaComment className="text-blue-600" />
                                <h4 className="font-bold text-blue-900">Your Response</h4>
                              </div>
                              <p className="text-blue-800 whitespace-pre-wrap">{deposit.member_response}</p>
                            </div>
                          )}

                          {!deposit.treasurer_comment && !deposit.member_response && (
                            <div className="p-4 bg-gray-50 border-2 border-gray-300 rounded-xl text-center text-gray-600">
                              <p>No comments or responses for this deposit proof.</p>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Response Modal */}
      {showResponseModal && selectedDeposit && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50" onClick={() => setShowResponseModal(false)}>
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-purple-600 text-white px-6 py-4 rounded-t-xl flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">Respond to Treasurer</h2>
              <button
                onClick={() => setShowResponseModal(false)}
                className="text-white hover:text-purple-200 text-2xl font-bold transition-colors"
              >
                ×
              </button>
            </div>
            
            <div className="p-6 md:p-8 space-y-6">
              {selectedDeposit.treasurer_comment && (
                <div className="bg-yellow-50 border-2 border-yellow-300 rounded-xl p-4">
                  <h3 className="font-bold text-yellow-900 mb-2">Treasurer's Comment:</h3>
                  <p className="text-yellow-800 whitespace-pre-wrap">{selectedDeposit.treasurer_comment}</p>
                </div>
              )}

              <div>
                <label htmlFor="response" className="block text-base md:text-lg font-semibold text-blue-900 mb-2">
                  Your Response *
                </label>
                <textarea
                  id="response"
                  value={responseText}
                  onChange={(e) => setResponseText(e.target.value)}
                  required
                  rows={6}
                  className="w-full p-3 border-2 border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  placeholder="Please provide your response to the treasurer's comment..."
                />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t-2 border-blue-200">
                <button
                  onClick={() => setShowResponseModal(false)}
                  className="btn-secondary"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSubmitResponse}
                  disabled={submittingResponse || !responseText.trim()}
                  className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-semibold transition-colors"
                >
                  {submittingResponse ? 'Submitting...' : 'Submit Response'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Proof Modal */}
      {showProofModal && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50" onClick={closeProofModal}>
          <div className="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[95vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 flex justify-between items-center">
              <h2 className="text-xl md:text-2xl font-bold">Proof of Payment</h2>
              <button
                onClick={closeProofModal}
                className="text-white hover:text-blue-200 text-2xl font-bold transition-colors"
              >
                ×
              </button>
            </div>
            
            <div className="flex-1 overflow-auto p-6 bg-gray-100">
              {proofLoading ? (
                <div className="flex items-center justify-center h-96">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto mb-4"></div>
                    <p className="text-blue-700 text-lg">Loading proof file...</p>
                  </div>
                </div>
              ) : proofError ? (
                <div className="flex items-center justify-center h-96">
                  <div className="text-center">
                    <div className="text-red-500 text-5xl mb-4">⚠️</div>
                    <p className="text-red-700 text-lg font-semibold">{proofError}</p>
                    <button
                      onClick={closeProofModal}
                      className="mt-4 px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                    >
                      Close
                    </button>
                  </div>
                </div>
              ) : proofBlobUrl && selectedDeposit ? (
                <div className="w-full h-full">
                  {isImage(selectedDeposit.upload_path) ? (
                    <div className="flex items-center justify-center min-h-[500px]">
                      <img
                        src={proofBlobUrl}
                        alt="Proof of Payment"
                        className="max-w-full max-h-[80vh] object-contain rounded-lg shadow-lg"
                      />
                    </div>
                  ) : (
                    <div className="w-full h-[80vh]">
                      <iframe
                        src={proofBlobUrl}
                        className="w-full h-full border-0 rounded-lg shadow-lg"
                        title="Proof of Payment"
                      />
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            {proofBlobUrl && selectedDeposit && (
              <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-between items-center">
                <p className="text-sm text-gray-600">
                  {selectedDeposit.upload_path.split('/').pop() || 'Proof file'}
                </p>
                <div className="flex gap-3">
                  <a
                    href={proofBlobUrl}
                    download={selectedDeposit.upload_path.split('/').pop() || 'proof.pdf'}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                  >
                    Download
                  </a>
                  <button
                    onClick={closeProofModal}
                    className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 text-sm font-semibold transition-colors"
                  >
                    Close
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
