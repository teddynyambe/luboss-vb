'use client';

import InterestRevenueReportView from '@/components/InterestRevenueReportView';

export default function MemberLoanRevenueReportPage() {
  return (
    <InterestRevenueReportView
      endpoint="/api/member/reports/interest-revenue"
      backHref="/dashboard/member"
    />
  );
}
