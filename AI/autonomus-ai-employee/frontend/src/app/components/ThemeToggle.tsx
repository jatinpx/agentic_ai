"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useTheme } from "./ThemeProvider";

type ThemeOption = {
  label: string;
  value: "light" | "dark" | "sand" | "forest" | "system";
};

const options: ThemeOption[] = [
  { label: "Light", value: "light" },
  { label: "Dark", value: "dark" },
  { label: "Sand", value: "sand" },
  { label: "Forest", value: "forest" },
  { label: "Auto", value: "system" },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const currentLabel = options.find((option) => option.value === theme)?.label || "Theme";

  return (
    <div ref={rootRef} className="theme-dropdown">
      <motion.button
        className="ghost-button text-xs px-3 py-2"
        onClick={() => setOpen((prev) => !prev)}
        type="button"
        whileHover={{ scale: 1.03, y: -1 }}
        whileTap={{ scale: 0.97 }}
        transition={{ duration: 0.18 }}
      >
        Theme: {currentLabel} ▾
      </motion.button>

      {open && (
        <motion.div
          className="theme-dropdown__menu"
          initial={{ opacity: 0, y: 6, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 6, scale: 0.98 }}
          transition={{ duration: 0.16 }}
        >
          {options.map((option) => (
            <button
              key={option.value}
              className={theme === option.value ? "theme-dropdown__item theme-dropdown__item--active" : "theme-dropdown__item"}
              onClick={() => {
                setTheme(option.value);
                setOpen(false);
              }}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </motion.div>
      )}
    </div>
  );
}
