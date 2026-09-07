"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { Drop, Sparkle, Tree } from "@phosphor-icons/react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

// ============================================================
// 植物农场卡片：专注分钟 → 能量 → 手动浇水进阶
// 盆栽长的是“树”，与 3D 小岛上的树同一造型语言：
// - 阶段 0~4：种子/发芽/成苗/小树/成熟成树（第 4 段 = 岛树的样子）
// - 每次浇水消耗 25 分钟能量，植物进入下一造型
// - 成熟(第4段)后再浇一次 = 收获：盆栽回到种子，
//   小岛上的树 +1（树的棵数 = maturedCount，见小岛接口）
// - 专注会话完成（focus-timer 派发 garden:focus-recorded）后自动刷新
// ============================================================

interface GardenState {
  energy: number;
  wateredCount: number;
  maturedCount: number;
  stage: number;
  waterCost: number;
  maxStage: number;
  updatedAt?: string | null;
}

const STAGE_LABELS = ["埋下种子", "破土发芽", "抽枝成苗", "枝叶渐丰", "成熟成树"];

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
        | (GardenState & { ok?: boolean; harvested?: boolean })
        | { detail?: { code?: string; message?: string } }
        | null;
      if (!res.ok) {
        const message =
          body && "detail" in body ? body.detail?.message : "浇水失败，请稍后再试";
        toast.error(message ?? "浇水失败，请稍后再试");
        return;
      }
      if (body && "ok" in body && body.ok) {
        const { energy, stage, waterCost, maxStage, maturedCount, harvested } =
          body as GardenState & { harvested?: boolean };
        setGarden({
          energy,
          wateredCount: (body as GardenState).wateredCount ?? 0,
          stage,
          waterCost,
          maxStage,
          maturedCount,
        });
        if (harvested) {
          toast.success("收获一棵树，小岛又多了一棵树！", {
            icon: <Tree className="size-4" weight="fill" />,
          });
        } else {
          toast.success("浇过水啦，小树正在长大");
        }
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

  const { energy, wateredCount, stage, waterCost, maxStage, maturedCount } = garden;
  const maxed = stage >= maxStage;
  // 距下次浇水的进度（能量可累积，满 1 即可浇水/收获）
  const progress = Math.min(energy / waterCost, 1);
  const needMore = energy < waterCost;
  const hint = maxed
    ? needMore
      ? `再专注 ${waterCost - energy} 分钟即可收获成树`
      : "再浇一次水，把这棵树种到小岛上去"
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
            <Tree className="size-4" weight="duotone" />
          </div>
          <div className="min-w-0 leading-tight">
            <h3 className="truncate text-[13px] font-semibold text-foreground">我的树</h3>
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

      {/* 树的造型（阶段切换时播放生长动画） */}
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
      <div className="flex items-center justify-center gap-1.5 pb-2">
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

      {/* 已种到小岛的树（与 3D 小岛联动） */}
      <div className="flex items-center justify-center gap-1.5 pb-3 text-[11px] text-muted-foreground/70">
        <Tree className="size-3.5" weight="duotone" />
        <span>
          已种到小岛 <span className="font-semibold tabular-nums text-foreground/85">{maturedCount}</span> 棵
        </span>
      </div>

      {/* 浇水/收获区 */}
      <div className="border-t border-white/[0.07] px-4 pb-4 pt-3">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground/60">
          <span>
            {maxed
              ? `已成熟 · 第 ${stage + 1} 段`
              : `第 ${stage + 1} 段 · 还需 ${needMore ? waterCost - energy : 0} 分钟`}
          </span>
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
          disabled={needMore || watering}
          className={cn(
            "mt-3.5 flex w-full items-center justify-center gap-2 rounded-full px-4 py-2.5 text-sm font-semibold transition-all",
            needMore || watering
              ? "cursor-not-allowed bg-white/[0.05] text-muted-foreground/50"
              : "bg-primary text-primary-foreground shadow-lg shadow-primary/25 hover:scale-[1.02] hover:bg-primary/90 active:scale-95"
          )}
        >
          {maxed ? (
            <>
              <Sparkle className="size-4" weight="duotone" />
              收获成树 · 种到小岛
            </>
          ) : (
            <>
              <Drop className="size-4" weight="bold" />
              浇水 · 让它长大
            </>
          )}
        </button>
        <p className="mt-2 text-center text-[10px] leading-4 text-muted-foreground/40">{hint}</p>
      </div>
    </section>
  );
}

// ============================================================
// 树的造型：0 种子 → 4 成熟成树（第 4 段 = 3D 小岛上那棵树的造型）
// 低多边形树冠 + 褐色树干，与小岛 TinyTree 同一语言
// ============================================================

const TRUNK = "#6b5a3e"; // 与岛树树皮一致
const LEAF_DARK = "#4d9e6a";
const LEAF_MID = "#5ead78";
const LEAF_LIGHT = "#6dbf8a";
const LEAF_HI = "#82cf9d";

