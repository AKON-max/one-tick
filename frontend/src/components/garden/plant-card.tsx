"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Drop, Sparkle, Flower } from "@phosphor-icons/react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

// ============================================================
// 植物农场卡片：专注分钟 → 能量 → 手动浇水进阶
// - 阶段 0~4 五种造型（种子/发芽/新叶/茁壮/开花结果）
// - 每浇水一次消耗 25 分钟能量，植物进入下一造型
// - 专注会话完成（focus-timer 派发 garden:focus-recorded）后自动刷新
// ============================================================

interface GardenState {
  energy: number;
  wateredCount: number;
  stage: number;
  waterCost: number;
  maxStage: number;
  updatedAt?: string | null;
}

const STAGE_LABELS = ["埋下种子", "破土发芽", "抽出新叶", "日渐茁壮", "开花结果"];

export function PlantCard() {
  const [garden, setGarden] = useState<GardenState | null>(null);
  const [watering, setWatering] = useState(false);
  const aliveRef = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/garden");
      if (!res.ok) return;
      const data: GardenState = await res.json();
      if (aliveRef.current) setGarden(data);
    } catch {
      /* 网络异常时保持旧状态 */
    }
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    void refresh();
    // 专注完成 → 能量到账 → 自动刷新
    const onFocusRecorded = () => void refresh();
    window.addEventListener("garden:focus-recorded", onFocusRecorded);
    return () => {
      aliveRef.current = false;
      window.removeEventListener("garden:focus-recorded", onFocusRecorded);
    };
  }, [refresh]);

  async function handleWater() {
    if (!garden || watering) return;
    setWatering(true);
    try {
      const res = await fetch("/api/garden/water", { method: "POST" });
      const body = (await res.json().catch(() => null)) as
        | (GardenState & { ok?: boolean })
        | { detail?: { code?: string; message?: string } }
        | null;
      if (!res.ok) {
        const message =
          body && "detail" in body ? body.detail?.message : "浇水失败，请稍后再试";
        toast.error(message ?? "浇水失败，请稍后再试");
        return;
      }
      if (body && "ok" in body && body.ok) {
        const { energy, wateredCount, stage, waterCost, maxStage } = body;
        setGarden({ energy, wateredCount, stage, waterCost, maxStage });
        toast.success("浇过水啦，植物正在生长");
      }
    } finally {
      setWatering(false);
    }
  }

  // 首帧加载占位，避免卡片跳动
  if (!garden) {
    return (
      <div className="flex h-[520px] max-h-[62dvh] w-full max-w-[300px] items-center justify-center rounded-xl border border-white/[0.09] bg-[color-mix(in_srgb,var(--theme-background)_58%,transparent)] backdrop-blur-2xl">
        <div className="size-5 animate-spin rounded-full border-2 border-primary/25 border-t-primary" />
      </div>
    );
  }

  const { energy, wateredCount, stage, waterCost, maxStage } = garden;
  const maxed = stage >= maxStage;
  // 距下次浇水的进度（能量可累积，满 1 即可浇水）
  const progress = maxed ? 1 : Math.min(energy / waterCost, 1);
  const needMore = !maxed && energy < waterCost;
  const hint = maxed
    ? "植物已经开花结果，这一株圆满了"
    : needMore
      ? `再专注 ${waterCost - energy} 分钟即可浇水`
      : "消耗 25 分钟能量，浇一次水";

  return (
    <section className="relative flex h-[520px] max-h-[62dvh] w-full max-w-[300px] shrink-0 flex-col overflow-hidden rounded-xl border border-white/[0.09] bg-[color-mix(in_srgb,var(--theme-background)_58%,transparent)] shadow-[0_18px_55px_rgba(0,0,0,0.16)] backdrop-blur-2xl">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-primary/[0.055] to-transparent" />

      {/* 标题 + 能量 */}
      <header className="relative flex items-center justify-between px-4 pb-3 pt-4">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-primary/15 bg-primary/10 text-primary">
            <Flower className="size-4" weight="duotone" />
          </div>
          <div className="min-w-0 leading-tight">
            <h3 className="truncate text-[13px] font-semibold text-foreground">我的植物</h3>
            <p className="mt-1 text-[10px] text-muted-foreground/65">{STAGE_LABELS[stage]}</p>
          </div>
        </div>
        <div
          className="flex shrink-0 items-center gap-1 rounded-full border border-primary/15 bg-primary/10 px-2.5 py-1 text-[11px] font-semibold tabular-nums text-primary"
          title="专注完成的分钟数会自动积累为能量"
        >
          <Drop className="size-3.5" weight="fill" />
          {energy}
        </div>
      </header>

      {/* 植物造型（阶段切换时播放生长动画） */}
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={stage}
            initial={{ opacity: 0, scale: 0.82, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 1.06, y: -6 }}
            transition={{ type: "spring", stiffness: 200, damping: 22 }}
            className="flex items-center justify-center"
          >
            <PlantArt stage={stage} />
          </motion.div>
        </AnimatePresence>
      </div>

      {/* 阶段点 */}
      <div className="flex items-center justify-center gap-1.5 pb-3">
        {Array.from({ length: maxStage + 1 }).map((_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 rounded-full transition-all duration-500",
              i <= stage ? "w-4 bg-primary" : "w-1.5 bg-white/12"
            )}
          />
        ))}
      </div>

      {/* 浇水区 */}
      <div className="border-t border-white/[0.07] px-4 pb-4 pt-3">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground/60">
          <span>{maxed ? "生长完成" : `第 ${stage + 1} 段 · 还需 ${needMore ? waterCost - energy : 0} 分钟`}</span>
          <span className="tabular-nums">{Math.round(progress * 100)}%</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/8">
          <motion.div
            className="h-full rounded-full bg-gradient-to-r from-primary/70 to-primary"
            animate={{ width: `${progress * 100}%` }}
            transition={{ type: "spring", stiffness: 180, damping: 28 }}
          />
        </div>
        <button
          type="button"
          onClick={handleWater}
          disabled={maxed || needMore || watering}
          className={cn(
            "mt-3.5 flex w-full items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold transition-all",
            maxed || needMore || watering
              ? "cursor-not-allowed bg-white/[0.05] text-muted-foreground/50"
              : "bg-primary text-primary-foreground shadow-lg shadow-primary/25 hover:scale-[1.02] hover:bg-primary/90 active:scale-95"
          )}
        >
          {maxed ? (
            <>
              <Sparkle className="size-4" weight="duotone" />
              已经圆满
            </>
          ) : (
            <>
              <Drop className="size-4" weight="bold" />
              {needMore ? "浇水" : "浇水 · 让它长大"}
            </>
          )}
        </button>
        <p className="mt-2 text-center text-[10px] leading-4 text-muted-foreground/40">{hint}</p>
      </div>
    </section>
  );
}

