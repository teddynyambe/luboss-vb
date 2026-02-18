'use client';

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import Link from 'next/link';
import UserMenu from '@/components/UserMenu';

interface BankStatementItem {
  id: string;
  cycle_id: string;
  statement_month: string;   // "YYYY-MM-DD"
  description: string | null;
  filename: string;
  uploaded_at: string | null;
}

interface DeclarationItems {
  savings_amount: number;
  social_fund: number;
  admin_fund: number;
  penalties: number;
  loan_repayment: number;
  interest_on_loan: number;
}

interface SavingsEntry {
  id: string;
  date: string;        // "YYYY-MM-DD" or ISO
  description: string;
  amount: number;
  is_declaration?: boolean;
  declaration_items?: DeclarationItems;
}

export default function MemberStatementPage() {
  const [bankStatements, setBankStatements] = useState<BankStatementItem[]>([]);
  const [savingsHistory, setSavingsHistory] = useState<SavingsEntry[]>([]);
  const [loading, setLoading] = useState(true);

  // PDF viewer state
  const [showFileModal, setShowFileModal] = useState(false);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileBlobUrl, setFileBlobUrl] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [currentFilename, setCurrentFilename] = useState<string>('');

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    const [stmtsRes, savingsRes] = await Promise.all([
      api.get<{ statements: BankStatementItem[] }>('/api/member/bank-statements'),
      api.get<{ type: string; transactions: SavingsEntry[] }>('/api/member/transactions?type=savings'),
    ]);

    if (stmtsRes.data) setBankStatements(stmtsRes.data.statements);
    if (savingsRes.data) setSavingsHistory(savingsRes.data.transactions);
    setLoading(false);
  };

  const formatMonth = (dateString: string) => {
    const datePart = dateString.split('T')[0].split(' ')[0];
    const [year, month] = datePart.split('-').map(Number);
    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    if (month >= 1 && month <= 12 && year) {
      return `${monthNames[month - 1]} ${year}`;
    }
    return dateString;
  };

  const getFileExtension = (filename: string): string => {
    return filename.split('.').pop()?.toLowerCase() || '';
  };

  const isImage = (filename: string): boolean => {
    return ['jpg', 'jpeg', 'png', 'gif'].includes(getFileExtension(filename));
  };

  const handleViewStatement = async (stmt: BankStatementItem) => {
    setCurrentFilename(stmt.filename);
    setFileLoading(true);
    setFileError(null);
    setFileBlobUrl(null);
    setShowFileModal(true);

    try {
      const blobUrl = await api.getFileBlob(
        `/api/member/bank-statements/file/${encodeURIComponent(stmt.filename)}`
      );
      setFileBlobUrl(blobUrl);
    } catch (error) {
      setFileError(error instanceof Error ? error.message : 'Failed to load file');
    } finally {
      setFileLoading(false);
    }
  };

  const closeFileModal = () => {
    setShowFileModal(false);
    if (fileBlobUrl) {
      URL.revokeObjectURL(fileBlobUrl);
      setFileBlobUrl(null);
    }
    setFileError(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-blue-100 to-blue-200">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white shadow-lg border-b-2 border-blue-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16 md:h-20">
            <div className="flex items-center space-x-3 md:space-x-4">
              <Link href="/dashboard/member" className="text-blue-600 hover:text-blue-800 text-base md:text-lg font-medium">
                ← Back
              </Link>
              <h1 className="text-lg md:text-2xl font-bold text-blue-900">My Statement</h1>
            </div>
            <UserMenu />
          </div>
        </div>
      </nav>

      <main className="max-w-4xl mx-auto py-4 md:py-6 px-4 sm:px-6 lg:px-8 pt-20 md:pt-24 space-y-6">
        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto" />
            <p className="mt-4 text-blue-700 text-lg">Loading...</p>
          </div>
        ) : (
          <>
            {/* Bank Statements Card */}
            <div className="card">
              <h2 className="text-lg md:text-xl font-bold text-blue-900 mb-4">Bank Statements</h2>
              {bankStatements.length === 0 ? (
                <p className="text-blue-700 text-sm text-center py-6">No bank statements available for the current cycle.</p>
              ) : (
                <div className="space-y-2">
                  {bankStatements.map((stmt) => (
                    <div
                      key={stmt.id}
                      className="flex items-center gap-3 p-3 bg-blue-50 border border-blue-200 rounded-lg"
                    >
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-blue-900 text-sm">{formatMonth(stmt.statement_month)}</p>
                        {stmt.description && (
                          <p className="text-xs text-blue-600 truncate">{stmt.description}</p>
                        )}
                      </div>
                      <button
                        onClick={() => handleViewStatement(stmt)}
                        className="px-3 py-1 bg-blue-600 text-white rounded text-xs font-semibold hover:bg-blue-700 transition-colors flex-shrink-0"
                      >
                        View PDF
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* My Savings History Card */}
            <div className="card">
              <h2 className="text-lg md:text-xl font-bold text-blue-900 mb-4">My Savings History</h2>
              {savingsHistory.length === 0 ? (
                <p className="text-blue-700 text-sm text-center py-6">No savings history available.</p>
              ) : (() => {
                // Group entries by month key (YYYY-MM), keeping declaration and deposit separately
                const monthMap = new Map<string, { month: string; declarationItems: DeclarationItems | null; deposited: number | null }>();
                for (const entry of savingsHistory) {
                  const key = entry.date.substring(0, 7); // "YYYY-MM"
                  if (!monthMap.has(key)) {
                    monthMap.set(key, { month: entry.date, declarationItems: null, deposited: null });
                  }
                  const row = monthMap.get(key)!;
                  if (entry.is_declaration) {
                    row.declarationItems = entry.declaration_items ?? null;
                  } else {
                    row.deposited = (row.deposited ?? 0) + entry.amount;
                  }
                }
                const rows = Array.from(monthMap.values()).sort((a, b) => a.month.localeCompare(b.month));
                const totalDeclared = rows.reduce((s, r) => {
                  if (!r.declarationItems) return s;
                  return s + Object.values(r.declarationItems).reduce((a, b) => a + b, 0);
                }, 0);
                const totalDeposited = rows.reduce((s, r) => s + (r.deposited ?? 0), 0);
                const fmt = (n: number | null) =>
                  n !== null ? `K ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';

                return (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b-2 border-blue-200">
                          <th className="text-left py-2 pr-4 text-blue-700 font-semibold">Month</th>
                          <th className="text-right py-2 pr-4 text-blue-700 font-semibold">Declaration</th>
                          <th className="text-right py-2 text-blue-700 font-semibold">Approved Deposit</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-blue-100">
                        {rows.map((row) => (
                          <tr key={row.month}>
                            <td className="py-2 pr-4 text-blue-800 whitespace-nowrap">{formatMonth(row.month)}</td>
                            <td className="py-2 pr-4 text-right text-blue-700">
                              {row.declarationItems ? (
                                <div className="text-xs space-y-0.5 leading-5">
                                  {row.declarationItems.savings_amount > 0 && (
                                    <div><span className="text-blue-500">Savings:</span> {fmt(row.declarationItems.savings_amount)}</div>
                                  )}
                                  {row.declarationItems.social_fund > 0 && (
                                    <div><span className="text-blue-500">Social Fund:</span> {fmt(row.declarationItems.social_fund)}</div>
                                  )}
                                  {row.declarationItems.admin_fund > 0 && (
                                    <div><span className="text-blue-500">Admin Fund:</span> {fmt(row.declarationItems.admin_fund)}</div>
                                  )}
                                  {row.declarationItems.penalties > 0 && (
                                    <div><span className="text-blue-500">Penalties:</span> {fmt(row.declarationItems.penalties)}</div>
                                  )}
                                  {row.declarationItems.loan_repayment > 0 && (
                                    <div><span className="text-blue-500">Loan Repayment:</span> {fmt(row.declarationItems.loan_repayment)}</div>
                                  )}
                                  {row.declarationItems.interest_on_loan > 0 && (
                                    <div><span className="text-blue-500">Interest:</span> {fmt(row.declarationItems.interest_on_loan)}</div>
                                  )}
                                </div>
                              ) : '—'}
                            </td>
                            <td className="py-2 text-right font-semibold text-blue-900 whitespace-nowrap">{fmt(row.deposited)}</td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr className="border-t-2 border-blue-300 bg-blue-50">
                          <td className="py-2 pr-4 font-bold text-blue-900">Total</td>
                          <td className="py-2 pr-4 text-right font-bold text-blue-900 whitespace-nowrap">{fmt(totalDeclared)}</td>
                          <td className="py-2 text-right font-bold text-blue-900 whitespace-nowrap">{fmt(totalDeposited)}</td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                );
              })()}
            </div>
          </>
        )}
      </main>

      {/* File Viewer Modal */}
      {showFileModal && (
        <div
          className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-4 z-50"
          onClick={closeFileModal}
        >
          <div
            className="bg-white rounded-xl shadow-2xl max-w-6xl w-full max-h-[95vh] overflow-hidden flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-blue-600 text-white px-6 py-4 flex justify-between items-center">
              <h2 className="text-xl font-bold">Bank Statement</h2>
              <button
                onClick={closeFileModal}
                className="text-white hover:text-blue-200 text-2xl font-bold transition-colors"
              >
                ×
              </button>
            </div>

            <div className="flex-1 overflow-auto p-6 bg-gray-100">
              {fileLoading ? (
                <div className="flex items-center justify-center h-96">
                  <div className="text-center">
                    <div className="animate-spin rounded-full h-16 w-16 border-4 border-blue-200 border-t-blue-600 mx-auto mb-4" />
                    <p className="text-blue-700 text-lg">Loading file...</p>
                  </div>
                </div>
              ) : fileError ? (
                <div className="flex items-center justify-center h-96">
                  <div className="text-center">
                    <div className="text-red-500 text-5xl mb-4">⚠️</div>
                    <p className="text-red-700 text-lg font-semibold">{fileError}</p>
                    <button
                      onClick={closeFileModal}
                      className="mt-4 px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                    >
                      Close
                    </button>
                  </div>
                </div>
              ) : fileBlobUrl ? (
                <div className="w-full h-full">
                  {isImage(currentFilename) ? (
                    <div className="flex items-center justify-center min-h-[500px]">
                      <img
                        src={fileBlobUrl}
                        alt="Bank Statement"
                        className="max-w-full max-h-[80vh] object-contain rounded-lg shadow-lg"
                      />
                    </div>
                  ) : (
                    <div className="w-full h-[80vh]">
                      <iframe
                        src={fileBlobUrl}
                        className="w-full h-full border-0 rounded-lg shadow-lg"
                        title="Bank Statement"
                      />
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            {fileBlobUrl && (
              <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-between items-center">
                <p className="text-sm text-gray-600">{currentFilename}</p>
                <div className="flex gap-3">
                  <a
                    href={fileBlobUrl}
                    download={currentFilename}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-semibold transition-colors"
                  >
                    Download
                  </a>
                  <button
                    onClick={closeFileModal}
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