function PlantArt({ stage }: { stage: number }) {
  return (
    <svg
      width="210"
      height="250"
      viewBox="0 0 220 270"
      fill="none"
      className="select-none"
      role="img"
      aria-label={STAGE_LABELS[stage]}
    >
      {/* 陶盆 + 泥土 */}
      <Pot />

      {stage === 0 && (
        <g>
          {/* 埋下的种子：土里拱起一个小丘 */}
          <ellipse cx="110" cy="206" rx="20" ry="9" fill="#7a4f2c" />
          <ellipse cx="110" cy="202" rx="12" ry="6" fill="#a8743f" />
          <ellipse cx="110" cy="200" rx="7" ry="4.5" fill="#e7c98f" />
        </g>
      )}

      {stage === 1 && (
        <g>
          {/* 破土发芽：嫩茎 + 两片小芽 */}
          <path
            d="M110 208 C110 196 110 188 110 180"
            stroke="#45bd68"
            strokeWidth="4"
            strokeLinecap="round"
          />
          <path d="M110 188 C103 181 95 181 92 184.5 C98 190 105 190 110 186" fill="#67d18a" />
          <path d="M110 182 C117 175 125 175 128 178.5 C122 184 115 184 110 180" fill="#4cbf6f" />
        </g>
      )}

      {stage === 2 && (
        <g>
          {/* 抽枝成苗：笔直小树干 + 迷你树冠 */}
          <TreeTrunk top={172} base={208} wTop={2.4} wBase={6.5} />
          <TreeCrown cx={110} cy={160} R={15} />
        </g>
      )}

      {stage === 3 && (
        <g>
          {/* 枝叶渐丰：树干长高，树冠更大 */}
          <TreeTrunk top={150} base={208} wTop={3} wBase={9} />
          <TreeCrown cx={110} cy={140} R={25} />
        </g>
      )}

      {stage === 4 && (
        <g>
          {/* 成熟成树：与 3D 小岛上的树一致的低多边形大树 */}
          <TreeTrunk top={126} base={208} wTop={3.5} wBase={12} />
          <TreeCrown cx={110} cy={116} R={36} />
        </g>
      )}
    </svg>
  );
}

/** 陶盆 + 盆内泥土（底部固定，树从土里长出来） */
function Pot() {
  return (
    <g>
      {/* 盆身 */}
      <path d="M52 226 L82 262 L138 262 L168 226 L168 220 L52 220 Z" fill="#c47a4a" />
      {/* 盆身阴影 */}
      <path d="M52 220 L82 262 L102 262 L64 220 Z" fill="#b06a3e" opacity="0.85" />
      {/* 盆沿 */}
      <rect x="46" y="212" width="128" height="15" rx="7" fill="#d08a56" />
      {/* 盆沿高光 */}
      <rect x="52" y="214" width="116" height="4" rx="2" fill="#e09a64" opacity="0.9" />
      {/* 泥土 */}
      <ellipse cx="110" cy="212" rx="58" ry="9" fill="#5b3d21" />
      <ellipse cx="110" cy="209" rx="44" ry="6" fill="#6b4423" />
      {/* 小碎石光点 */}
      <circle cx="86" cy="211" r="1.5" fill="#8a5a33" opacity="0.8" />
      <circle cx="136" cy="213" r="1.3" fill="#8a5a33" opacity="0.7" />
    </g>
  );
}

/** 树干：上细下粗的褐色梯形（岛树风格） */
function TreeTrunk({
  top,
  base,
  wTop,
  wBase,
}: {
  top: number;
  base: number;
  wTop: number;
  wBase: number;
}) {
  return (
    <g>
      <polygon
        points={`${110 - wBase / 2},${base} ${110 + wBase / 2},${base} ${110 + wTop / 2},${top} ${110 - wTop / 2},${top}`}
        fill={TRUNK}
      />
      {/* 树干右侧阴影，增加圆柱感 */}
      <polygon
        points={`${110},${base} ${110 + wBase / 2},${base} ${110 + wTop / 2},${top} ${110},${top}`}
        fill="#00000022"
      />
    </g>
  );
}

/** 一块低多边形树冠叶片：不规则 6 边形，模拟 3D icosahedron 的切面 */
function CrownBlob({ cx, cy, r, color }: { cx: number; cy: number; r: number; color: string }) {
  const pts: string[] = [];
  for (let i = 0; i < 6; i++) {
    const angle = (i / 6) * Math.PI * 2 + (i % 3) * 0.38 + 0.6;
    const rad = r * (1 + Math.sin(i * 1.9 + cx * 0.03) * 0.18);
    pts.push(`${(cx + Math.cos(angle) * rad).toFixed(1)},${(cy + Math.sin(angle) * rad).toFixed(1)}`);
  }
  return <polygon points={pts.join(" ")} fill={color} />;
}

/** 树冠：4 片错落的低多边形叶簇（颜色与 3D 小岛 TinyTree 一致） */
function TreeCrown({ cx, cy, R }: { cx: number; cy: number; R: number }) {
  return (
    <g>
      <CrownBlob cx={cx - R * 0.46} cy={cy + R * 0.22} r={R * 0.42} color={LEAF_DARK} />
      <CrownBlob cx={cx + R * 0.46} cy={cy + R * 0.2} r={R * 0.4} color={LEAF_MID} />
      <CrownBlob cx={cx + R * 0.1} cy={cy - R * 0.4} r={R * 0.4} color={LEAF_HI} />
      <CrownBlob cx={cx} cy={cy} r={R * 0.62} color={LEAF_LIGHT} />
    </g>
  );
}
