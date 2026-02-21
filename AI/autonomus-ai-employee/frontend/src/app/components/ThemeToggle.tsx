"use client";

import { motion } from "framer-motion";
import { useTheme } from "./ThemeProvider";

type ThemeOption = {
  label: string;
  value: "light" | "dark" | "system";
};

const options: ThemeOption[] = [
  { label: "Light", value: "light" },
  { label: "Dark", value: "dark" },
  { label: "Auto", value: "system" },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <div className="theme-toggle">
      {options.map((option) => (
        <motion.button
          key={option.value}
          className={
            theme === option.value
              ? "theme-toggle__button theme-toggle__button--active"
              : "theme-toggle__button"
          }
          onClick={() => setTheme(option.value)}
          type="button"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          transition={{ duration: 0.15 }}
        >
          {option.label}
        </motion.button>
      ))}
    </div>
  );
}