// ============================================================
// 五种造型（0 种子 → 4 开花结果）
// ============================================================

function PlantArt({ stage }: { stage: number }) {
  return (
    <svg
      width="210"
      height="250"
      viewBox="0 0 220 260"
      fill="none"
      className="select-none"
      role="img"
      aria-label={STAGE_LABELS[stage]}
    >
      {/* 土壤 */}
      <g>
        <ellipse cx="110" cy="236" rx="86" ry="18" fill="#6b4423" />
        <ellipse cx="110" cy="232" rx="86" ry="16" fill="#8a5a33" />
        <ellipse cx="110" cy="228" rx="62" ry="11" fill="#9d6a3f" />
        {/* 小碎石光点 */}
        <circle cx="72" cy="231" r="1.6" fill="#c08a55" opacity="0.8" />
        <circle cx="150" cy="234" r="1.4" fill="#c08a55" opacity="0.7" />
        <circle cx="118" cy="238" r="1.2" fill="#c08a55" opacity="0.6" />
      </g>

      {stage === 0 && (
        <g>
          {/* 刚埋下的种子：浅土里拱起一个小丘 */}
          <ellipse cx="110" cy="222" rx="16" ry="7" fill="#7a4f2c" />
          <ellipse cx="110" cy="219" rx="10" ry="5" fill="#a8743f" />
          <ellipse cx="110" cy="217" rx="6" ry="4" fill="#e7c98f" />
        </g>
      )}

      {stage === 1 && (
        <g>
          {/* 破土发芽 */}
          <path d="M110 224 C110 214 110 206 110 198" stroke="#34a853" strokeWidth="5" strokeLinecap="round" />
          <path d="M110 204 C102 196 94 196 90 200 C96 206 104 206 110 202" fill="#67d18a" />
          <path d="M110 198 C118 190 126 190 130 194 C124 200 116 200 110 196" fill="#4cbf6f" />
        </g>
      )}

      {stage === 2 && (
        <g>
          {/* 抽出新叶：主干长高 + 四片叶 */}
          <path d="M110 226 C110 206 110 194 110 180" stroke="#34a853" strokeWidth="6" strokeLinecap="round" />
          <Leaf tip={[60, 196]} dir={-1} />
          <Leaf tip={[160, 196]} dir={1} />
          <Leaf tip={[78, 172]} dir={-1} small />
          <Leaf tip={[142, 172]} dir={1} small />
          <path d="M110 180 C110 172 110 168 110 164" stroke="#34a853" strokeWidth="5" strokeLinecap="round" />
          <Leaf tip={[110, 152]} dir={0} />
        </g>
      )}

      {stage === 3 && (
        <g>
          {/* 日渐茁壮：主茎更高、六片叶 + 花苞 */}
          <path d="M110 228 C110 204 110 190 110 168" stroke="#2f9e54" strokeWidth="7" strokeLinecap="round" />
          <Leaf tip={[56, 202]} dir={-1} />
          <Leaf tip={[164, 202]} dir={1} />
          <Leaf tip={[72, 178]} dir={-1} small />
          <Leaf tip={[148, 178]} dir={1} small />
          <Leaf tip={[86, 156]} dir={-1} small />
          <Leaf tip={[134, 156]} dir={1} small />
          <path d="M110 168 C110 158 110 152 110 146" stroke="#2f9e54" strokeWidth="5" strokeLinecap="round" />
          <Bud cx={110} cy={142} />
        </g>
      )}

      {stage === 4 && (
        <g>
          {/* 开花结果：花冠展开 + 两片大叶托底 */}
          <path d="M110 230 C110 206 110 190 110 166" stroke="#2f9e54" strokeWidth="8" strokeLinecap="round" />
          <Leaf tip={[50, 200]} dir={-1} />
          <Leaf tip={[170, 200]} dir={1} />
          <Leaf tip={[78, 172]} dir={-1} small />
          <Leaf tip={[142, 172]} dir={1} small />
          <path d="M110 166 C110 156 110 150 110 146" stroke="#2f9e54" strokeWidth="6" strokeLinecap="round" />
          <FlowerBlossom cx={110} cy={140} />
        </g>
      )}
    </svg>
  );
}

