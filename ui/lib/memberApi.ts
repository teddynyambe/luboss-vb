import { api } from './api';

export interface DeclarationCreate {
  cycle_id: string;
  effective_month: string; // ISO date string
  declared_savings_amount?: number;
  declared_social_fund?: number;
  declared_admin_fund?: number;
  declared_penalties?: number;
  declared_interest_on_loan?: number;
  declared_loan_repayment?: number;
}

export interface LoanApplicationCreate {
  cycle_id: string;
  amount: number;
  term_months: string;
  notes?: string;
}

export interface RejectedDepositProof {
  id: string;
  amount: number;
  reference?: string;
  treasurer_comment?: string;
  member_response?: string;
  upload_path: string;
  rejected_at?: string;
}

export interface Declaration {
  id: string;
  cycle_id: string;
  effective_month: string;
  declared_savings_amount?: number;
  declared_social_fund?: number;
  declared_admin_fund?: number;
  declared_penalties?: number;
  declared_interest_on_loan?: number;
  declared_loan_repayment?: number;
  status: string;
  created_at: string;
  updated_at?: string;
  can_edit?: boolean;
  rejected_deposit_proof?: RejectedDepositProof;
}

export interface LoanApplication {
  id: string;
  cycle_id: string;
  amount: number;
  term_months: string;
  status: string;
  application_date: string;
}

export interface Cycle {
  id: string;
  year: number;
  cycle_number: number;
  start_date: string;
  end_date?: string;
}

export interface DepositProof {
  id: string;
  declaration_id?: string;
  effective_month?: string;
  amount: number;
  reference?: string;
  status: string;
  treasurer_comment?: string;
  member_response?: string;
  rejected_at?: string;
  uploaded_at: string;
  upload_path: string;
}

export interface Transaction {
  id: string;
  date: string;
  description: string;
  debit: number;
  credit: number;
  amount: number;
  is_penalty_record?: boolean;
  penalty_status?: string;
  is_late_declaration?: boolean;
  is_declaration?: boolean;
  is_initial_requirement?: boolean;
  is_payment?: boolean;
}

export interface AccountTransactionsResponse {
  type: string;
  transactions: Transaction[];
}

export const memberApi = {
  createDeclaration: (data: DeclarationCreate) =>
    api.post<{ message: string; declaration_id: string }>('/api/member/declarations', data),
  
  getDeclarations: () =>
    api.get<Declaration[]>('/api/member/declarations'),
  
  getCurrentMonthDeclaration: () =>
    api.get<Declaration | null>('/api/member/declarations/current-month'),
  
  updateDeclaration: (declarationId: string, data: DeclarationCreate) =>
    api.put<{ message: string; declaration_id: string }>(`/api/member/declarations/${declarationId}`, data),
  
  getDepositProofs: () =>
    api.get<DepositProof[]>('/api/member/deposits'),
  
  respondToDepositProof: (depositId: string, response: string) => {
    const formData = new FormData();
    formData.append('response', response);
    return api.postFormData<{ message: string; deposit_id: string }>(`/api/member/deposits/${depositId}/respond`, formData);
  },
  
  resubmitDepositProof: (depositId: string, data: {
    file?: File;
    amount?: number;
    reference?: string;
    member_response?: string;
  }) => {
    const formData = new FormData();
    if (data.file) formData.append('file', data.file);
    if (data.amount !== undefined) formData.append('amount', data.amount.toString());
    if (data.reference !== undefined) formData.append('reference', data.reference);
    if (data.member_response !== undefined) formData.append('member_response', data.member_response);
    return api.putFormData<{ message: string; deposit_proof_id: string; declaration_status: string }>(`/api/member/deposits/${depositId}/resubmit`, formData);
  },
  
  applyForLoan: (data: LoanApplicationCreate) =>
    api.post<{ message: string; application_id: string }>('/api/member/loans/apply', data),
  
  getLoans: () =>
    api.get<LoanApplication[]>('/api/member/loans'),
  
  withdrawLoanApplication: (applicationId: string) =>
    api.post<{ message: string }>(`/api/member/loans/${applicationId}/withdraw`),
  
  updateLoanApplication: (applicationId: string, data: LoanApplicationCreate) =>
    api.put<{ message: string; application_id: string }>(`/api/member/loans/${applicationId}`, data),
  
  getCurrentLoan: () =>
    api.get<any>('/api/member/loans/current'),
  
  getAccountTransactions: (type: 'savings' | 'penalties' | 'social_fund' | 'admin_fund') =>
    api.get<AccountTransactionsResponse>(`/api/member/transactions?type=${type}`),
};
