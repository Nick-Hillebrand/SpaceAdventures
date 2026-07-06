interface SkeletonProps {
  width?: string;
  height?: string;
  className?: string;
}

export default function Skeleton({ width = "100%", height = "1rem", className = "" }: SkeletonProps) {
  return (
    <div
      className={`skeleton-block ${className}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}
