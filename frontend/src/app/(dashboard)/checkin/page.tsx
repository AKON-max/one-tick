import { requireAuth } from "@/lib/auth-utils";
import { startOfYear, endOfYear, format, eachDayOfInterval } from "date-fns";
import LearningIsland from "@/components/landing/learning-island-dynamic";
import { Heatmap } from "@/components/calendar/heatmap";
import { CheckinButton } from "./checkin-button";
import { FootprintHeading } from "./footprint-heading";
import { SceneSelector } from "@/components/island/scene-selector";

// FastAPI 服务端直连（与 auth-utils 一致）
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://localhost:8001";

interface CheckinSummary {
  todayCheckin: boolean;
  streak: number;
  totalCheckins: number;
  totalHours: number;
  weekCheckins: number;
  heatmap: { date: string; checked: boolean }[];
  longestStreak: number;
}

export default async function CheckinPage() {
  const user = await requireAuth();
  const now = new Date();

  // 一次拉取签到页全部聚合数据（对应原 7 次 Prisma 查询）
  let summary: CheckinSummary | null = null;
  try {
    const res = await fetch(`${API_INTERNAL_URL}/api/checkins/summary`, {
      cache: "no-store",
    });
    if (res.ok) summary = (await res.json()) as CheckinSummary;
  } catch {
    // FastAPI 不可达时页面降级展示，不抛错
  }

  const todayCheckin = summary?.todayCheckin ?? false;
  const streak = summary?.streak ?? 0;
  const totalCheckins = summary?.totalCheckins ?? 0;
  const userTotalHours = summary?.totalHours ?? 0;
  const todayCheckins = todayCheckin ? 5 : 0;
  const weekCheckins = summary?.weekCheckins ?? 0;
  const longestStreak = summary?.longestStreak ?? 0;

  // 年度热力图（接口没返回时回退为空年视图）
  const yearStart = startOfYear(now);
  const yearEnd = endOfYear(now);
  const heatmapData =
    summary?.heatmap ??
    eachDayOfInterval({ start: yearStart, end: yearEnd }).map((d) => ({
      date: format(d, "yyyy-MM-dd"),
      checked: false,
    }));
  const checkedInDays = new Set(heatmapData.filter((d) => d.checked).map((d) => d.date));

  const todayDate = now.toLocaleDateString("zh-CN", {
    month: "long", day: "numeric", weekday: "long",
  });

  return (
    <div className="relative h-[100dvh] w-full overflow-hidden">
      {/* ── 3D 小岛（透明背景，融入全局背景） ── */}
      <div className="absolute inset-0">
        <LearningIsland
          totalCheckins={totalCheckins}
          streak={streak}
          totalHours={userTotalHours}
          todayCheckins={todayCheckins}
        />
      </div>

      {/* 顶部渐变遮罩（轻量，仅保证文字可读） */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-36 bg-gradient-to-b from-background/85 to-transparent" />

      {/* ── 顶部：标题 + 统计 ── */}
      <div className="absolute inset-x-0 top-0 z-20 flex items-start justify-between gap-4 px-4 pt-24 md:px-10 md:pt-24">
        <div className="flex flex-col gap-3">
          <div>
            <p className="product-eyebrow whitespace-nowrap">
              {todayDate}
            </p>
            <h1 className="mt-2 text-2xl font-semibold text-white md:text-3xl">
              小岛
            </h1>
          </div>
          <SceneSelector />
        </div>
        <div className="surface grid grid-cols-3 overflow-hidden">
          {[
            { label: "持续来访", value: streak, unit: "天" },
            { label: "岛龄", value: totalCheckins, unit: "天" },
            { label: "本周足迹", value: weekCheckins, unit: "天" },
          ].map((item) => (
            <div key={item.label} className="min-w-16 border-l border-white/8 px-2.5 py-2 text-center first:border-l-0 md:min-w-24 md:px-4 md:py-2.5">
              <p className="truncate text-[9px] text-white/36 md:text-[10px]">{item.label}</p>
              <p className="text-lg font-semibold tabular-nums text-foreground md:text-xl">
                {item.value}
                <span className="ml-0.5 text-xs font-normal text-muted-foreground">{item.unit}</span>
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* ── 底部：热力图 + 签到 融合面板 ── */}
      <div className="absolute inset-x-0 bottom-0 z-20">
        <div className="pointer-events-none h-16 bg-gradient-to-t from-background/70 to-transparent" />

        <div className="border-t border-white/[0.06] bg-background/75 backdrop-blur-4xl">
          <div className="mx-auto flex max-w-[1440px] flex-col gap-5 px-4 py-5 md:flex-row md:items-end md:gap-8 md:px-10 md:py-6">
            {/* 左侧：热力图 */}
            <div className="flex-1 overflow-hidden">
              <FootprintHeading exploredDays={checkedInDays.size} longestStreak={longestStreak} />
              <div className="overflow-x-auto pb-1">
                <Heatmap data={heatmapData} year={now.getFullYear()} compact />
              </div>
            </div>

            {/* 右侧分隔 + 签到区 */}
            <div className="hidden h-16 w-px bg-border md:block" />
            <div className="flex shrink-0 items-center justify-center md:justify-end">
              {todayCheckin ? (
                <div className="flex items-center gap-3 rounded-md bg-primary/8 px-5 py-3 ring-1 ring-primary/20">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/20">
                    <svg className="h-5 w-5 text-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-primary">今天来过了</p>
                    <p className="text-xs text-primary/60">已持续 {streak} 天</p>
                  </div>
                </div>
              ) : (
                <CheckinButton />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
