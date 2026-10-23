const STEPS = [
  { key: "draft", label: "Received" },
  { key: "pending_processing", label: "Validated" },
  { key: "approval", label: "Approval" },
  { key: "posted", label: "ERP Posting" },
];

const STATUS_TO_INDEX = {
  draft: 0,
  pending_processing: 1,
  validated: 2,
  pending_approval: 2,
  approved: 3,
  posted: 3,
  parked: 3,
};

// Sub-label shown under the Approval step
const APPROVAL_SUBLABEL = {
  validated: "Ready to Submit",
  pending_approval: "Pending Approval",
  approved: "Approved",
  rejected: "Rejected",
};

export default function WorkflowStepper({ currentStatus }) {
  const isException = currentStatus === "exception";
  const isRejected = currentStatus === "rejected";
  const isApproved = currentStatus === "approved" || currentStatus === "posted" || currentStatus === "parked";

  const currentIndex = isException
    ? 1
    : isRejected
      ? 2
      : (STATUS_TO_INDEX[currentStatus] ?? 0);

  return (
    <div className="bg-neutral-0 border border-neutral-100 rounded-md shadow-sm px-6 py-4">
      <div className="flex items-center">
        {STEPS.map((step, i) => {
          const isCompleted = i < currentIndex;
          const isCurrent = i === currentIndex;
          const isError = isCurrent && (isException || isRejected);

          // For the Approval step, show as completed (green) when approved/posted
          const isApprovalStep = step.key === "approval";
          const approvalCompleted = isApprovalStep && isApproved;

          const showCompleted = isCompleted || approvalCompleted;

          return (
            <div key={step.key} className="flex items-center flex-1 last:flex-none">
              {/* Step circle + label */}
              <div className="flex flex-col items-center">
                <div
                  className={`
                    w-8 h-8 rounded-full flex items-center justify-center text-2xs font-bold
                    transition-colors relative
                    ${showCompleted
                      ? "bg-success-base text-white"
                      : isError
                        ? "bg-danger-base text-white"
                        : isCurrent
                          ? "bg-brand-600 text-white"
                          : "bg-neutral-200 text-neutral-500"
                    }
                  `}
                >
                  {showCompleted ? (
                    <svg className="w-3.5 h-3.5" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M2.5 7L5.5 10L11.5 4" />
                    </svg>
                  ) : isError ? (
                    <svg className="w-3.5 h-3.5" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M3.5 3.5L10.5 10.5M10.5 3.5L3.5 10.5" />
                    </svg>
                  ) : (
                    i + 1
                  )}
                  {/* Error ring */}
                  {isError && (
                    <div className="absolute -inset-1 rounded-full border-2 border-danger-base animate-pulse" />
                  )}
                </div>
                <span
                  className={`mt-1.5 text-2xs font-medium whitespace-nowrap ${
                    showCompleted
                      ? "text-success-dark"
                      : isError
                        ? "text-danger-dark"
                        : isCurrent
                          ? "text-brand-700"
                          : "text-neutral-400"
                  }`}
                >
                  {isCurrent && isException
                    ? "Exception"
                    : isCurrent && isRejected
                      ? "Rejected"
                      : step.key === "posted" && currentStatus === "parked"
                        ? "Parked"
                        : step.label}
                </span>
                {/* Sub-label for Approval step */}
                {isApprovalStep && APPROVAL_SUBLABEL[currentStatus] && !isException && (
                  <span className={`text-2xs whitespace-nowrap ${
                    isApproved ? "text-success-dark" : isRejected ? "text-danger-dark" : isCurrent ? "text-neutral-500" : "text-neutral-400"
                  }`}>
                    {APPROVAL_SUBLABEL[currentStatus]}
                  </span>
                )}
              </div>

              {/* Connecting line (not after last step) */}
              {i < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-2 mt-[-16px] ${
                    showCompleted ? "bg-success-base" : "bg-neutral-200"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
