"use client";

import { motion } from "motion/react";
import { CalendarCheck, Drop, Fire, Sparkle, Tree } from "@phosphor-icons/react";
import LearningIsland from "@/components/landing/learning-island-dynamic";
import { PlantArt } from "@/components/garden/plant-card";

/** 盆栽 5 个造型阶段（与专注房「我的树」一致） */
const treeStages = ["埋下种子", "破土发芽", "抽枝成苗", "枝叶渐丰", "成熟成树"];

/** 小岛：打卡留下的足迹 */
const islandPoints = [
  {
    icon: CalendarCheck,
    title: "打卡即留痕",
    copy: "每天到访小岛，足迹自动落在地图上，配合热力图把连续天数一眼看清。",
  },
  {
    icon: Fire,
    title: "坚持有形状",
    copy: "不再是冷冰冰的数字——小岛的绿意会随着你的节奏一点点变浓。",
  },
];

/** 种树：专注能量 → 浇水 → 收获上岛 */
const treePoints = [
  {
    icon: Drop,
    title: "专注攒能量",
    copy: "每完成一段专注，能量自动到账；攒够 25 分钟就能浇一次水。",
  },
  {
    icon: Sparkle,
    title: "收获后上岛",
    copy: "盆栽成熟即可收获，收获的树会直接种到 3D 小岛上，越专注岛越茂盛。",
  },
];

export function IslandShowcase() {
  return (
    <section id="island" className="relative border-y border-white/10 bg-background/88 px-4 py-20 text-white backdrop-blur-2xl md:px-8 md:py-28">
      <div className="mx-auto max-w-7xl">
        {/* 标题 */}
        <div className="grid gap-8 md:grid-cols-[0.9fr_1.1fr] md:items-end">
          <div>
            <p className="text-sm font-semibold text-primary">打卡与专注，都会长出来</p>
            <h2 className="mt-3 text-3xl font-semibold leading-tight md:text-5xl">
              坚持会变成一座岛，
              <br />
              专注会种出<span className="text-primary">一片树</span>
            </h2>
          </div>
          <p className="max-w-2xl text-base leading-relaxed text-white/58 md:text-lg">
            在 One-Tick 里，成长不是一句鼓励。每天的打卡会落在小岛上，每段专注会浇灌一棵盆栽——
            时间久了，你的坚持真的看得见。
          </p>
        </div>

        {/* 两张功能卡：小岛 / 种树 */}
        <div className="mt-14 grid gap-6 lg:grid-cols-2">
          {/* 小岛：真实 3D 小岛预览 */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.6 }}
            className="flex flex-col rounded-lg border border-white/14 bg-background/74 p-6 shadow-[0_32px_90px_rgba(0,0,0,0.28)] sm:p-8"
          >
            <div className="flex items-center gap-3">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/14 text-primary">
                <Tree className="size-5" weight="duotone" />
              </span>
              <div>
                <h3 className="text-lg font-semibold">小岛：把坚持长成一座岛</h3>
                <p className="mt-0.5 text-[11px] text-white/35">打卡足迹 · 连续天数 · 岛屿绿化</p>
              </div>
            </div>

            {/* 3D 小岛预览：画布必须是真实布局尺寸（不能再用 CSS transform 缩放，
                否则 three 量到的是缩放后的客户区尺寸，画布会缩到容器左上角导致整体偏心）；
                岛在画布中的大小改由正交相机 zoom 控制 */}
            <div className="mt-7 overflow-hidden rounded-lg border border-white/12 bg-black/25">
              <div className="flex h-[230px] items-center justify-center md:h-[250px] lg:h-[280px]">
                <div className="h-full w-full max-w-[300px] shrink-0 md:max-w-none md:w-[420px] lg:w-[500px]">
                  <LearningIsland
                    totalCheckins={0}
                    streak={12}
                    totalHours={18.6}
                    todayCheckin
                    treeCount={10}
                    zoom={52}
                  />
                </div>
              </div>
              <div className="flex items-center justify-between gap-3 border-t border-white/10 px-4 py-2.5 text-[11px] text-white/40">
                <span>岛上的树 = 收获的成熟盆栽</span>
                <span>岛龄 42 天 · 岛上 10 棵树</span>
              </div>
            </div>

            <div className="mt-6 space-y-5">
              {islandPoints.map(({ icon: Icon, title, copy }) => (
                <div key={title} className="flex items-start gap-4">
                  <Icon className="size-5 shrink-0 text-primary" weight="duotone" />
                  <div>
                    <p className="text-sm font-semibold">{title}</p>
                    <p className="mt-1 text-xs leading-5 text-white/45">{copy}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>

          {/* 种树：5 段真实树形 */}
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.6, delay: 0.08 }}
            className="flex flex-col rounded-lg border border-white/14 bg-background/74 p-6 shadow-[0_32px_90px_rgba(0,0,0,0.28)] sm:p-8"
          >
            <div className="flex items-center gap-3">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/14 text-primary">
                <Drop className="size-5" weight="fill" />
              </span>
              <div>
                <h3 className="text-lg font-semibold">种树：把专注浇成一棵树</h3>
                <p className="mt-0.5 text-[11px] text-white/35">专注能量 · 浇水进阶 · 收获上岛</p>
              </div>
            </div>

            {/* 5 段生长：种子 → 成熟成树（与专注房「我的树」同一套造型） */}
            <div className="mt-7 rounded-lg border border-white/12 bg-black/20 px-4 py-4">
              <div className="flex items-end justify-between gap-1">
                {treeStages.map((stage, index) => (
                  <div key={stage} className="flex min-w-0 flex-1 flex-col items-center gap-2">
                    <PlantArt
                      stage={index}
                      width={96}
                      height={110}
                      className="h-auto w-full max-w-[96px]"
                    />
                    <span
                      className={`truncate text-[10px] ${
                        index === treeStages.length - 1 ? "text-primary/85" : "text-white/40"
                      }`}
                    >
                      {stage}
                    </span>
                  </div>
                ))}
              </div>

              {/* 浇水进度：每 25 分钟能量浇一次，第 5 段成熟可收获 */}
              <div className="mt-4 border-t border-white/10 pt-3">
                <div className="flex items-center justify-between gap-3 text-[10px] text-white/40">
                  <span>浇水进度 · 满 25 分钟能量浇一次</span>
                  <span className="shrink-0 text-primary">第 5 段 · 可收获上岛</span>
                </div>
                <div className="mt-2 flex gap-1">
                  {treeStages.map((stage, index) => (
                    <span
                      key={stage}
                      className={`h-1 flex-1 rounded-full ${
                        index < treeStages.length - 1 ? "bg-primary/45" : "bg-primary"
                      }`}
                    />
                  ))}
                </div>
              </div>
            </div>

            <div className="mt-6 space-y-5">
              {treePoints.map(({ icon: Icon, title, copy }) => (
                <div key={title} className="flex items-start gap-4">
                  <Icon className="size-5 shrink-0 text-primary" weight="duotone" />
                  <div>
                    <p className="text-sm font-semibold">{title}</p>
                    <p className="mt-1 text-xs leading-5 text-white/45">{copy}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