/** 一片叶子：tip 为叶尖坐标，dir -1 向左倾 / 1 向右倾 / 0 竖直朝上 */
function Leaf({
  tip,
  dir,
  small = false,
}: {
  tip: [number, number];
  dir: -1 | 0 | 1;
  small?: boolean;
}) {
  const [x, y] = tip;
  const s = small ? 0.8 : 1;
  const hue = dir === 1 ? "#5ecf7e" : dir === -1 ? "#45bd68" : "#71dd90";
  if (dir === 0) {
    // 顶部嫩芽：朝上的小叶子
    return (
      <g transform={`translate(${x} ${y}) scale(${s})`}>
        <path d="M0 14 C-8 6 -8 -2 0 -8 C8 -2 8 6 0 14 Z" fill={hue} />
      </g>
    );
  }
  const flip = dir === 1 ? "scale(-1 1)" : "";
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <g transform={`rotate(${dir === 1 ? -24 : 24}) ${flip}`}>
        <path d="M0 0 C-10 -2 -16 6 -12 18 C-6 14 0 8 0 0 Z" fill={hue} />
        <path d="M0 0 C-8 6 -10 14 -8 22" stroke="#2f9e54" strokeWidth="1.4" strokeLinecap="round" fill="none" />
      </g>
    </g>
  );
}

/** 花苞 */
function Bud({ cx, cy }: { cx: number; cy: number }) {
  return (
    <g>
      <ellipse cx={cx} cy={cy - 6} rx="7" ry="11" fill="#7ee2a0" />
      <ellipse cx={cx - 6} cy={cy - 2} rx="5" ry="8" fill="#67d18a" transform={`rotate(-24 ${cx - 6} ${cy - 2})`} />
      <ellipse cx={cx + 6} cy={cy - 2} rx="5" ry="8" fill="#67d18a" transform={`rotate(24 ${cx + 6} ${cy - 2})`} />
    </g>
  );
}

/** 盛开的花 */
function FlowerBlossom({ cx, cy }: { cx: number; cy: number }) {
  const petals = [
    [0, -17],
    [15, -8],
    [11, 10],
    [-11, 10],
    [-15, -8],
  ];
  return (
    <g>
      {petals.map(([dx, dy], i) => (
        <ellipse
          key={i}
          cx={cx + dx}
          cy={cy + dy}
          rx="8.5"
          ry="11"
          fill="#fb923c"
          opacity="0.95"
          transform={`rotate(${i * 72 - 90} ${cx + dx} ${cy + dy})`}
        />
      ))}
      <circle cx={cx} cy={cy} r="7" fill="#fde047" />
      <circle cx={cx - 2} cy={cy - 2} r="2" fill="#fef3c7" opacity="0.9" />
    </g>
  );
}
