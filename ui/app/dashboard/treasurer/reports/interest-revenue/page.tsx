'use client';

import InterestRevenueReportView from '@/components/InterestRevenueReportView';

export default function TreasurerInterestRevenuePage() {
  return (
    <InterestRevenueReportView
      endpoint="/api/treasurer/reports/interest-revenue"
      backHref="/dashboard/treasurer"
    />
  );
}
