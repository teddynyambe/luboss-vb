'use client';

interface NotificationModalProps {
  /** 'success' | 'error' */
  type: 'success' | 'error';
  message: string;
  onClose: () => void;
}

export default function NotificationModal({ type, message, onClose }: NotificationModalProps) {
  const isSuccess = type === 'success';
  const bgClass = isSuccess ? 'bg-green-50 border-green-400' : 'bg-red-50 border-red-400';
  const textClass = isSuccess ? 'text-green-800' : 'text-red-800';
  const icon = isSuccess ? '✓' : '✗';
  const title = isSuccess ? 'Success' : 'Notice';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="notification-title"
      aria-describedby="notification-message"
      onClick={onClose}
    >
      <div
        className={`relative w-full max-w-md rounded-xl border-2 ${bgClass} shadow-xl ${textClass}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-5 md:p-6">
          <div className="flex items-start gap-4">
            <span
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-lg font-bold ${
                isSuccess ? 'bg-green-200 text-green-800' : 'bg-red-200 text-red-800'
              }`}
            >
              {icon}
            </span>
            <div className="flex-1 min-w-0">
              <h2 id="notification-title" className="text-lg font-bold mb-1">
                {title}
              </h2>
              <p id="notification-message" className="text-base font-medium">
                {message}
              </p>
            </div>
          </div>
          <div className="mt-5 flex justify-end">
            <button
              type="button"
              onClick={onClose}
              className={`px-4 py-2 rounded-xl font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                isSuccess
                  ? 'bg-green-600 text-white hover:bg-green-700 focus:ring-green-500'
                  : 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500'
              }`}
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
