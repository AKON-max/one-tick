"use client";

import { useRef, useState } from "react";
import { Timer } from "@phosphor-icons/react";
import { FocusTimer, type PomodoroHandle } from "./focus-timer";

const focusPresets = [25, 45, 60];

export function PomodoroStation({
  immersive = false,
  onStart,
}: {
  immersive?: boolean;
  onStart?: () => void;
}) {
  const timerRef = useRef<PomodoroHandle>(null);
  const [focusMinutes, setFocusMinutes] = useState(25);
  const breakMinutes = 5;

  if (immersive) {
    return (
      <FocusTimer
        ref={timerRef}
        focusMinutes={focusMinutes}
        breakMinutes={breakMinutes}
        onRestoreFocusMinutes={setFocusMinutes}
        immersive
      />
    );
  }

  return (
    <section className="relative flex h-[520px] max-h-[62dvh] w-full min-w-0 shrink-0 flex-col overflow-hidden rounded-xl border border-white/[0.09] bg-[color-mix(in_srgb,var(--theme-background)_58%,transparent)] shadow-[0_18px_55px_rgba(0,0,0,0.16)] backdrop-blur-2xl lg:max-h-none">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-primary/[0.055] to-transparent" />

      {/* 标题与时长 */}
      <header className="relative flex items-center justify-between px-4 pb-3 pt-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-primary/15 bg-primary/10 text-primary">
            <Timer className="size-4" weight="duotone" />
          </div>
          <div className="min-w-0 leading-tight">
            <h3 className="truncate text-[13px] font-semibold text-foreground">专注计时</h3>
            <p className="mt-1 text-[10px] text-muted-foreground/65">
              {focusMinutes} 分钟专注 · {breakMinutes} 分钟休息
            </p>
          </div>
        </div>
      </header>

      <div className="mx-4 h-px overflow-hidden bg-white/[0.07]" />

      {/* 预设时长 + 计时圆环 */}
      <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center gap-4 px-4 pb-4">
        <div className="flex items-center rounded-md border border-white/10 bg-black/10 p-1">
          {focusPresets.map((minutes) => (
            <button
              key={minutes}
              type="button"
              onClick={() => setFocusMinutes(minutes)}
              className={
                focusMinutes === minutes
                  ? "rounded bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground"
                  : "rounded px-3 py-1.5 text-xs text-white/55 transition hover:text-white"
              }
            >
              {minutes} 分钟
            </button>
          ))}
        </div>
        <FocusTimer
          ref={timerRef}
          focusMinutes={focusMinutes}
          breakMinutes={breakMinutes}
          onRestoreFocusMinutes={setFocusMinutes}
          onStart={onStart}
        />
      </div>
    </section>
  );
}
