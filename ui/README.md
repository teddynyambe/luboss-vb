# Luboss95 Village Banking v2 - Frontend

Next.js frontend for the Village Banking system.

## Setup

```bash
cd ui
npm install
```

## Development

```bash
npm run dev
```

The app will be available at http://localhost:3000

## Environment Variables

Create `.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8002
```

## Features

- **Authentication**: Login and registration
- **Role-based Dashboards**: 
  - Member: View status, make declarations, apply for loans, AI chat
  - Admin: System settings
  - Chairman: Approve members, manage cycles
  - Treasurer: Approve deposits and penalties
  - Compliance: Create penalty records
- **AI Chat**: Interactive chat for rules and account status

## Project Structure

```
ui/
  app/              # Next.js app router pages
  components/       # Reusable components
  contexts/         # React contexts (Auth)
  lib/              # API client and utilities
```
