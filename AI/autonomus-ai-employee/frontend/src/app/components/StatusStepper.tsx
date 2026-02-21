import { ProgressBar } from "./ProgressBar";

export function StatusStepper({
  steps,
  currentStep,
  status,
}: {
  steps: string[];
  currentStep: number;
  status: string;
}) {
  const progress = steps.length > 1 ? (currentStep / (steps.length - 1)) * 100 : 0;

  return (
    <div className="status-stepper">
      <div className="status-stepper__header">
        <p className="eyebrow">Live Status</p>
        <span className="status-pill">{status}</span>
      </div>
      <ProgressBar value={progress} />
      <div className="status-stepper__steps">
        {steps.map((step, index) => (
          <div
            key={step}
            className={
              index <= currentStep
                ? "status-step status-step--active"
                : "status-step"
            }
          >
            <span>{String(index + 1).padStart(2, "0")}</span>
            <p>{step}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
