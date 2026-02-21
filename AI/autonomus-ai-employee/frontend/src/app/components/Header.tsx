import type { ReactNode } from "react";
import { ThemeToggle } from "./ThemeToggle";

export function Header({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="glass-header">
      <div>
        <p className="eyebrow">Autonomous Suite</p>
        <h1 className="display-text">{title}</h1>
        {subtitle ? <p className="header-subtitle">{subtitle}</p> : null}
      </div>
      <div className="header-actions">
        {actions}
        <ThemeToggle />
      </div>
    </header>
  );
}
