'use client';

import { useState, useEffect } from 'react';
import { memberApi, Transaction } from '@/lib/memberApi';

interface TransactionHistoryModalProps {
  open: boolean;
  onClose: () => void;
  type: 'savings' | 'penalties' | 'social_fund' | 'admin_fund';
  title: string;
}

export default function TransactionHistoryModal({
  open,
  onClose,
  type,
  title,
}: TransactionHistoryModalProps) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTransactions = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await memberApi.getAccountTransactions(type);
      if (response.data) {
        setTransactions(response.data.transactions);
      } else {
        setError(response.error || 'Failed to load transactions');
      }
    } catch (err) {
      setError('An error occurred while loading transactions');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      loadTransactions();
    } else {
      // Reset state when modal closes
      setTransactions([]);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, type]);

  if (!open) return null;

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-ZM', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatAmount = (amount: number) => {
    return `K${amount.toLocaleString('en-ZM', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="transaction-history-title"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-4xl max-h-[90vh] rounded-xl border-2 border-blue-300 bg-white shadow-xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-500 to-blue-600 text-white p-5 md:p-6">
          <div className="flex items-center justify-between">
            <h2 id="transaction-history-title" className="text-xl md:text-2xl font-bold">
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="text-white hover:text-blue-200 transition-colors focus:outline-none focus:ring-2 focus:ring-white rounded-full p-1"
              aria-label="Close modal"
            >
              <svg
                className="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 md:p-6">
          {loading ? (
            <div className="text-center py-12">
              <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-200 border-t-blue-600 mx-auto"></div>
              <p className="mt-4 text-blue-700 text-lg">Loading transactions...</p>
            </div>
          ) : error ? (
            <div className="text-center py-12">
              <div className="mb-4">
                <svg
                  className="mx-auto h-16 w-16 text-red-500"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
              </div>
              <p className="text-red-700 text-lg font-medium">{error}</p>
              <button
                onClick={loadTransactions}
                className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                Retry
              </button>
            </div>
          ) : transactions.length === 0 ? (
            <div className="text-center py-12">
              <div className="mb-4">
                <svg
                  className="mx-auto h-16 w-16 text-gray-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              </div>
              <p className="text-gray-600 text-lg font-medium">No transactions yet</p>
              <p className="text-gray-500 text-sm mt-2">
                Transaction history will appear here once you have activity in this account.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-blue-50 border-b-2 border-blue-200">
                    <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Date
                    </th>
                    <th className="text-left p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Description
                    </th>
                    <th className="text-right p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Debit (K)
                    </th>
                    <th className="text-right p-3 md:p-4 text-sm md:text-base font-semibold text-blue-900">
                      Credit (K)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((transaction) => {
                    const isPenaltyRecord = transaction.is_penalty_record === true;
                    const isLateDeclaration = transaction.is_late_declaration === true;
                    const isDeclaration = transaction.is_declaration === true;
                    const isInitialRequirement = transaction.is_initial_requirement === true;
                    const isPayment = transaction.is_payment === true;
                    
                    return (
                      <tr
                        key={transaction.id}
                        className={`border-b border-gray-200 hover:bg-blue-50 transition-colors ${
                          isPenaltyRecord 
                            ? (isLateDeclaration ? 'bg-blue-50/50' : 'bg-yellow-50/50')
                            : isDeclaration
                            ? 'bg-green-50/50'
                            : isInitialRequirement
                            ? 'bg-orange-50/50'
                            : isPayment
                            ? 'bg-purple-50/50'
                            : ''
                        }`}
                      >
                        <td className="p-3 md:p-4 text-sm md:text-base text-gray-700">
                          {formatDate(transaction.date)}
                        </td>
                        <td className="p-3 md:p-4 text-sm md:text-base text-gray-700">
                          {isPenaltyRecord ? (
                            <div className="flex items-center gap-2">
                              <span className={isLateDeclaration ? 'text-blue-600' : 'text-yellow-600'}>•</span>
                              <span>{transaction.description}</span>
                              {isLateDeclaration && (
                                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                                  Late Declaration
                                </span>
                              )}
                            </div>
                          ) : isDeclaration ? (
                            <div className="flex items-center gap-2">
                              <span className="text-green-600">•</span>
                              <span>{transaction.description}</span>
                            </div>
                          ) : isInitialRequirement ? (
                            <div className="flex items-center gap-2">
                              <span className="text-orange-600">•</span>
                              <span>{transaction.description}</span>
                              <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-medium">
                                Required Amount
                              </span>
                            </div>
                          ) : isPayment ? (
                            <div className="flex items-center gap-2">
                              <span className="text-purple-600">•</span>
                              <span>{transaction.description}</span>
                              <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium">
                                Payment
                              </span>
                            </div>
                          ) : (
                            transaction.description
                          )}
                        </td>
                        <td className="p-3 md:p-4 text-sm md:text-base text-right text-gray-700">
                          {transaction.debit > 0 ? formatAmount(transaction.debit) : '-'}
                        </td>
                        <td className="p-3 md:p-4 text-sm md:text-base text-right text-gray-700">
                          {transaction.credit > 0 ? formatAmount(transaction.credit) : '-'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 bg-gray-50 p-5 md:p-6 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
