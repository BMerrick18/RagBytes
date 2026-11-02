interface CollapseButtonProps {
  open: boolean;
  onToggle: () => void;
  controls: string;
  showLabel?: string;
  hideLabel?: string;
}

export function CollapseButton({ open, onToggle, controls, showLabel = "Show", hideLabel = "Hide" }: CollapseButtonProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      aria-controls={controls}
      className="flex items-center gap-1.5 rounded-md px-2.5 py-3 text-sm font-medium text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200 md:py-1.5"
    >
      {open ? hideLabel : showLabel}
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        aria-hidden
        className={`h-4 w-4 transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
      </svg>
    </button>
  );
}
