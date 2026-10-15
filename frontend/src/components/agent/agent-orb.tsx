"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkle } from "@phosphor-icons/react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useSceneCopy } from "@/context/scene-context";
import { cn } from "@/lib/utils";

// 悬浮球位置（拖动后记忆）
const ORB_POSITION_KEY = "rainforest-orb-position";
// 首次引导气泡是否已看过
const ORB_HINT_KEY = "rainforest-orb-hint";

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

// 全局悬浮球：可拖动；点击（非拖拽）跳转到智能体独立页面 /agent
export function AgentOrb() {
  const router = useRouter();
  const { explorerTitle, explorerButtonLabel } = useSceneCopy();
  const [position, setPosition] = useState({ x: 0, y: 0 });
  // 位置算出来之前不显示：否则球和常驻标签会在左上角闪一下
  const [ready, setReady] = useState(false);
  const [viewportWidth, setViewportWidth] = useState(0);
  const [showHint, setShowHint] = useState(false);
  const dragRef = useRef({ dragging: false, moved: false, dx: 0, dy: 0 });

  useEffect(() => {
    const saved = localStorage.getItem(ORB_POSITION_KEY);
    let parsed: { x: number; y: number } | null = null;
    try {
      parsed = saved ? (JSON.parse(saved) as { x: number; y: number }) : null;
    } catch {
      localStorage.removeItem(ORB_POSITION_KEY);
    }
    const frame = requestAnimationFrame(() => {
      setViewportWidth(window.innerWidth);
      setPosition({
        x: parsed?.x ?? window.innerWidth - 92,
        y: parsed?.y ?? Math.round(window.innerHeight * 0.62),
      });
      setReady(true);
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  // 首次进入：冒一次气泡说明这颗球是什么（看过就写标记，不再打扰）
  useEffect(() => {
    if (localStorage.getItem(ORB_HINT_KEY)) return;
    const timer = setTimeout(() => setShowHint(true), 1200);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!showHint) return;
    const timer = setTimeout(dismissHint, 12000);
    return () => clearTimeout(timer);
  }, [showHint]);

  function dismissHint() {
    setShowHint(false);
    localStorage.setItem(ORB_HINT_KEY, "1");
  }

  useEffect(() => {
    function keepOrbInViewport() {
      setViewportWidth(window.innerWidth);
      setPosition((current) => {
        const next = {
          x: current.x + 32 < window.innerWidth / 2 ? 12 : window.innerWidth - 76,
          y: clamp(current.y, 76, window.innerHeight - 76),
        };
        localStorage.setItem(ORB_POSITION_KEY, JSON.stringify(next));
        return next;
      });
    }
    window.addEventListener("resize", keepOrbInViewport);
    return () => window.removeEventListener("resize", keepOrbInViewport);
  }, []);

  function onPointerDown(event: React.PointerEvent<HTMLButtonElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      dragging: true,
      moved: false,
      dx: event.clientX - position.x,
      dy: event.clientY - position.y,
    };
  }

  function onPointerMove(event: React.PointerEvent<HTMLButtonElement>) {
    if (!dragRef.current.dragging) return;
    const nextX = clamp(event.clientX - dragRef.current.dx, 12, window.innerWidth - 76);
    const nextY = clamp(event.clientY - dragRef.current.dy, 76, window.innerHeight - 76);
    if (Math.abs(nextX - position.x) > 3 || Math.abs(nextY - position.y) > 3) dragRef.current.moved = true;
    setPosition({ x: nextX, y: nextY });
  }

  function onPointerUp() {
    if (!dragRef.current.dragging) return;
    dragRef.current.dragging = false;
    if (!dragRef.current.moved) {
      // 点击（未拖动）→ 跳转到智能体页面
      dismissHint();
      router.push("/agent");
      return;
    }
    const snapped = {
      x: position.x + 32 < window.innerWidth / 2 ? 12 : window.innerWidth - 76,
      y: clamp(position.y, 76, window.innerHeight - 76),
    };
    setPosition(snapped);
    localStorage.setItem("rainforest-orb-position", JSON.stringify(snapped));
  }

  // 球在左半屏时，常驻标签/气泡改贴右侧，避免被屏幕边缘裁掉
  const side: "left" | "right" =
    viewportWidth > 0 && position.x + 32 < viewportWidth / 2 ? "left" : "right";

  return (
    <div
      data-side={side}
      className={cn(
        "rainforest-orb-wrap touch-none select-none transition-opacity duration-300",
        ready ? "opacity-100" : "opacity-0"
      )}
      style={{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }}
    >
      <Tooltip>
        <TooltipTrigger
          render={
            <button
              type="button"
              data-tour="ai-orb"
              aria-label={explorerButtonLabel}
              className="rainforest-orb touch-none select-none"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
            />
          }
        >
          <span className="rainforest-orb__halo" />
          <span className="rainforest-orb__core"><Sparkle weight="fill" /></span>
          <span className="rainforest-orb__spark rainforest-orb__spark--one" />
          <span className="rainforest-orb__spark rainforest-orb__spark--two" />
        </TooltipTrigger>
        <TooltipContent side="left">{explorerTitle}</TooltipContent>
      </Tooltip>

      {/* 常驻标签：不悬停也能看出这是 AI 入口 */}
      <span className="rainforest-orb__label">问问雨宝</span>

      {/* 首次进入的一次性引导气泡 */}
      {showHint && (
        <div className="rainforest-orb__hint">
          我是雨宝，点我就能提问、拆计划、翻资料；也能拖动我换个位置
        </div>
      )}
    </div>
  );
}
