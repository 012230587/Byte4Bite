export default function Loader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="inline-flex items-center gap-3 rounded-full bg-slate-100 px-4 py-2 text-sm text-slate-600">
      <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-600"></span>
      <span>{label}…</span>
    </div>
  );
}
